import asyncio
import json
import logging
import uuid
from typing import Any

import zmq
import zmq.asyncio

from egse.notifyhub import DEFAULT_REQUESTS_PORT
from egse.registry import MessageType

REQUEST_TIMEOUT = 5.0  # seconds


class AsyncNotificationHubClient:
    def __init__(
        self,
        req_endpoint: str = None,
        request_timeout: float = REQUEST_TIMEOUT,
        client_id: str = "async-notify-hub-client",
    ):
        """
        Initialize the async notification hub client.

        Args:
            req_endpoint: ZeroMQ endpoint for REQ-REP socket, defaults to DEFAULT_RS_REQ_PORT on localhost.
            request_timeout: Timeout for requests in seconds, defaults to 5.0.
            client_id: client identification, default='registry-client'
        """
        self.req_endpoint = req_endpoint or f"tcp://localhost:{DEFAULT_REQUESTS_PORT}"

        self.request_timeout = request_timeout
        self.logger = logging.getLogger("egse.notifyhub.client")

        self._client_id = f"{client_id}-{uuid.uuid4()}".encode()

        self.context = zmq.asyncio.Context.instance()
        self.req_socket: zmq.asyncio.Socket | None = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        self.logger.debug("Connecting to notification hub...")

        # REQ socket for request-reply pattern
        self.req_socket = self.context.socket(zmq.DEALER)
        self.req_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
        self.req_socket.setsockopt(zmq.IDENTITY, self._client_id)
        self.req_socket.connect(self.req_endpoint)

    def disconnect(self):
        self.logger.debug("Disconnecting from notification hub...")

        if self.req_socket:
            self.req_socket.close(linger=0)
        self.req_socket = None

    async def health_check(self) -> bool:
        """
        Check if the registry server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        request = {"action": "health"}
        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)
        return response.get("success", False)

    async def terminate_notification_hub(self):
        """
        Send a terminate request to the notification hub. Returns True when successful.
        """
        request = {"action": "terminate"}
        response = await self._send_request(MessageType.REQUEST_WITH_REPLY, request)
        return response.get("success", False)

    async def _send_request(self, msg_type: MessageType, request: dict[str, Any]) -> dict[str, Any]:
        """
        Send a request to the registry and get the response.

        Args:
            msg_type: the type of message and reply
            request: The request to send to the service registry server.

        Returns:
            The response from the registry as a dictionary.
        """
        self.logger.debug(f"Sending request: {request}")

        try:
            await self.req_socket.send_multipart([msg_type.value, json.dumps(request).encode()])

            if msg_type == MessageType.REQUEST_NO_REPLY:
                return {
                    "success": True,
                }

            try:
                message_parts = await asyncio.wait_for(self.req_socket.recv_multipart(), timeout=self.request_timeout)

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
                self.logger.warning(f"Request timed out after {self.request_timeout:.2f}s")
                return {"success": False, "error": "Request timed out"}
        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}


class NotificationHubClient:
    def __init__(
        self,
        req_endpoint: str = None,
        request_timeout: float = REQUEST_TIMEOUT,
        client_id: str = "notify-hub-client",
    ):
        """
        Initialize the async notification hub client.

        Args:
            req_endpoint: ZeroMQ endpoint for REQ-REP socket, defaults to DEFAULT_RS_REQ_PORT on localhost.
            request_timeout: Timeout for requests in seconds, defaults to 5.0.
            client_id: client identification, default='registry-client'
        """
        self.req_endpoint = req_endpoint or f"tcp://localhost:{DEFAULT_REQUESTS_PORT}"

        self.request_timeout = request_timeout
        self.logger = logging.getLogger("egse.notifyhub.client")

        self._client_id = f"{client_id}-{uuid.uuid4()}".encode()

        self.context = zmq.Context.instance()
        self.req_socket: zmq.Socket | None = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        self.logger.debug("Connecting to notification hub...")

        # REQ socket for request-reply pattern
        self.req_socket = self.context.socket(zmq.DEALER)
        self.req_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
        self.req_socket.setsockopt(zmq.IDENTITY, self._client_id)
        self.req_socket.connect(self.req_endpoint)

    def disconnect(self):
        self.logger.debug("Disconnecting from notification hub...")

        if self.req_socket:
            self.req_socket.close(linger=0)
        self.req_socket = None

    def health_check(self) -> bool:
        """
        Check if the registry server is healthy.

        Returns:
            True if healthy, False otherwise
        """
        request = {"action": "health"}
        response = self._send_request(MessageType.REQUEST_WITH_REPLY, request)
        return response.get("success", False)

    def terminate_notification_hub(self) -> bool:
        """
        Send a terminate request to the notification hub. Returns True when successful.
        """
        request = {"action": "terminate"}
        response = self._send_request(MessageType.REQUEST_NO_REPLY, request)
        return response.get("success", False)

    def _send_request(self, msg_type: MessageType, request: dict[str, Any]) -> dict[str, Any]:
        """
        Send a request to the registry and get the response.

        Args:
            msg_type: the type of message and reply
            request: The request to send to the service registry server.
            timeout: The number of seconds to wait before timeout

        Returns:
            The response from the registry as a dictionary.
        """

        self.logger.debug(f"Sending request: {request}")

        timeout_ms = int(self.request_timeout * 1000)
        try:
            self.req_socket.send_multipart([msg_type.value, json.dumps(request).encode()])

            try:
                if self.req_socket.poll(timeout=timeout_ms):
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
                    self.logger.error(f"Request timed out after {self.request_timeout:.2f}s")
                    return {"success": False, "error": "Request timed out"}

            except asyncio.TimeoutError:
                self.logger.warning(f"Request timed out after {self.request_timeout:.2f}s")
                return {"success": False, "error": "Request timed out"}
        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            self.logger.error(f"Error sending request: {exc}", exc_info=True)
            return {"success": False, "error": str(exc)}
