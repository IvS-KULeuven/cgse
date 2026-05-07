"""Async client for the Configuration Manager service."""

from __future__ import annotations

from typing import Any

from egse.setup import Setup

import egse.cm_acs as cm_acs_module
from egse.async_control import TypedAsyncControlClient
from egse.cm_acs.typed_serialization import get_typed_payload_serializer


class AsyncConfigurationManagerClient(TypedAsyncControlClient):
    """Typed async client for configuration manager device commands."""

    service_type = cm_acs_module.SERVICE_TYPE
    client_id = "cm-async-client"

    def create_typed_payload_serializer(self):
        return get_typed_payload_serializer()

    def _extract_return_code(self, response: dict[str, Any], command_name: str) -> Any:
        """Return command payload in a backward-compatible way.

        Legacy controller responses use `return_code`, while newer command styles
        may only return a `message` payload.
        """
        if not response.get("success"):
            raise RuntimeError(f"Failed to {command_name}: {response.get('message')}")

        if "return_code" in response:
            return response["return_code"]

        if "message" in response:
            return response["message"]

        raise RuntimeError(f"Failed to decode {command_name} response, missing payload.")

    async def list_setups(self, **attr: dict[str, Any]) -> list[list]:
        """List the available setups on the async configuration manager, optionally filtered by the given attributes.

        Args:
            **attr: see egse.system.filter_by_attr()

        Returns:
            A list of setups, where each setup is represented as a list of the following format:
                [setup_id, setup_name, setup_type, ...].
        """
        response = await self.send_device_command({"command": "list_setups", "attributes": attr or {}})
        result = self._extract_return_code(response, "list setups")
        if isinstance(result, list):
            return result
        raise RuntimeError(f"Failed to decode list_setups response, expected list but got {type(result).__name__}")

    async def load_setup(self, setup_id: int) -> Setup:
        response = await self.send_device_command({"command": "load_setup", "setup_id": setup_id})
        setup = self._extract_return_code(response, "load setup")
        if isinstance(setup, Setup):
            return setup

        raise RuntimeError(f"Failed to decode load_setup response, expected Setup but got {type(setup).__name__}")

    async def submit_setup(self, setup: Setup, description: str) -> Setup:
        response = await self.send_device_command(
            {"command": "submit_setup", "setup": setup, "description": description}
        )
        setup = self._extract_return_code(response, "submit setup")
        if isinstance(setup, Setup):
            return setup

        raise RuntimeError(f"Failed to decode submit_setup response, expected Setup but got {type(setup).__name__}")

    async def get_setup(self, setup_id: int | None = None) -> Setup:
        """
        Returns the Setup with the given `setup_id` or, when `setup_id` is None, returns the currently loaded Setup
        on the configuration manager.

        Raises:
            RuntimeError: when it fails to load a Setup.
        """
        response = await self.send_device_command({"command": "get_setup", "setup_id": setup_id})
        setup = self._extract_return_code(response, "get setup")
        if isinstance(setup, Setup):
            return setup

        raise RuntimeError(f"Failed to decode get_setup response, expected Setup but got {type(setup).__name__}")

    async def get_obsid(self) -> dict[str, Any]:
        response = await self.send_device_command({"command": "get_obsid"})
        result = self._extract_return_code(response, "get obsid")
        if isinstance(result, dict):
            return result
        raise RuntimeError(f"Failed to decode get_obsid response, expected dict but got {type(result).__name__}")

    async def reload_setups(self) -> dict[str, Any]:
        response = await self.send_device_command({"command": "reload_setups"})
        result = self._extract_return_code(response, "reload setups")
        if isinstance(result, dict):
            return result
        raise RuntimeError(f"Failed to decode reload_setups response, expected dict but got {type(result).__name__}")

    async def register_to_storage(self) -> dict[str, Any]:
        response = await self.send_device_command({"command": "register_to_storage"})
        result = self._extract_return_code(response, "register to storage")
        if isinstance(result, dict):
            return result
        raise RuntimeError(
            f"Failed to decode register_to_storage response, expected dict but got {type(result).__name__}"
        )

    async def confman_status(self) -> dict[str, Any] | None:
        response = await self.send_service_command("confman_status")
        return self._success_message_as_dict(response, "confman_status")
