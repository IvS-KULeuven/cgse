"""
Registry Service – core service


"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import signal
import sys
import textwrap
import time
import uuid
from typing import Any
from typing import Callable

import typer
import zmq
import zmq.asyncio

from egse.logger import remote_logging
from egse.registry import DEFAULT_RS_DB_PATH
from egse.registry import DEFAULT_RS_HB_PORT
from egse.registry import DEFAULT_RS_PUB_PORT
from egse.registry import DEFAULT_RS_REQ_PORT
from egse.registry import MessageType
from egse.registry import logger
from egse.registry.backend import AsyncRegistryBackend
from egse.registry.backend import AsyncSQLiteBackend
from egse.registry.client import AsyncRegistryClient
from egse.system import TyperAsyncCommand
from egse.system import get_logging_level

app = typer.Typer(name="rs_cs")


class AsyncRegistryServer:
    """
    Asynchronous ZeroMQ-based service registry server.

    This server uses the ZeroMQ async API and asyncio for non-blocking operations.

    Args:
        req_port: Port for the service requests socket [default=4242]
        pub_port: Port for the service notifications socket [default=4243]
        hb_port: Port for receiving heartbeats [default=4244]
        backend: a registry backend, [default=AsyncSQLiteBackend]
        db_path: Path to the SQLite database file [default='service_registry.db']
        cleanup_interval: How often to clean up expired services (seconds) [default=10]
    """

    def __init__(
        self,
        req_port: int = DEFAULT_RS_REQ_PORT,
        pub_port: int = DEFAULT_RS_PUB_PORT,
        hb_port: int = DEFAULT_RS_HB_PORT,
        backend: AsyncRegistryBackend | None = None,
        db_path: str = DEFAULT_RS_DB_PATH,
        cleanup_interval: int = 10,
    ):
        self.req_port = req_port
        self.pub_port = pub_port
        self.hb_port = hb_port
        self.db_path = db_path
        self.cleanup_interval = cleanup_interval
        self.logger = logger

        self.context = None
        self.req_socket = None
        self.pub_socket = None
        self.hb_socket = None

        # Initialize the storage backend
        self.backend = backend or AsyncSQLiteBackend(db_path)

        # Running flag and event for clean shutdown
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Tasks
        self._tasks = set()

    async def setup_sockets(self):
        """Set up the communication sockets."""

        # Set ZeroMQ to use asyncio
        self.context = zmq.asyncio.Context()

        # Socket to handle requests and commands
        req_rep_endpoint = f"tcp://*:{self.req_port}"
        self.req_socket = self.context.socket(zmq.ROUTER)
        self.req_socket.bind(req_rep_endpoint)
        self.logger.info(f"Binding request socket to {req_rep_endpoint}")

        # Socket to publish service events
        pub_endpoint = f"tcp://*:{self.pub_port}"
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind(pub_endpoint)
        self.logger.info(f"Binding publish socket to {pub_endpoint}")

        # Socket to handle heartbeats
        hb_endpoint = f"tcp://*:{self.hb_port}"
        self.hb_socket = self.context.socket(zmq.REP)
        self.hb_socket.bind(hb_endpoint)
        self.logger.info(f"Binding heartbeat socket to {hb_endpoint}")

    async def initialize_backend(self):
        """Initialize the storage backend."""
        await self.backend.initialize()

    async def start(self):
        """Start the registry server."""

        multiprocessing.current_process().name = "rs_cs"

        if self._running:
            return

        await self.setup_sockets()

        await self.initialize_backend()

        self._running = True
        self.logger.info(
            f"Async registry server started on ports {self.req_port} (ROUTER-DEALER), {self.pub_port} (PUB), "
            f"and {self.hb_port} (Heartbeat)"
        )

        # Start the cleanup task
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._tasks.discard)

        # Start the request handler task
        request_task = asyncio.create_task(self._handle_requests())
        self._tasks.add(request_task)
        request_task.add_done_callback(self._tasks.discard)

        # Start the heartbeat handler task
        heartbeats_task = asyncio.create_task(self._handle_heartbeats())
        self._tasks.add(heartbeats_task)
        heartbeats_task.add_done_callback(self._tasks.discard)

        # Wait for shutdown
        await self._shutdown_event.wait()

        # Clean shutdown
        await self._shutdown()

    async def _shutdown(self):
        """Perform clean shutdown."""
        self._running = False
        self.logger.info("Shutting down async registry server...")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete (with timeout)
        if self._tasks:
            try:
                await asyncio.wait(self._tasks, timeout=2.0)
            except asyncio.CancelledError:
                pass

        # Close database
        await self.backend.close()

        # Close ZeroMQ sockets
        self.req_socket.close()
        self.pub_socket.close()
        self.hb_socket.close()

        # Close context
        self.context.term()

        self.logger.info("Async registry server shutdown complete")

    def stop(self):
        """Signal the server to stop."""
        self._shutdown_event.set()

    async def _cleanup_loop(self):
        """Background task that periodically cleans up expired services."""
        self.logger.info(f"Started cleanup task with interval {self.cleanup_interval}s")

        try:
            while self._running:
                try:
                    # Clean up expired services
                    expired_ids = await self.backend.clean_expired_services()

                    # Publish de-registration events for expired services
                    for service_id in expired_ids:
                        await self._publish_event("expire", {"service_id": service_id})
                except Exception as exc:
                    self.logger.error(f"Error in cleanup task: {exc}")

                # Sleep for the specified interval
                await asyncio.sleep(self.cleanup_interval)
        except asyncio.CancelledError:
            self.logger.info("Cleanup task cancelled")

    async def _handle_requests(self):
        """Task that handles incoming requests."""
        self.logger.info("Started request handler task")

        try:
            message_parts = None
            while self._running:
                try:
                    # Wait for a request with timeout to allow checking if still running
                    try:
                        # self.logger.info("Waiting for a request with 1s timeout...")
                        message_parts = await asyncio.wait_for(self.req_socket.recv_multipart(), timeout=1.0)
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
                    self.logger.debug(f"{message_parts=}")
        except asyncio.CancelledError:
            self.logger.warning("Request handler task cancelled")

    async def _publish_event(self, event_type: str, data: dict[str, Any]):
        """
        Publish an event to subscribers.

        Args:
            event_type: Type of event (register, deregister, expire, etc.)
            data: Event payload
        """
        event = {"type": event_type, "timestamp": int(time.time()), "data": data}

        try:
            # Prefix with event type for subscribers that filter by type
            await self.pub_socket.send_multipart([event_type.encode("utf-8"), json.dumps(event).encode("utf-8")])
            self.logger.debug(f"Published {event_type} event: {data}")
        except Exception as exc:
            self.logger.error(f"Failed to publish event: {exc}")

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
            "register": self._handle_register,
            "deregister": self._handle_deregister,
            "renew": self._handle_renew,
            "info": self._handle_info,
            "get": self._handle_get,
            "list": self._handle_list,
            "discover": self._handle_discover,
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
            await self.req_socket.send_multipart([client_id, MessageType.RESPONSE.value, json.dumps(response).encode()])

    async def _handle_register(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a service registration request."""
        self.logger.info(f"Handle registration request: {request}")

        if "service_info" not in request:
            return {"success": False, "error": "Missing required field: service_info"}

        service_info = request["service_info"]

        # Validate required fields
        required_fields = ["name", "host", "port"]
        for field in required_fields:
            if field not in service_info:
                return {"success": False, "error": f"Missing required field in service_info: {field}"}

        # Generate ID if not provided
        service_id = service_info.get("id")
        if not service_id:
            service_id = f"{service_info['name'].lower().replace(' ', '-')}-{uuid.uuid4()}"
            service_info["id"] = service_id

        # Get TTL
        ttl = request.get("ttl", 30)

        # Register the service
        success = await self.backend.register(service_id, service_info, ttl)

        if success:
            # Publish registration event
            await self._publish_event("register", {"service_id": service_id, "service_info": service_info})

            return {"success": True, "service_id": service_id, "message": "Service registered successfully"}

        return {"success": False, "error": "Failed to register service"}

    async def _handle_deregister(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a service de-registration request."""
        service_id = request.get("service_id")

        self.logger.info(f"Handle de-registration request: {request}")

        if not service_id:
            return {"success": False, "error": "Missing required field: service_id"}

        # Get service details before de-registering (for event)
        service_info = await self.backend.get_service(service_id)

        # Deregister the service
        success = await self.backend.deregister(service_id)

        if success:
            # Publish de-registration event
            await self._publish_event("deregister", {"service_id": service_id, "service_info": service_info})

            return {"success": True, "message": "Service deregistered successfully"}

        return {"success": False, "error": "Service not found or could not be deregistered"}

    async def _handle_renew(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a service heartbeat request."""
        service_id = request.get("service_id")

        self.logger.info(f"Handle renew request: {request}")

        if not service_id:
            return {"success": False, "error": "Missing required field: service_id"}

        # Renew the service
        success = await self.backend.renew(service_id)

        if success:
            return {"success": True, "message": "Service renewed successfully"}

        return {"success": False, "error": "Service not found or could not be renewed"}

    async def _handle_heartbeats(self):
        """Task that handles heartbeat messages."""
        self.logger.info("Started heartbeats handler task")

        try:
            while self._running:
                try:
                    # Receive heartbeat (non-blocking with timeout)
                    message_json = await asyncio.wait_for(self.hb_socket.recv_string(), timeout=1.0)

                    # Parse the request
                    request = json.loads(message_json)
                    self.logger.info(f"Received heartbeat request: {request}")

                    response = await self._handle_renew(request)

                    # Send the response
                    await self.hb_socket.send_string(json.dumps(response))

                except asyncio.TimeoutError:
                    # self.logger.debug("waiting for heartbeat...")
                    continue

                except Exception as exc:
                    self.logger.error(f"Error handling heartbeat request: {exc}")
                    try:
                        await self.hb_socket.send_string(json.dumps({"success": False, "error": str(exc)}))
                    except Exception:
                        pass

        except asyncio.CancelledError:
            self.logger.info("Heartbeats handler task cancelled")

    async def _handle_get(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a request to get a specific service."""

        service_id = request.get("service_id")

        self.logger.info(f"Handle get request: {request}")

        if not service_id:
            return {"success": False, "error": "Missing required field: service_id"}

        # Get the service
        service = await self.backend.get_service(service_id)

        if service:
            return {"success": True, "service": service}

        return {"success": False, "error": "Service not found"}

    async def _handle_list(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a request to list services."""
        service_type = request.get("service_type")

        self.logger.info(f"Handle list request: {request}")

        # List the services
        services = await self.backend.list_services(service_type)

        return {
            "success": True,
            "services": services,
        }

    async def _handle_discover(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a service discovery request."""
        service_type = request.get("service_type")

        self.logger.info(f"Handle discover request for service type: {service_type}")

        if not service_type:
            return {"success": False, "error": "Missing required field: service_type"}

        # Discover a service
        service = await self.backend.discover_service(service_type)

        if service:
            return {"success": True, "service": service}

        return {"success": False, "error": f"No healthy service of type {service_type} found"}

    async def _handle_info(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle the info request and send information about the registry server."""

        self.logger.info(f"Handle info request: {request}")

        # List the services
        services = await self.backend.list_services()

        return {
            "success": True,
            "status": "ok",
            "req_port": self.req_port,
            "pub_port": self.pub_port,
            "services": services,
        }

    async def _handle_health(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a health check request."""

        self.logger.info(f"Handle health request: {request}")

        return {"success": True, "status": "ok", "timestamp": int(time.time())}

    async def _handle_terminate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a termination request."""

        self.logger.info(f"Handle termination request: {request}")

        self.stop()

        return {
            "success": True,
            "status": "terminating",
            "timestamp": time.time(),
        }


@app.command(cls=TyperAsyncCommand)
async def start(
    req_port: int = DEFAULT_RS_REQ_PORT,
    pub_port: int = DEFAULT_RS_PUB_PORT,
    hb_port: int = DEFAULT_RS_HB_PORT,
    db_path: str = DEFAULT_RS_DB_PATH,
    cleanup_interval: int = 10,
    log_level: str = "WARNING",
):
    """Run the registry server with signal handling."""

    logging.basicConfig(
        level=get_logging_level(log_level),
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-12s %(lineno)5d:%(module)-20s %(message)s",
    )
    logging.getLogger("aiosqlite").setLevel(logging.INFO)

    with remote_logging():
        server = AsyncRegistryServer(
            req_port=req_port,
            pub_port=pub_port,
            hb_port=hb_port,
            db_path=db_path,
            cleanup_interval=cleanup_interval,
        )

        # Set up signal handlers
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(handle_signal(server)))

        # Start server
        await server.start()


async def handle_signal(server):
    """Handle termination signals."""
    logger.info("Received termination signal")
    server.stop()


@app.command(cls=TyperAsyncCommand)
async def status(
    req_port: int = DEFAULT_RS_REQ_PORT,
    pub_port: int = DEFAULT_RS_PUB_PORT,
    hb_port: int = DEFAULT_RS_HB_PORT,
    host: str = "localhost",
):
    with AsyncRegistryClient(
        registry_req_endpoint=f"tcp://{host}:{req_port}",
        registry_sub_endpoint=f"tcp://{host}:{pub_port}",
        registry_hb_endpoint=f"tcp://{host}:{hb_port}",
    ) as client:
        response = await client.server_status()

    if response["success"]:
        status_report = textwrap.dedent(
            f"""\
            Registry Service:
                Status: {response["status"]}
                Requests port: {response["req_port"]}
                Notifications port: {response["pub_port"]}
                Registrations: {", ".join([f"({x['name']}, {x['health']})" for x in response["services"]])}\
            """
        )
    else:
        status_report = "Registry Service: not active"

    print(status_report)


@app.command(cls=TyperAsyncCommand)
async def stop(
    req_port: int = DEFAULT_RS_REQ_PORT,
    pub_port: int = DEFAULT_RS_PUB_PORT,
    hb_port: int = DEFAULT_RS_HB_PORT,
    host: str = "localhost",
):
    with AsyncRegistryClient(
        registry_req_endpoint=f"tcp://{host}:{req_port}",
        registry_sub_endpoint=f"tcp://{host}:{pub_port}",
        registry_hb_endpoint=f"tcp://{host}:{hb_port}",
    ) as client:
        response = await client.terminate_registry_server()

    if response:
        logger.info("Service registry server terminated.")


if __name__ == "__main__":
    try:
        rc = app()
    except zmq.ZMQError as exc:
        if "Address already in use" in str(exc):
            logger.error(f"The Service Registry server is already running: {exc}")
        else:
            logger.error("Couldn't start service registry server", exc_info=True)
        rc = -1

    sys.exit(rc)
