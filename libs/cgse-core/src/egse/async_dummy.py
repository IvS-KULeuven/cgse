from __future__ import annotations

from typing import Any

from egse.async_control import AsyncControlServer
from egse.async_control import TypedAsyncControlClient
from egse.zmq_ser import zmq_json_response
from egse.zmq_ser import zmq_string_response


class DummyAsyncControlServer(AsyncControlServer):
    """Example async control server showing what belongs in a subclass.

    The superclass handles sockets, request/response framing, registration, lifecycle,
    task management, and common service commands. This subclass only defines
    device-specific commands and extra service metadata.
    """

    service_type = "dummy-async-control-server"

    def __init__(self):
        self._last_value: str | None = None
        self._echo_count = 0
        super().__init__()

    def register_custom_handlers(self):
        self.add_device_command_handler("echo", self._do_echo)
        self.add_device_command_handler("set-value", self._do_set_value)
        self.add_service_command_handler("health", self._handle_health)

    def get_service_info(self) -> dict[str, Any]:
        info = super().get_service_info()
        info.update(
            {
                "supports": ["echo", "set-value", "health", "ping", "info", "terminate"],
                "echo count": self._echo_count,
                "last value": self._last_value,
            }
        )
        return info

    async def _do_echo(self, cmd: dict[str, Any]) -> list:
        payload = str(cmd.get("message", ""))
        self._echo_count += 1
        return zmq_string_response(payload)

    async def _do_set_value(self, cmd: dict[str, Any]) -> list:
        self._last_value = str(cmd.get("value", ""))
        return zmq_json_response({"success": True, "message": {"stored": self._last_value}})

    async def _handle_health(self, cmd: dict[str, Any]) -> list:
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "status": "ok",
                    "echo count": self._echo_count,
                    "last value": self._last_value,
                },
            }
        )


class DummyAsyncControlClient(TypedAsyncControlClient):
    """Example client wrapper with strongly named methods for dummy commands."""

    service_type = DummyAsyncControlServer.service_type

    async def echo(self, message: str, timeout: float | None = None) -> str | None:
        response = await self.send_device_command({"command": "echo", "message": message}, timeout=timeout)
        return self._success_message_as_str(response, "echo")

    async def set_value(self, value: str, timeout: float | None = None) -> str | None:
        response = await self.send_device_command({"command": "set-value", "value": value}, timeout=timeout)
        message = self._success_message_as_dict(response, "set-value")
        if message is None:
            return None
        return str(message.get("stored"))

    async def health(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_service_command("health", timeout=timeout)
        return self._success_message_as_dict(response, "health")
