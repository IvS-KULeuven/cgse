from __future__ import annotations

from typing import Any

from egse.async_control import ServiceCommandRouter
from egse.cm_acs.controller import AsyncConfigurationManagerController
from egse.response import Failure
from egse.zmq_ser import zmq_json_response


class AsyncConfigurationManagerServices(ServiceCommandRouter):
    """Confman-specific service-command handlers and status extensions."""

    def __init__(self, control_server, controller: AsyncConfigurationManagerController):
        super().__init__(control_server)
        self._controller = controller

    def register_default_handlers(self):
        super().register_default_handlers()  # ping, info, terminate, block
        self.add_handler("register_to_storage", self.register_to_storage)
        self.add_handler("confman_health", self._handle_health)

    async def register_to_storage(self, cmd: dict[str, Any]) -> list:
        response = await self._controller.register_to_storage_async()

        if isinstance(response, Failure):
            return zmq_json_response(
                {
                    "success": False,
                    "message": str(response),
                    "result_type": "Failure",
                }
            )

        return zmq_json_response(
            {
                "success": True,
                "message": "register_to_storage completed",
                "result_type": type(response).__name__,
            }
        )

    async def _handle_health(self, cmd: dict[str, Any]) -> list:
        """Return a compact confman-specific health payload."""
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "status": "ok",
                    "confman": self._controller.get_status(),
                },
            }
        )
