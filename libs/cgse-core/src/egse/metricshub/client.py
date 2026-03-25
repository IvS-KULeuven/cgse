"""Client for the Async Metrics Hub.

Use :class:`AsyncMetricsHubClient` to send control requests (health, info,
terminate) to a running ``mh_cs`` service.

For sending data points to the hub use :class:`AsyncMetricsHubSender` (async)
or :class:`MetricsHubSender` (sync), both of which keep a ZMQ PUSH socket and
serialise :class:`~egse.metrics.DataPoint` objects as JSON.

Canonical payload format (``DataPoint.as_dict()``)::

    {
        "measurement": "camera_tm",
        "tags": {"device_id": "cam_01"},
        "fields": {"temperature": 23.4},
        "time": "2026-03-23T12:34:56.000000+0000",  # optional
    }

Quick usage (async)::

    sender = AsyncMetricsHubSender()
    sender.connect()
    await sender.send(DataPoint.measurement("camera_tm").field("temperature", 23.4))
    sender.close()

Quick usage (sync)::

    sender = MetricsHubSender()
    sender.connect()
    sender.send(DataPoint.measurement("camera_tm").field("temperature", 23.4))
    sender.close()
"""

__all__ = [
    "AsyncMetricsHubClient",
    "MetricsHubClient",
    "AsyncMetricsHubSender",
    "MetricsHubSender",
]

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import zmq
import zmq.asyncio

from egse.metrics import DataPoint
from egse.metricshub import DEFAULT_COLLECTOR_PORT
from egse.metricshub import DEFAULT_REQUESTS_PORT
from egse.registry import MessageType

REQUEST_TIMEOUT = 5.0  # seconds


class AsyncMetricsHubClient:
    """Async client for sending control requests to the Metrics Hub.

    Typical use::

        async with AsyncMetricsHubClient() as client:
            ok = await client.health_check()
    """

    def __init__(
        self,
        req_endpoint: str | None = None,
        request_timeout: float = REQUEST_TIMEOUT,
        client_id: str = "async-metrics-hub-client",
    ):
        self.req_endpoint = req_endpoint or f"tcp://localhost:{DEFAULT_REQUESTS_PORT}"
        self.request_timeout = request_timeout
        self.logger = logging.getLogger("egse.metricshub.client")

        self._client_id = f"{client_id}-{uuid.uuid4()}".encode()

        self.context = zmq.asyncio.Context.instance()
        self.req_socket: zmq.asyncio.Socket | None = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        self.logger.debug("Connecting to Metrics Hub...")
        self.req_socket = self.context.socket(zmq.DEALER)
        self.req_socket.setsockopt(zmq.LINGER, 0)
        self.req_socket.setsockopt(zmq.IDENTITY, self._client_id)
        self.req_socket.connect(self.req_endpoint)

    def disconnect(self):
        self.logger.debug("Disconnecting from Metrics Hub...")
        if self.req_socket:
            self.req_socket.close(linger=0)
        self.req_socket = None

    async def health_check(self) -> bool:
        """Return True if the hub responds with a healthy status."""
        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, {"action": "health"})
        return response.get("success", False)

    async def server_status(self) -> dict[str, Any]:
        """Return the full info dict from the hub (ports, stats, config)."""
        return await self._send_request(MessageType.REQUEST_WITH_REPLY, {"action": "info"})

    async def terminate_metrics_hub(self) -> bool:
        """Send a terminate request.  Returns True on success."""
        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, {"action": "terminate"})
        return response.get("success", False)

    async def _send_request(self, msg_type: MessageType, request: dict[str, Any]) -> dict[str, Any]:
        self.logger.debug(f"Sending request: {request}")

        try:
            await self.req_socket.send_multipart([msg_type.value, json.dumps(request).encode()])  # type: ignore[union-attr]

            if msg_type == MessageType.REQUEST_NO_REPLY:
                return {"success": True}

            try:
                message_parts = await asyncio.wait_for(
                    self.req_socket.recv_multipart(),  # type: ignore[union-attr]
                    timeout=self.request_timeout,
                )

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
                            "error": f"Unexpected MessageType: {message_type.name}",
                        }
                else:
                    return {"success": False, "error": f"Incomplete response ({len(message_parts)} parts)"}

            except asyncio.TimeoutError:
                self.logger.warning(f"Request timed out after {self.request_timeout:.2f}s")
                return {"success": False, "error": "Request timed out"}

        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}


