from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from typing import Callable

import zmq
import zmq.asyncio

from egse.registry import DEFAULT_RS_PUB_PORT
from egse.registry import DEFAULT_RS_REQ_PORT
from egse.registry.client import AsyncRegistryClient
from egse.system import get_host_ip
from egse.zmq_ser import get_port_number

module_module_logger_name = "async_microservice"
module_logger = logging.getLogger(module_module_logger_name)


class ZMQMicroservice:
    """
    A pure ZeroMQ-based microservice implementation.

    This service:
    1. Registers with the service registry.
       Default endpoints are "tcp://localhost:4242" for the REQ-REP, and
       "tcp://localhost:4243" for the PUB-SUB (events, notifications)
    2. Exposes ZeroMQ sockets for its functionality
    3. Can discover and call other services
    """

    def __init__(
        self,
        service_name: str,
        service_type: str,
        rep_port: int = 0,
        pub_port: int | None = None,
        registry_req_endpoint: str | None = None,
        registry_sub_endpoint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Initialize the microservice. When port numbers for rep_port and pub_port
        are set to 0, the system will automatically assign a dynamic port number
        that will be reported to the service registry.

        Args:
            service_name: Human-readable name for this service
            service_type: Type of service (for discovery)
            rep_port: Port for REP socket (service API) [default=0]
            pub_port: Optional port for PUB socket (events/notifications)
            registry_req_endpoint: ZeroMQ endpoint for registry REQ socket
            registry_sub_endpoint: ZeroMQ endpoint for registry SUB socket
            metadata: Additional service metadata
        """
        self.service_name = service_name
        self.service_type = service_type
        self.rep_port = rep_port
        self.pub_port = pub_port
        self.registry_req_endpoint = registry_req_endpoint or f"tcp://localhost:{DEFAULT_RS_REQ_PORT}"
        self.registry_sub_endpoint = registry_sub_endpoint or f"tcp://localhost:{DEFAULT_RS_PUB_PORT}"
        self.metadata = metadata or {}

        self.host_ip = get_host_ip()

        # Service ID will be set when registered
        self.service_id = None

        # ZeroMQ context
        self.context = zmq.asyncio.Context()

        # REP socket for service API
        self.rep_socket = self.context.socket(zmq.REP)
        self.rep_socket.bind(f"tcp://*:{rep_port}")

        # Determine the dynamically assigned port number
        if rep_port == 0:
            self.rep_port = get_port_number(self.rep_socket)

        # PUB socket for events/notifications (optional)
        if pub_port is not None:
            self.pub_socket = self.context.socket(zmq.PUB)
            self.pub_socket.bind(f"tcp://*:{pub_port}")
        else:
            self.pub_socket = None

        # Determine the dynamically assigned port number
        if pub_port == 0:
            self.pub_port = get_port_number(self.pub_socket)

        self.registry_client = AsyncRegistryClient(
            registry_req_endpoint=self.registry_req_endpoint, registry_sub_endpoint=self.registry_sub_endpoint
        )
        self.registry_client.connect()

        self.command_handlers = {}

        self._register_default_handlers()

        # Shutdown will be 'set' to terminate the service.
        self._shutdown = asyncio.Event()

        self._tasks = set()

    def _register_default_handlers(self):
        """Register default command handlers."""
        self.register_handler("ping", self._handle_ping)
        self.register_handler("info", self._handle_info)
        self.register_handler("health", self._handle_health)

    def register_handler(self, command: str, handler: Callable):
        """
        Register a command handler.

        Args:
            command: Command name
            handler: Async function that will handle the command
        """
        self.command_handlers[command] = handler
        module_logger.info(f"Registered handler for command: {command}")

    async def _handle_ping(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle ping command."""
        return {"status": "ok", "message": "pong", "timestamp": time.time()}

    async def _handle_info(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle info command."""
        return {
            "status": "ok",
            "service_id": self.service_id,
            "service_name": self.service_name,
            "service_type": self.service_type,
            "host": self.host_ip,
            "rep_port": self.rep_port,
            "pub_port": self.pub_port,
            "metadata": self.metadata,
        }

    async def _handle_health(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle health command."""
        return {"status": "ok", "timestamp": time.time()}

    async def start(self):
        """Start the microservice. This will:

        - register the service to the service registry
        - start the service heartbeat
        - start the service event listener
        - start the background task to handle requests
        """
        module_logger.info(f"Starting {self.service_name} ({self.service_type}) on {self.host_ip}:{self.rep_port}")

        # Register with the registry
        self.service_id = await self.registry_client.register(
            self.service_name,
            self.host_ip,
            self.rep_port,
            service_type=self.service_type,
            metadata={**self.metadata, "pub_port": self.pub_port},
        )

        if not self.service_id:
            module_logger.error("Failed to register with the service registry")
            return True

        module_logger.info(f"Registered with service ID: {self.service_id}")

        # Start heartbeat and event listener
        await self.registry_client.start_heartbeat()
        await self.registry_client.start_event_listener()

        # Start request handler
        request_task = asyncio.create_task(self._handle_requests())
        self._tasks.add(request_task)
        request_task.add_done_callback(self._tasks.discard)

        # Wait for shutdown signal
        await self._shutdown.wait()

        # Clean shutdown
        await self._cleanup()

        return False

    async def _handle_requests(self):
        """Handle incoming requests."""
        module_logger.info("Started request handler")

        try:
            while not self._shutdown.is_set():
                try:
                    # Wait for a request with timeout
                    try:
                        request_json = await asyncio.wait_for(self.rep_socket.recv_string(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue

                    # Parse the request
                    request = json.loads(request_json)
                    command = request.get("command")

                    if not command:
                        response = {"status": "error", "error": "Missing 'command' field"}
                    elif command not in self.command_handlers:
                        response = {"status": "error", "error": f"Unknown command: {command}"}
                    else:
                        # Call the handler
                        try:
                            handler = self.command_handlers[command]
                            response = await handler(request)
                        except Exception as exc:
                            module_logger.error(f"Error handling command {command}: {exc}")
                            response = {"status": "error", "error": f"Error handling command: {str(exc)}"}

                    # Send the response
                    await self.rep_socket.send_string(json.dumps(response))
                except zmq.ZMQError as exc:
                    module_logger.error(f"ZMQ error: {exc}")
                except json.JSONDecodeError:
                    module_logger.error("Invalid JSON received")
                    try:
                        await self.rep_socket.send_string(
                            json.dumps({"status": "error", "error": "Invalid JSON format"})
                        )
                    except Exception as exc:
                        module_logger.warning(f"Caught {type(exc).__name__}: {exc}")
                except Exception as exc:
                    module_logger.error(f"Error handling request: {exc}")
                    try:
                        await self.rep_socket.send_string(json.dumps({"status": "error", "error": str(exc)}))
                    except Exception as exc:
                        module_logger.warning(f"Caught {type(exc).__name__}: {exc}")
        except asyncio.CancelledError:
            module_logger.info("Request handler task cancelled")

    async def stop(self):
        """Signal the service to stop."""
        self._shutdown.set()

    async def _cleanup(self):
        """Clean up resources."""
        module_logger.info("Cleaning up resources...")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Deregister from the registry
        if self.service_id:
            await self.registry_client.deregister()
            module_logger.info(f"Deregistered service: {self.service_id}")

        # Close registry client
        await self.registry_client.close()

        # Close ZeroMQ sockets
        if hasattr(self, "rep_socket") and self.rep_socket:
            self.rep_socket.close()

        if hasattr(self, "pub_socket") and self.pub_socket:
            self.pub_socket.close()

        if hasattr(self, "context") and self.context:
            self.context.term()

        module_logger.info("Cleanup complete")

    async def publish_event(self, event_type: str, data: dict[str, Any]):
        """
        Publish an event to subscribers.

        Args:
            event_type: Type of event
            data: Event data
        """
        if not self.pub_socket:
            module_logger.warning("Cannot publish event: no PUB socket")
            return

        event = {"type": event_type, "service_id": self.service_id, "timestamp": time.time(), "data": data}

        try:
            await self.pub_socket.send_multipart([event_type.encode("utf-8"), json.dumps(event).encode("utf-8")])
            module_logger.debug(f"Published event: {event_type}")
        except Exception as exc:
            module_logger.error(f"Failed to publish event: {exc}")

    async def call_service(self, service_type: str, command: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Call another service.

        Args:
            service_type: Type of service to call
            command: Command to invoke
            data: Command parameters

        Returns:
            Response from the service
        """
        # Discover the service
        service = await self.registry_client.discover_service(service_type)

        if not service:
            raise ValueError(f"No service of type '{service_type}' found")

        # Prepare the request
        request = {"command": command, **(data or {})}

        # Create a REQ socket
        socket = self.context.socket(zmq.REQ)
        socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout

        try:
            # Connect to the service
            socket.connect(f"tcp://{service['host']}:{service['port']}")

            # Send the request
            await socket.send_string(json.dumps(request))

            # Wait for the response
            response_json = await socket.recv_string()
            return json.loads(response_json)
        finally:
            socket.close()

    async def subscribe_to_service_events(
        self, service_type: str, event_types: list[str], callback: Callable[[dict[str, Any]], None]
    ):
        """
        Subscribe to events from another service.

        Args:
            service_type: Type of service to subscribe to
            event_types: List of event types to subscribe to
            callback: Function to call with events

        Returns:
            Subscription task
        """
        # Discover the service
        service = await self.registry_client.discover_service(service_type)

        if not service:
            raise ValueError(f"No service of type '{service_type}' found")

        # Get PUB port from metadata
        pub_port = service.get("metadata", {}).get("pub_port")

        if not pub_port:
            raise ValueError("Service does not expose a PUB socket")

        # Create a SUB socket
        socket = self.context.socket(zmq.SUB)

        # Subscribe to specified event types
        for event_type in event_types:
            socket.setsockopt_string(zmq.SUBSCRIBE, event_type)

        # Connect to the service
        socket.connect(f"tcp://{service['host']}:{pub_port}")

        async def subscription_loop():
            try:
                module_logger.info(f"Subscribed to events from {service['name']} ({service_type})")

                while not self._shutdown.is_set():
                    try:
                        # Wait for an event with timeout
                        if socket.poll(timeout=1000) == 0:
                            continue

                        # Receive the event
                        event_type_bytes, event_json_bytes = await socket.recv_multipart()
                        event_type = event_type_bytes.decode("utf-8")
                        event = json.loads(event_json_bytes.decode("utf-8"))

                        # Call the callback
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(event)
                            else:
                                callback(event)
                        except Exception as exc:
                            module_logger.error(f"Error in event callback: {exc}")
                    except zmq.ZMQError as exc:
                        if exc.errno == zmq.EAGAIN:
                            # Timeout, just continue
                            continue
                        module_logger.error(f"ZMQ error in subscription: {exc}")
                    except Exception as exc:
                        module_logger.error(f"Error in subscription loop: {exc}")
                        await asyncio.sleep(1)  # Prevent tight loop on error
            except asyncio.CancelledError:
                module_logger.info(f"Subscription to {service_type} cancelled")
            finally:
                socket.close()

        # Start the subscription task
        task = asyncio.create_task(subscription_loop())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return task
