from __future__ import annotations

from typing import Any

from egse.response import Failure

from egse.async_control import ServiceCommandRouter
from egse.async_control import SocketType
from egse.cm_acs.controller import AsyncConfigurationManagerController


class AsyncConfigurationManagerServices(ServiceCommandRouter):
    """Confman-specific service-command handlers and status extensions."""

    def __init__(self, control_server, controller: AsyncConfigurationManagerController):
        super().__init__(control_server)
        self._controller = controller

    def register_handlers(self):
        self.add_handler("register_to_storage", self.register_to_storage)
        self.add_handler("confman_status", self._handle_status)

    async def register_to_storage(self, cmd: dict[str, Any]) -> list:
        response = await self._controller.register_to_storage_async()

        if isinstance(response, Failure):
            return self._control_server.create_json_response(
                SocketType.SERVICE,
                {
                    "success": False,
                    "message": str(response),
                    "result_type": "Failure",
                },
            )

        return self._control_server.create_json_response(
            SocketType.SERVICE,
            {
                "success": True,
                "message": "register_to_storage completed",
                "result_type": type(response).__name__,
            },
        )

    async def _handle_status(self, cmd: dict[str, Any]) -> list:
        """Return a compact confman-specific status payload."""
        return self._control_server.create_json_response(
            SocketType.SERVICE,
            {
                "success": True,
                "message": {
                    "status": "ok",
                    "confman": self._controller.get_status(),
                },
            },
        )
