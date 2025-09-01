import asyncio
import json
import logging
import multiprocessing
import sys
import time
from typing import Any
from typing import Callable

import typer
import zmq
import zmq.asyncio

from egse.log import logger
from egse.logger import remote_logging
from egse.notifyhub import DEFAULT_COLLECTOR_PORT
from egse.notifyhub import DEFAULT_PUBLISHER_PORT
from egse.notifyhub import DEFAULT_REQUESTS_PORT
from egse.notifyhub import STATS_INTERVAL
from egse.notifyhub.client import AsyncNotificationHubClient
from egse.registry import MessageType
from egse.registry.client import AsyncRegistryClient, REQUEST_TIMEOUT
from egse.system import TyperAsyncCommand
from egse.system import get_host_ip
from .event import NotificationEvent

REQUEST_POLL_TIMEOUT = 1.0
"""time to wait for while listening for requests [seconds]."""

app = typer.Typer(name="notify_hub")


class AsyncNotificationHub:
    def __init__(self):
        self.server_id = "notification-hub-1"

        self.context: zmq.asyncio.Context = zmq.asyncio.Context()

        # Receive events from services (PULL socket for load balancing)
        self.collector_socket: zmq.asyncio.Socket = self.context.socket(zmq.PULL)

        # Publish events to subscribers (PUB socket for fan-out)
        self.publisher_socket: zmq.asyncio.Socket = self.context.socket(zmq.PUB)

        # Health check socket (ROUTER - can handle multiple clients)
        self.requests_socket: zmq.asyncio.Socket = self.context.socket(zmq.ROUTER)

        # Register notification hub to the service registry
        self.registry_client = AsyncRegistryClient(timeout=REQUEST_TIMEOUT)
        self.service_id = None
        self.service_name = "Notification Hub"
        self.service_type = "notification-hub"

        self.stats = {
            "events_received": 0,
            "events_published": 0,
            "last_message_time": 0.0,
            "start_time": time.time(),
        }

        self.running = False
        self._shutdown_event = asyncio.Event()

        # Tasks
        self._tasks = set()

        self.logger = logging.getLogger("egse.notifyhub")

    async def start(self):
        """Start the notification hub. This will start the event collector and
        publisher, the health check, and the stats reporter as asyncio Tasks.
        """
        multiprocessing.current_process().name = "notifyhub"

        self.running = True
        self.logger.info("Starting Async Notification Hub...")

        self.collector_socket.bind(f"tcp://*:{DEFAULT_COLLECTOR_PORT}")
        self.publisher_socket.bind(f"tcp://*:{DEFAULT_PUBLISHER_PORT}")
        self.requests_socket.bind(f"tcp://*:{DEFAULT_REQUESTS_PORT}")

        self._tasks = [
            asyncio.create_task(self._event_collector()),
            asyncio.create_task(self._stats_reporter()),
            asyncio.create_task(self._handle_requests()),
        ]

        await self._register_service()

        await self._shutdown_event.wait()

        await self._deregister_service()

        await self._shutdown()

    async def _shutdown(self):
        self.running = False
        self.logger.info("Async Notification Hub shutdown requested...")

        # Wait for tasks to gracefully complete (with timeout)
        if self._tasks:
            done, pending = await asyncio.wait(self._tasks, timeout=2.0)
            for task in pending:
                task.cancel()

        self.collector_socket.close()
        self.publisher_socket.close()
        self.requests_socket.close()

        self.context.term()

        self.logger.info("Async Notification Hub shutdown complete")

    async def _register_service(self):
        self.logger.info("Registering service...")

        self.registry_client.connect()

        self.service_id = await self.registry_client.register(
            name=self.service_name,
            host=get_host_ip(),
            port=DEFAULT_REQUESTS_PORT,
            service_type=self.service_type,
            metadata={"pub_port": DEFAULT_PUBLISHER_PORT, "collector_port": DEFAULT_COLLECTOR_PORT},
        )

        if not self.service_id:
            self.logger.error("Failed to register with the service registry")
        else:
            await self.registry_client.start_heartbeat()

    async def _deregister_service(self):
        self.logger.info("De-registering service...")

        if self.service_id:
            await self.registry_client.stop_heartbeat()
            await self.registry_client.deregister()

        self.registry_client.disconnect()

    async def _event_collector(self):
        """Main event collection loop"""
        while self.running:
            try:
                # Receive event from any service (non-blocking with timeout)
                message_bytes = await asyncio.wait_for(self.collector_socket.recv(), timeout=0.1)

                message = json.loads(message_bytes.decode())

                event = NotificationEvent(
                    event_type=message["event_type"],
                    source_service=message["source_service"],
                    data=message["data"],
                    timestamp=message.get("timestamp"),
                    correlation_id=message.get("correlation_id"),
                )

                self.logger.info(f"Received: {event.event_type} from {event.source_service}")

                self.stats["events_received"] += 1
                self.stats["last_message_time"] = time.time()

                await self._publish_event(event)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                self.logger.warning("Event collector cancelled.")
                self.running = False
            except Exception as exc:
                self.logger.error(f"Error in event collector: {exc}", exc_info=True)
                # Why waiting 1s here?
                # - Is this to prevent overloading the logger when there is a serious problem
                # - Will this improve when we get more experience with the NotifyHub?
                await asyncio.sleep(1.0)

    async def _publish_event(self, event: NotificationEvent):
        """Publish event to all subscribers"""
        try:
            await self.publisher_socket.send_multipart(
                [
                    event.event_type.encode(),  # Topic for filtering
                    json.dumps(event.as_dict()).encode(),  # Event data
                ]
            )

            self.stats["events_published"] += 1
            self.logger.info(f"Published: {event.event_type}")

        except Exception as exc:
            self.logger.error(f"Error publishing event: {exc}")

    async def _stats_reporter(self):
        """Periodically report statistics"""
        while self.running:
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=STATS_INTERVAL)
                # shutdown was requested if we get here
                # self.logger.info("Shutdown request caught in stats reporter.")
                break
            except asyncio.TimeoutError:
                # normal case, 30s timeout before next report
                # FIXME: Shouldn't this also be reported on the PUB channel?
                self.logger.info(f"Stats: {self.stats}")
            except asyncio.CancelledError:
                self.logger.warning("Stats reporter cancelled.")
                self.running = False

    async def _handle_requests(self):
        """Handle basic requests like e.g. health check."""
        self.logger.info("Started request handler task")

        while self.running:
            try:
                try:
                    message_parts = await asyncio.wait_for(
                        self.requests_socket.recv_multipart(), timeout=REQUEST_POLL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    # self.logger.debug("waiting for command request...")
                    continue

                if len(message_parts) >= 3:
                    client_id = message_parts[0]
                    message_type = MessageType(message_parts[1])
                    message_data = message_parts[2]

                    self.logger.info(f"{client_id = }, {message_type = }, {message_data = }")
                    response = await self._process_request(message_data)

                    await self._send_response(client_id, message_type, response)

            except zmq.ZMQError as exc:
                self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            except Exception as exc:
                self.logger.error(f"Error handling request: {exc}", exc_info=True)
            except asyncio.CancelledError:
                self.logger.warning("Request handling cancelled.")
                self.running = False

    async def _process_request(self, msg_data: bytes):
        """
        Process a client request and generate a response.

        Args:
            msg_data: the actual JSON with the request

        """
        try:
            request = json.loads(msg_data.decode())
            self.logger.info(f"Received request: {request}")

        except json.JSONDecodeError as exc:
            self.logger.error(f"Invalid JSON received: {exc}")
            return {"success": False, "error": "Invalid JSON format"}

        action = request.get("action")
        if not action:
            return {"success": False, "error": "Missing required field: action"}

        handlers: dict[str, Callable] = {
            "health": self._handle_health,
            "terminate": self._handle_terminate,
        }

        handler = handlers.get(action)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action}"}

        return await handler(request)

    async def _send_response(self, client_id: bytes, msg_type: MessageType, response: dict[str, Any]):
        """
        If the client expects a reply, send the response.

        Args:
            client_id: the client identification, part 1 of the multipart message
            msg_type: the type of the message, e.g. if reply is required
            response: a dictionary with the status and response

        """
        if msg_type == MessageType.REQUEST_WITH_REPLY:
            await self.requests_socket.send_multipart(
                [client_id, MessageType.RESPONSE.value, json.dumps(response).encode()]
            )

    async def _handle_health(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a health check request."""

        self.logger.info(f"Handle health request: {request}")

        return {"success": True, "status": "ok", "timestamp": int(time.time())}

    async def _handle_terminate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a termination request."""

        self.logger.info(f"Handle termination request: {request}")

        await self.stop()

        return {
            "success": True,
            "status": "terminating",
            "timestamp": time.time(),
        }

    async def _generate_health_response(self, request):
        """Generate health response data"""
        health_data = {
            "status": "healthy" if self.running else "unhealthy",
            "uptime": time.time() - self.stats["start_time"],
            "events_received": self.stats["events_received"],
            "events_published": self.stats["events_published"],
            "last_message_time": self.stats["last_message_time"],
            "timestamp": time.time(),
            "request_id": request.get("request_id"),
            "server_id": self.server_id,
        }

        return health_data

    async def stop(self):
        """Signal the server to stop."""
        self._shutdown_event.set()


@app.command(cls=TyperAsyncCommand)
# Usage
async def start():
    with remote_logging():
        hub = AsyncNotificationHub()
        await hub.start()


@app.command(cls=TyperAsyncCommand)
async def stop():
    with AsyncNotificationHubClient() as client:
        await client.terminate_notification_hub()


if __name__ == "__main__":
    try:
        rc = app()
    except zmq.ZMQError as exc:
        if "Address already in use" in str(exc):
            logger.error(f"The Service Registry server is already running: {exc}")
        else:
            logger.error("Couldn't start service registry server", exc_info=True)
        rc = -1

    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received for NotifyHub, terminating...")
        rc = -1

    sys.exit(rc)
