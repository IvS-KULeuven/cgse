from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any
from typing import Callable
from typing import Coroutine
from typing import Union

import zmq
import zmq.asyncio

from egse.log import logger
from egse.registry import DEFAULT_RS_HB_PORT
from egse.registry import DEFAULT_RS_PUB_PORT
from egse.registry import DEFAULT_RS_REQ_PORT
from egse.registry import MessageType
from egse.system import do_every

REQUEST_TIMEOUT = 0.5
"""time to wait for a request-reply [seconds]. For responsive message handling."""
EVENT_POLL_TIMEOUT = 0.5
"""time to wait for while listening for events [seconds]."""
TASK_COMPLETION_TIMEOUT = 5.0
"""time to wait for Tasks to complete [seconds]."""
HEALTH_CHECK_TIMEOUT = 2.0
"""Health checks shouldn't take too long. Recommended: 1-5s."""
HEART_BEAT_TIMEOUT = 1.0
"""Heart beat should fail fast to detect network issues. Recommended: 0.5-2s."""
HEART_BEAT_RECONNECT = 1.0
"""Time to wait between a disconnect an a connect to the heartbeat socket."""
THREAD_JOIN_TIMEOUT = 10.0
"""Joining threads should be longer, but the key is balancing graceful cleanup with reasonable shutdown times."""
PROCESS_SHUTDOWN_TIMEOUT = 10.0
"""Waiting for a process shutdown confirmation message."""