class MetricsHubClient:
    """Synchronous client for sending control requests to the Metrics Hub.

    This client is intended for older control servers that do not use asyncio.
    """

    def __init__(
        self,
        req_endpoint: str | None = None,
        request_timeout: float = REQUEST_TIMEOUT,
        client_id: str = "metrics-hub-client",
    ):
        self.req_endpoint = req_endpoint or f"tcp://localhost:{DEFAULT_REQUESTS_PORT}"
        self.request_timeout = request_timeout
        self.logger = logging.getLogger("egse.metricshub.client")

        self._client_id = f"{client_id}-{uuid.uuid4()}".encode()

        self.context = zmq.Context.instance()
        self.req_socket: zmq.Socket | None = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        self.logger.debug("Connecting to Metrics Hub...")

        socket = self.context.socket(zmq.DEALER)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.IDENTITY, self._client_id)
        socket.connect(self.req_endpoint)
        self.req_socket = socket

    def disconnect(self):
        self.logger.debug("Disconnecting from Metrics Hub...")

        if self.req_socket:
            self.req_socket.close(linger=0)
        self.req_socket = None

    def health_check(self) -> bool:
        """Return True if the hub responds with a healthy status."""
        response = self._send_request(MessageType.REQUEST_WITH_REPLY, {"action": "health"})
        return response.get("success", False)

    def server_status(self) -> dict[str, Any]:
        """Return the full info dict from the hub (ports, stats, config)."""
        return self._send_request(MessageType.REQUEST_WITH_REPLY, {"action": "info"})

    def terminate_metrics_hub(self) -> bool:
        """Send a terminate request. Returns True when request was sent."""
        response = self._send_request(MessageType.REQUEST_NO_REPLY, {"action": "terminate"})
        time.sleep(0.2)  # Allow request delivery before caller potentially exits.
        return response.get("success", False)

    def _send_request(self, msg_type: MessageType, request: dict[str, Any]) -> dict[str, Any]:
        self.logger.debug(f"Sending request: {request}")

        timeout_ms = int(self.request_timeout * 1000)

        try:
            self.req_socket.send_multipart([msg_type.value, json.dumps(request).encode()])  # type: ignore[union-attr]

            if msg_type == MessageType.REQUEST_NO_REPLY:
                return {"success": True}

            if self.req_socket.poll(timeout=timeout_ms):  # type: ignore[union-attr]
                message_parts = self.req_socket.recv_multipart()  # type: ignore[union-attr]

                if len(message_parts) >= 2:
                    message_type = MessageType(message_parts[0])
                    message_data = message_parts[1]

                    if message_type == MessageType.RESPONSE:
                        response = json.loads(message_data)
                        self.logger.debug(f"Received response: {response}")
                        return response

                    return {
                        "success": False,
                        "error": f"Unexpected MessageType: {message_type.name}, {message_data = }",
                    }

                return {
                    "success": False,
                    "error": f"Not enough parts received: {len(message_parts)}",
                    "data": message_parts,
                }

            self.logger.warning(f"Request timed out after {self.request_timeout:.2f}s")
            return {"success": False, "error": "Request timed out"}

        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}


class AsyncMetricsHubSender:
    """Lightweight sender for pushing :class:`~egse.metrics.DataPoint` objects to the hub.

    Maintains a single ZMQ PUSH socket for the lifetime of the sender.
    Fire-and-forget: if the hub queue is full the point is silently dropped and
    False is returned.

    Typical use inside an async control server::

        sender = AsyncMetricsHubSender()
        sender.connect()

        point = DataPoint.measurement("hexapod").tag("device_id", "hexapod_01").field("pos_x", 12.3)
        await sender.send(point)

        sender.close()
    """

    def __init__(
        self,
        hub_endpoint: str | None = None,
    ):
        self.hub_endpoint = hub_endpoint or f"tcp://localhost:{DEFAULT_COLLECTOR_PORT}"
        self.logger = logging.getLogger("egse.metricshub.sender")

        self.context = zmq.asyncio.Context.instance()
        self.socket: zmq.asyncio.Socket | None = None

    def connect(self):
        self.socket = self.context.socket(zmq.PUSH)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.SNDHWM, 1000)
        self.socket.connect(self.hub_endpoint)
        self.logger.debug(f"AsyncMetricsHubSender connected to {self.hub_endpoint}")

    def close(self):
        if self.socket:
            self.socket.close(linger=0)
        self.socket = None

    async def send(self, point: DataPoint) -> bool:
        """Serialise *point* and push it to the hub.

        Returns True on success, False if the hub is unreachable or the local
        send buffer is full (``zmq.Again``).
        """
        if self.socket is None:
            raise RuntimeError("Call connect() before send().")

        try:
            payload = json.dumps(point.as_dict()).encode()
            await self.socket.send(payload, flags=zmq.NOBLOCK)
            return True
        except zmq.Again:
            self.logger.debug("AsyncMetricsHubSender: send buffer full, point dropped.")
            return False
        except Exception as exc:
            self.logger.error(f"AsyncMetricsHubSender.send error: {exc}", exc_info=True)
            return False


class MetricsHubSender:
    """Synchronous sender for pushing DataPoint payloads to the Metrics Hub.

    Fire-and-forget semantics: if the local ZMQ send buffer is full this sender
    returns ``False`` rather than blocking.
    """

    def __init__(self, hub_endpoint: str | None = None):
        self.hub_endpoint = hub_endpoint or f"tcp://localhost:{DEFAULT_COLLECTOR_PORT}"
        self.logger = logging.getLogger("egse.metricshub.sender")

        self.context = zmq.Context.instance()
        self.socket: zmq.Socket | None = None

    def connect(self):
        socket = self.context.socket(zmq.PUSH)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.SNDHWM, 1000)
        socket.connect(self.hub_endpoint)
        self.socket = socket
        self.logger.debug(f"MetricsHubSender connected to {self.hub_endpoint}")

    def close(self):
        if self.socket:
            self.socket.close(linger=0)
        self.socket = None

    def send(self, point: DataPoint | dict[str, Any]) -> bool:
        """Serialise *point* and push it to the hub.

        Args:
            point: a :class:`~egse.metrics.DataPoint` instance or a pre-serialized
                dictionary matching ``DataPoint.as_dict()``.

        Returns:
            True when successfully queued to ZMQ, False when local send buffer
            is full (``zmq.Again``) or on other errors.
        """
        if self.socket is None:
            raise RuntimeError("Call connect() before send().")

        try:
            payload = json.dumps(point.as_dict() if isinstance(point, DataPoint) else point).encode()
            self.socket.send(payload, flags=zmq.NOBLOCK)
            return True
        except zmq.Again:
            self.logger.debug("MetricsHubSender: send buffer full, point dropped.")
            return False
        except Exception as exc:
            self.logger.error(f"MetricsHubSender.send error: {exc}", exc_info=True)
            return False