class RegistryClient:
    """
    Synchronous client for the service registry.
    """

    def __init__(
        self,
        registry_req_endpoint: str = None,
        registry_sub_endpoint: str = None,
        registry_hb_endpoint: str = None,
        timeout: float = REQUEST_TIMEOUT,
        client_id: str = "registry-client",
    ):
        """
        Initialize the async registry client.

        Args:
            registry_req_endpoint: ZeroMQ endpoint for REQ-REP socket, defaults to DEFAULT_RS_REQ_PORT on localhost.
            registry_sub_endpoint: ZeroMQ endpoint for SUB socket, defaults to DEFAULT_RS_PUB_PORT on localhost.
            registry_hb_endpoint: ZeroMQ endpoint for Heartbeat socket, defaults to DEFAULT_RS_HB_PORT on localhost.
            timeout: Timeout for requests in seconds, defaults to 0.5s.
            client_id: client identification, default='registry-client'
        """
        self.registry_req_endpoint = registry_req_endpoint or f"tcp://localhost:{DEFAULT_RS_REQ_PORT}"
        self.registry_sub_endpoint = registry_sub_endpoint or f"tcp://localhost:{DEFAULT_RS_PUB_PORT}"
        self.registry_hb_endpoint = registry_hb_endpoint or f"tcp://localhost:{DEFAULT_RS_HB_PORT}"

        self.timeout = timeout
        self.timeout_ms = int(timeout * 1000)
        self.logger = logger

        # Service state
        self._service_id = None
        self._service_info = None
        self._ttl = None

        self._hb_stop_event = None
        self._hb_thread: threading.Thread | None = None

        self._client_id = f"{client_id}-{uuid.uuid4()}".encode()

        self.context: zmq.Context = zmq.Context.instance()

        self.req_socket: zmq.Socket | None = None
        self.sub_socket: zmq.Socket | None = None
        self.hb_socket: zmq.Socket | None = None

        self.poller = zmq.Poller()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        # self.logger.debug("Connecting to service registry...")

        # REQ socket for request-reply pattern
        self.req_socket = self.context.socket(zmq.DEALER)
        self.req_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
        self.req_socket.setsockopt(zmq.IDENTITY, self._client_id)
        self.req_socket.connect(self.registry_req_endpoint)

        # SUB socket for receiving events
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(self.registry_sub_endpoint)
        # Default to receiving all events
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self.poller.register(self.req_socket, zmq.POLLIN)
        self.poller.register(self.sub_socket, zmq.POLLIN)

    def _connect_hb_socket(self):
        self.hb_socket = self.context.socket(zmq.REQ)
        self.hb_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
        self.hb_socket.connect(self.registry_hb_endpoint)

    def disconnect(self):
        # self.logger.debug("Disconnecting from service registry...")

        if self.req_socket:
            self.poller.unregister(self.req_socket)
            self.req_socket.close(linger=0)
        self.req_socket = None

        if self.sub_socket:
            self.poller.unregister(self.sub_socket)
            self.sub_socket.close(linger=0)
        self.sub_socket = None

    def _disconnect_hb_socket(self):
        if self.hb_socket:
            self.hb_socket.setsockopt(zmq.LINGER, 0)
            self.hb_socket.close()
        self.hb_socket = None

    def _send_request(self, msg_type: MessageType, request: dict[str, Any], timeout: float = None) -> dict[str, Any]:
        """
        Send a request to the registry and get the response.

        Args:
            msg_type: the type of message and reply
            request: The request to send
            timeout: The number of seconds to wait, if None, instance variable is used.

        Returns:
            The response from the registry.
        """
        timeout_ms = int(timeout * 1000) if timeout else self.timeout_ms

        try:
            self.logger.debug(f"Sending request: {request}")
            self.req_socket.send_multipart([msg_type.value, json.dumps(request).encode()])

            if msg_type == MessageType.REQUEST_NO_REPLY:
                return {"success": True}

            if self.poller.poll(timeout=timeout_ms):
                message_parts = self.req_socket.recv_multipart()

                if len(message_parts) >= 2:
                    message_type = MessageType(message_parts[0])
                    message_data = message_parts[1]

                    if message_type == MessageType.RESPONSE:
                        response = json.loads(message_data)
                        self.logger.debug(f"Received response: {response}")
                        return response
                    else:
                        return {
                            "success": False,
                            "error": f"unexpected MessageType received: {message_type.name}, {message_data = }",
                        }
                else:
                    return {
                        "success": False,
                        "error": f"not enough parts received: {len(message_parts)}",
                        "data": message_parts,
                    }
            else:
                self.logger.error(f"Request timed out after {self.timeout:.2f}s")
                return {"success": False, "error": "Request timed out"}
        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    def _send_heartbeat(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Send a heartbeat to the registry and get the response.

        Args:
            request: The request to send

        Returns:
            The response from the registry.
        """

        try:
            self.logger.debug(f"Sending heartbeat request: {request}")
            self.hb_socket.send_string(json.dumps(request))

            ready_sockets, _, _ = zmq.select([self.hb_socket], [], [], timeout=HEART_BEAT_TIMEOUT)

            if ready_sockets:
                response_json = self.hb_socket.recv_string()
                response = json.loads(response_json)
                self.logger.debug(f"Received response: {response}")
                return response
            else:
                self.logger.error(f"Request timed out after {HEART_BEAT_TIMEOUT:.2f}s")
                self._disconnect_hb_socket()
                time.sleep(HEART_BEAT_RECONNECT)
                self._connect_hb_socket()
                return {"success": False, "error": "Request timed out"}

        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    def register(
        self,
        name: str,
        host: str,
        port: int,
        service_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        ttl: int = 30,
    ) -> str | None:
        """
        Register this service with the registry.

        Args:
            name: Service name
            host: Service host/IP
            port: Service port
            service_type: Service type (for discovery)
            metadata: Additional service metadata
            ttl: Time-to-live in seconds

        Returns:
            The service ID if successful, None otherwise
        """
        # Prepare service info
        service_info: dict[str, str | int | dict | list] = {"name": name, "host": host, "port": port}

        # Add optional fields
        if service_type:
            service_info["type"] = service_type

        if metadata:
            service_info["metadata"] = metadata

        # Prepare tags for easier discovery
        tags = []
        if service_type:
            tags.append(service_type)
        service_info["tags"] = tags

        # Send registration request
        request = {"action": "register", "service_info": service_info, "ttl": ttl}

        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            # Store service information for later use
            self._service_id = response.get("service_id")
            self._service_info = service_info
            self._ttl = ttl

            self.logger.info(f"Service registered with ID: {self._service_id}")
            return self._service_id
        else:
            self.logger.error(f"Failed to register service: {response.get('error')}")
            return None

    def deregister(self, service_id: str = None) -> bool:
        """
        Deregister this service from the registry.

        Returns:
            True if successful, False otherwise.
        """

        service_id = service_id or self._service_id

        if not service_id:
            self.logger.warning("Cannot deregister: no service is registered")
            return False

        request = {"action": "deregister", "service_id": service_id}

        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            self.logger.info(f"Service deregistered: {service_id}")
            self._service_id = None
            self._service_info = None
            self._ttl = None
            return True
        else:
            self.logger.error(f"Failed to deregister service: {response.get('error')}")
            return False

    def discover_service(self, service_type: str, use_cache: bool = False) -> dict[str, Any] | None:
        """
        Discover a service of the specified type. The service is guaranteed to be healthy at the time of discovery.

        The returned information contains:

        - name: the name of the service
        - host: the ip address or hostname of the service
        - port: the port number for requests to the microservice

        Args:
            service_type: Type of service to discover
            use_cache: Whether to use cached service information

        Returns:
            Service information if found, None otherwise
        """
        # Try to use cache first if enabled
        if use_cache:
            self.logger.info("Cache not yet implemented.")

        request = {"action": "discover", "service_type": service_type}

        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        # self.logger.debug(f"{response = }")

        if response.get("success"):
            service = response.get("service")
            return service
        else:
            self.logger.warning(f"Service discovery failed: {response.get('error')}")
            return None

    def get_service(self, service_id: str, use_cache: bool = True) -> dict[str, Any] | None:
        """
        Get information about a specific service.

        Args:
            service_id: ID of the service to get
            use_cache: Whether to use cached service information

        Returns:
            Service information if found, None otherwise.
        """

        request = {"action": "get", "service_id": service_id}

        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            service = response.get("service")
            return service
        else:
            self.logger.warning(f"Get service failed: {response.get('error')}")
            return None

    def list_services(self, service_type: str | None = None) -> list[dict[str, Any]]:
        """
        List all registered services, optionally filtered by type.

        Args:
            service_type: Type of services to list

        Returns:
            List of service information.
        """
        request = {"action": "list", "service_type": service_type}

        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            services = response.get("services", [])
            return services
        else:
            self.logger.warning(f"List services failed: {response.get('error')}")
            return []

    def get_endpoint(self, service_type) -> str | None:
        """Returns the endpoint for the given service type or None if the service_type is not registered."""
        service = self.discover_service(service_type)

        if service:
            protocol = service.get("protocol", "tcp")
            hostname = service["host"]
            port = service["port"]

            return f"{protocol}://{hostname}:{port}"
        else:
            return None

    def health_check(self) -> bool:
        """
        Check if the registry server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        request = {"action": "health"}

        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request, timeout=HEALTH_CHECK_TIMEOUT)
        return response.get("success", False)

    def terminate_registry_server(self) -> bool:
        """
        Send a terminate request to the service registry server. Returns True when successful.
        """
        request = {"action": "terminate"}
        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request, timeout=PROCESS_SHUTDOWN_TIMEOUT)
        return response.get("success", False)

    def server_status(self) -> dict[str, Any]:
        """
        Requests the status information from the service registry.
        """
        request = {
            "action": "info",
        }
        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request)
        return response

    def start_heartbeat(self, interval: int | None = None) -> None:
        if not self._service_id:
            self.logger.warning("Cannot start heartbeat: no service is registered")
            return None

        # If interval not specified, use 1/3 of TTL
        if interval is None:
            interval = max(1, self._ttl // 3)

        def send_heartbeat():
            try:
                request = {"action": "renew", "service_id": self._service_id}

                response = self._send_heartbeat(request)

                if not response.get("success"):
                    self.logger.warning(f"Heartbeat failed: {response.get('error')}")

                    # Do a health check
                    if not self.health_check():
                        self.logger.warning("ServiceRegistry not responding.")
                        return

                else:
                    self.logger.debug(response.get("message"))

            except Exception as exc:
                self.logger.error(f"Error sending heartbeat: {exc}")

        self._hb_stop_event = threading.Event()
        self._hb_thread = threading.Thread(
            target=do_every,
            args=(interval, send_heartbeat),
            kwargs={
                "stop_event": self._hb_stop_event,
                "setup_func": self._connect_hb_socket,
                "teardown_func": self._disconnect_hb_socket,
            },
        )
        self._hb_thread.daemon = True
        self._hb_thread.start()
        return None

    def stop_heartbeat(self) -> None:
        self._hb_stop_event.set()
        if self._hb_thread.is_alive():
            self._hb_thread.join(timeout=THREAD_JOIN_TIMEOUT)

    def close(self) -> None:
        """Clean up resources."""
        try:
            if hasattr(self, "req_socket") and self.req_socket:
                self.req_socket.close()

            if hasattr(self, "sub_socket") and self.sub_socket:
                self.sub_socket.close()

            if hasattr(self, "context") and self.context:
                self.context.term()
        except Exception as exc:
            self.logger.error(f"Error during cleanup: {exc}")


class AsyncRegistryClient:
    """
    Asynchronous client for interacting with the ZeroMQ-based service registry.

    This class uses asyncio and the ZeroMQ asyncio API for non-blocking operations.
    """

    def __init__(
        self,
        registry_req_endpoint: str = None,
        registry_sub_endpoint: str = None,
        registry_hb_endpoint: str = None,
        timeout: float = REQUEST_TIMEOUT,
        client_id: str = "registry-client",
    ):
        """
        Initialize the async registry client.

        Args:
            registry_req_endpoint: ZeroMQ endpoint for REQ-REP socket, defaults to DEFAULT_RS_REQ_PORT on localhost.
            registry_sub_endpoint: ZeroMQ endpoint for SUB socket, defaults to DEFAULT_RS_PUB_PORT on localhost.
            registry_hb_endpoint: ZeroMQ endpoint for heartbeat socket, defaults to DEFAULT_RS_HB_PORT on localhost.
            timeout: Timeout for requests in seconds, defaults to 5000.
            client_id: client identification, default='registry-client'
        """
        self.registry_req_endpoint = registry_req_endpoint or f"tcp://localhost:{DEFAULT_RS_REQ_PORT}"
        self.registry_sub_endpoint = registry_sub_endpoint or f"tcp://localhost:{DEFAULT_RS_PUB_PORT}"
        self.registry_hb_endpoint = registry_hb_endpoint or f"tcp://localhost:{DEFAULT_RS_HB_PORT}"

        self.timeout = timeout
        self.timeout_ms = int(timeout * 1000)
        self.logger = logging.getLogger("egse.registry.client")

        # Service state
        self._service_id = None
        self._service_info = None
        self._ttl = None

        self._client_id = f"{client_id}-{uuid.uuid4()}".encode()

        self.context = zmq.asyncio.Context.instance()

        self._running = False
        self._tasks = set()
        self._heartbeat_task = None
        self._event_listener_task = None

        self._event_handlers = {}

        # Service cache (for discovery)
        self._service_cache = {}
        self._service_cache_lock = None

        self.req_socket: zmq.asyncio.Socket | None = None
        self.sub_socket: zmq.asyncio.Socket | None = None
        self.hb_socket: zmq.asyncio.Socket | None = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        self.logger.debug("Connecting to service registry...")

        # REQ socket for request-reply pattern
        self.req_socket = self.context.socket(zmq.DEALER)
        self.req_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
        self.req_socket.setsockopt(zmq.IDENTITY, self._client_id)
        self.req_socket.connect(self.registry_req_endpoint)

        # SUB socket for receiving events
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(self.registry_sub_endpoint)
        # Default to receiving all events
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")

        self._connect_hb_socket()

    def _connect_hb_socket(self):
        self.hb_socket = self.context.socket(zmq.REQ)
        self.hb_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
        self.hb_socket.connect(self.registry_hb_endpoint)

    def disconnect(self):
        self.logger.debug("Disconnecting from service registry...")

        if self.req_socket:
            self.req_socket.close(linger=0)
        self.req_socket = None

        if self.sub_socket:
            self.sub_socket.close(linger=0)
        self.sub_socket = None

        self._disconnect_hb_socket()

    def _disconnect_hb_socket(self):
        if self.hb_socket:
            self.hb_socket.close(linger=0)
        self.hb_socket = None

    def _get_service_cache_lock(self):
        if self._service_cache_lock is None:
            self._service_cache_lock = asyncio.Lock()
        return self._service_cache_lock

    async def _send_request(
        self, msg_type: MessageType, request: dict[str, Any], timeout: float = None
    ) -> dict[str, Any]:
        """
        Send a request to the registry and get the response.

        Args:
            msg_type: the type of message and reply
            request: The request to send to the service registry server.
            timeout: The number of seconds to wait, if None, instance variable is used.

        Returns:
            The response from the registry as a dictionary.
        """
        self.logger.debug(f"Sending request: {request}")

        timeout = timeout or self.timeout
        try:
            await self.req_socket.send_multipart([msg_type.value, json.dumps(request).encode()])

            try:
                message_parts = await asyncio.wait_for(self.req_socket.recv_multipart(), timeout=timeout)

                if len(message_parts) >= 2:
                    message_type = MessageType(message_parts[0])
                    message_data = message_parts[1]

                    if message_type == MessageType.RESPONSE:
                        response = json.loads(message_data)
                        self.logger.debug(f"Received response: {response}")
                        return response
                    else:
                        return {
                            "success": False,
                            "error": f"unexpected MessageType received: {message_type.name}, {message_data = }",
                        }
                else:
                    return {
                        "success": False,
                        "error": f"not enough parts received: {len(message_parts)}",
                        "data": message_parts,
                    }
            except asyncio.TimeoutError:
                self.logger.error(f"Request timed out after {timeout:.2f}s")
                return {"success": False, "error": "Request timed out"}
        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def _send_heartbeat(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Send a heartbreak request to the registry and get the response.

        Args:
            request: The request to send to the service registry server.

        Returns:
            The response from the registry as a dictionary.
        """

        try:
            self.logger.debug(f"Sending heartbeat request: {request}")
            await self.hb_socket.send_string(json.dumps(request))

            try:
                response_json = await asyncio.wait_for(self.hb_socket.recv_string(), timeout=HEART_BEAT_TIMEOUT)
                response = json.loads(response_json)
                self.logger.debug(f"Received heartbeat response: {response = }")
                return response
            except asyncio.TimeoutError:
                self.logger.error(f"Heartbeat request timed out after {HEART_BEAT_TIMEOUT:.2f}s")
                # Reset the socket to avoid invalid state
                self.hb_socket.close()
                self.hb_socket = self.context.socket(zmq.REQ)
                self.hb_socket.connect(self.registry_req_endpoint)
                return {"success": False, "error": "Heartbeat request timed out"}
        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending heartbeat request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}

    async def register(
        self,
        name: str,
        host: str,
        port: int,
        service_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        ttl: int = 30,
    ) -> str | None:
        """
        Register this service with the registry.

        Args:
            name: Service name
            host: Service host/IP
            port: Service port
            service_type: Service type (for discovery)
            metadata: Additional service metadata
            ttl: Time-to-live in seconds

        Returns:
            The service ID if successful, None otherwise
        """
        # Prepare service info
        service_info: dict[str, Any] = {"name": name, "host": host, "port": port}

        # Add optional fields
        if service_type:
            service_info["type"] = service_type

        if metadata:
            service_info["metadata"] = metadata

        # Prepare tags for easier discovery
        tags = []
        if service_type:
            tags.append(service_type)
        service_info["tags"] = tags

        # Send registration request
        request = {"action": "register", "service_info": service_info, "ttl": ttl}

        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            # Store service information for later use
            self._service_id = response.get("service_id")
            self._service_info = service_info
            self._ttl = ttl

            self.logger.info(f"Service registered with ID: {self._service_id}")
            return self._service_id
        else:
            self.logger.error(f"Failed to register service: {response.get('error')}")
            return None

    async def deregister(self, service_id: str = None) -> bool:
        """
        Deregister this service or the service with service_id from the registry.

        When you register and deregister with the same client instance, you don't have to provide
        the service_id.

        Args:
            service_id: the service identifier that was previously handed out by the ServiceRegistry after
                registration. If not provided, the service_id that was saved when registering is used.

        Returns:
            True if successful, False otherwise
        """

        service_id = service_id or self._service_id

        if not service_id:
            self.logger.warning("Cannot deregister: no service is registered")
            return False

        request = {"action": "deregister", "service_id": service_id}

        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            self.logger.info(f"Service deregistered: {service_id}")
            self._service_id = None
            self._service_info = None
            self._ttl = None
            return True
        else:
            self.logger.error(f"Failed to deregister service: {response.get('error')}")
            return False

    async def start_heartbeat(self, interval: int | None = None) -> asyncio.Task | None:
        """
        Start sending heartbeats to the registry.

        Args:
            interval: Heartbeat interval in seconds (default: 1/3 of TTL)

        Returns:
            The heartbeat task
        """
        if not self._service_id:
            self.logger.warning("Cannot start heartbeat: no service is registered")
            return None

        # Cancel existing heartbeat task if present
        await self.stop_heartbeat()

        # If interval not specified, use 1/3 of TTL
        if interval is None:
            interval = max(1, self._ttl // 3)

        self._running = True

        async def heartbeat_loop():
            try:
                while self._running and self._service_id:
                    try:
                        request = {"action": "renew", "service_id": self._service_id}

                        response = await self._send_heartbeat(request)

                        if not response.get("success"):
                            self.logger.warning(f"Heartbeat failed: {response.get('error')}")
                        else:
                            self.logger.info(response.get("message"))
                    except Exception as exc:
                        self.logger.error(f"Error in heartbeat loop: {exc}", exc_info=True)

                    # Sleep until next heartbeat
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                self.logger.info("Heartbeat task cancelled")

        # Start the heartbeat task
        self._heartbeat_task = task = asyncio.create_task(heartbeat_loop())
        self._tasks.add(task)
        task.add_done_callback(lambda t: self._tasks.discard(t))

        self.logger.info(f"Started heartbeat task with interval {interval}s")
        return task

    async def stop_heartbeat(self) -> None:
        """Stop the running heartbeat task."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._tasks.discard(self._heartbeat_task)
            self._heartbeat_task = None
            self.logger.info("Stopped heartbeat task")
        else:
            self.logger.info("Couldn't stop heartbeat, heartbeat_task is None")

    async def stop_event_listener(self) -> None:
        """Stop the running event listener task."""
        if self._event_listener_task is not None:
            self._event_listener_task.cancel()
            try:
                await self._event_listener_task
            except asyncio.CancelledError:
                pass
            self._tasks.discard(self._event_listener_task)
            self._event_listener_task = None
            self.logger.info("Stopped event listener task")
        else:
            self.logger.info("Couldn't stop event_listener, event_listener_task is None")

    async def stop_all_tasks(self) -> None:
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete (with timeout)
        if self._tasks:
            try:
                await asyncio.wait(self._tasks, timeout=TASK_COMPLETION_TIMEOUT)
            except asyncio.CancelledError:
                pass

        self._tasks.clear()
        self.logger.info("Stopped all background tasks")

    def on_event(self, event_type: str, handler: Callable[[dict[str, Any]], Union[None, Coroutine]]) -> None:
        """
        Register a handler for a specific event type.

        Args:
            event_type: Type of event to handle (register, deregister, expire)
            handler: Function or coroutine to call with event data
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []

            # Subscribe to this specific event type
            self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, event_type)

        self._event_handlers[event_type].append(handler)
        self.logger.debug(f"Registered handler for {event_type} events")

    async def start_event_listener(self) -> asyncio.Task:
        """
        Start listening for registry events.

        Returns:
            The event listener task
        """
        # Cancel existing event listener task if present
        await self.stop_event_listener()

        self._running = True

        async def subscription_loop():
            try:
                while self._running:
                    try:
                        # Use a timeout to allow for clean shutdown
                        try:
                            message = await asyncio.wait_for(
                                self.sub_socket.recv_multipart(), timeout=EVENT_POLL_TIMEOUT
                            )
                        except asyncio.TimeoutError:
                            continue

                        # Parse the message
                        event_type_bytes, event_json_bytes = message
                        event_type = event_type_bytes.decode("utf-8")
                        event = json.loads(event_json_bytes.decode("utf-8"))

                        self.logger.debug(f"Received event: {event_type}")

                        # Update service cache based on events
                        await self._update_cache_from_event(event_type, event)

                        # Call registered handlers
                        handlers = self._event_handlers.get(event_type, [])
                        for handler in handlers:
                            try:
                                # Check if handler is a coroutine function
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(event["data"])
                                else:
                                    handler(event["data"])
                            except Exception as exc:
                                self.logger.error(f"Error in event handler: {exc}")
                    except zmq.ZMQError as exc:
                        self.logger.error(f"ZMQ error in event listener: {exc}")
                    except Exception as exc:
                        self.logger.error(f"Error in event listener: {exc}")
                        await asyncio.sleep(1)  # Prevent tight loop on error
            except asyncio.CancelledError:
                self.logger.info("Event listener task cancelled")

        # Start the subscription task
        self._event_listener_task = task = asyncio.create_task(subscription_loop())
        self._tasks.add(task)
        task.add_done_callback(lambda t: self._tasks.discard(t))

        self.logger.info("Started event listener task")
        return task

    async def _update_cache_from_event(self, event_type: str, event: dict[str, Any]) -> None:
        """
        Update the service cache based on registry events.

        Args:
            event_type: Type of the event.
            event: Event data
        """
        async with self._get_service_cache_lock():
            data = event.get("data", {})
            service_id = data.get("service_id")

            if not service_id:
                return

            if event_type == "register":
                service_info = data.get("service_info", {})
                if service_info:
                    self._service_cache[service_id] = service_info
            elif event_type in ("deregister", "expire"):
                if service_id in self._service_cache:
                    del self._service_cache[service_id]

    async def discover_service(self, service_type: str, use_cache: bool = True) -> dict[str, Any] | None:
        """
        Discover a service of the specified type. The service is guaranteed to be healthy at the time of discovery.

        The returned information contains:

        - name: the name of the service
        - host: the ip address or hostname of the service
        - port: the port number for requests to the microservice

        Args:
            service_type: Type of service to discover
            use_cache: Whether to use cached service information

        Returns:
            Service information if found, None otherwise
        """
        # Try to use cache first if enabled
        if use_cache:
            async with self._get_service_cache_lock():
                # Find services of the specified type
                matching_services = []
                for service_id, service_info in self._service_cache.items():
                    if service_info.get("type") == service_type or service_type in service_info.get("tags", []):
                        matching_services.append(service_info)

                if matching_services:
                    # Simple load balancing - random selection
                    import random

                    return random.choice(matching_services)

        # If not found in cache or cache disabled, ask the registry
        request = {"action": "discover", "service_type": service_type}

        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        self.logger.debug(f"{response = }")

        if response.get("success"):
            service = response.get("service")

            # Update cache
            if service and "id" in service:
                async with self._get_service_cache_lock():
                    self._service_cache[service["id"]] = service

            return service
        else:
            self.logger.warning(f"Service discovery failed: {response.get('error')}")
            return None

    async def get_service(self, service_id: str, use_cache: bool = True) -> dict[str, Any] | None:
        """
        Get information about a specific service.

        Args:
            service_id: ID of the service to get
            use_cache: Whether to use cached service information

        Returns:
            Service information if found, None otherwise
        """
        # Try to use cache first if enabled
        if use_cache:
            async with self._get_service_cache_lock():
                if service_id in self._service_cache:
                    return self._service_cache[service_id]

        # If not found in cache or cache disabled, ask the registry
        request = {"action": "get", "service_id": service_id}

        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            service = response.get("service")

            # Update cache
            if service:
                async with self._get_service_cache_lock():
                    self._service_cache[service_id] = service

            return service
        else:
            self.logger.warning(f"Get service failed: {response.get('error')}")
            return None

    async def list_services(self, service_type: str | None = None) -> list[dict[str, Any]]:
        """
        List all registered services, optionally filtered by type.

        Args:
            service_type: Type of services to list

        Returns:
            List of service information
        """
        request = {"action": "list", "service_type": service_type}

        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)

        if response.get("success"):
            services = response.get("services", [])

            # Update cache
            async with self._get_service_cache_lock():
                for service in services:
                    if "id" in service:
                        self._service_cache[service["id"]] = service

            return services
        else:
            self.logger.warning(f"List services failed: {response.get('error')}")
            return []

    async def get_endpoint(self, service_type) -> str | None:
        """Returns the endpoint for the given service type."""
        service = await self.discover_service(service_type)

        if service:
            protocol = service.get("protocol", "tcp")
            hostname = service["host"]
            port = service["port"]

            return f"{protocol}://{hostname}:{port}"
        else:
            return None

    async def health_check(self) -> bool:
        """
        Check if the registry server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        request = {"action": "health"}

        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request, timeout=HEALTH_CHECK_TIMEOUT)
        return response.get("success", False)

    async def terminate_registry_server(self) -> bool:
        """
        Send a terminate request to the service registry server. Returns True when successful.
        """
        request = {"action": "terminate"}
        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request, timeout=PROCESS_SHUTDOWN_TIMEOUT)
        return response.get("success", False)

    async def server_status(self) -> dict[str, Any]:
        """
        Requests the status information from the service registry.
        """
        request = {
            "action": "info",
        }
        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)
        return response

    async def close(self) -> None:
        """Clean up resources."""
        await self.stop_heartbeat()  # This stops all tasks

        try:
            if hasattr(self, "req_socket") and self.req_socket:
                self.req_socket.close()

            if hasattr(self, "sub_socket") and self.sub_socket:
                self.sub_socket.close()

            # We can not terminate the context, because we use a global instance, i.e. a singleton context.
            # When we try to terminate it, even after checking if it was closed,
            if hasattr(self, "context") and self.context:
                self.logger.info(f"{self.context = !r}")
                self.logger.info(f"{self.context._sockets = !r}")
                if not self.context.closed:
                    self.context.term()
        except Exception as exc:
            self.logger.error(f"Error during cleanup: {exc}")

    @asynccontextmanager
    async def register_context(self, *args, **kwargs):
        """
        Async context manager for service registration.

        Example:
            async with client.register_context("my-service", "localhost", 8080):
                # Service is registered
                await app.start()
            # Service is automatically deregistered
        """
        service_id = await self.register(*args, **kwargs)

        if not service_id:
            raise RuntimeError("Failed to register service")

        # Start heartbeat and event listener
        await self.start_heartbeat()
        await self.start_event_listener()

        try:
            yield service_id
        finally:
            # Clean up
            await self.stop_event_listener()
            await self.stop_heartbeat()
            await self.deregister()
            # await self.close()  # client shall not be closed by this context manager !!


def is_service_registered(service_type: str):
    """Convenience function to check if a service is registered."""
    with RegistryClient() as reg:
        response = reg.discover_service(service_type)

    return False if response is None else True
