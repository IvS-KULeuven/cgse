"""Async client for the Configuration Manager service."""

from __future__ import annotations

from typing import Any

from egse.setup import Setup

import egse.cm_acs as cm_acs_module
from egse.async_control import AsyncControlClient
from egse.cm_acs.typed_serialization import get_typed_payload_serializer


class AsyncConfigurationManagerClient(AsyncControlClient):
    """Typed async client for configuration manager device commands."""

    service_type = cm_acs_module.SERVICE_TYPE
    client_id = "cm-async-client-xxx"

    def _create_typed_payload_serializer(self):
        return get_typed_payload_serializer()

    async def list_setups(self, **attr: dict[str, Any]) -> list[list]:
        """List the available setups on the async configuration manager, optionally filtered by the given attributes.

        Args:
            **attr: see egse.system.filter_by_attr()

        Returns:
            A list of setups, where each setup is represented as a list of the following format:
                [setup_id, setup_name, setup_type, ...].
        """
        response = await self.send_device_command({"command": "list_setups", "attributes": attr or {}})
        if not response.get("success"):
            raise RuntimeError(f"Failed to list setups: {response.get('message')}")
        return response["return_code"]

    async def load_setup(self, setup_id: int) -> dict[str, Any]:
        response = await self.send_device_command({"command": "load_setup", "setup_id": setup_id})
        if not response.get("success"):
            raise RuntimeError(f"Failed to load setup: {response.get('message')}")
        return response["return_code"]

    async def get_setup(self, setup_id: int | None = None) -> Setup:
        """
        Returns the Setup with the given `setup_id` or, when `setup_id` is None, returns the currently loaded Setup
        on the configuration manager.

        Raises:
            RuntimeError: when it fails to load a Setup.
        """
        response = await self.send_device_command({"command": "get_setup", "setup_id": setup_id})
        if not response.get("success"):
            raise RuntimeError(f"Failed to get setup: {response.get('message')}")

        setup = response["return_code"]
        if isinstance(setup, Setup):
            return setup

        raise RuntimeError(f"Failed to decode setup response, expected Setup but got {type(setup).__name__}")

    async def get_obsid(self) -> dict[str, Any]:
        response = await self.send_device_command({"command": "get_obsid"})
        if not response.get("success"):
            raise RuntimeError(f"Failed to get obsid: {response.get('message')}")
        return response["return_code"]

    async def reload_setups(self) -> dict[str, Any]:
        response = await self.send_device_command({"command": "reload_setups"})
        if not response.get("success"):
            raise RuntimeError(f"Failed to reload setups: {response.get('message')}")
        return response["return_code"]

    async def register_to_storage(self) -> dict[str, Any]:
        response = await self.send_device_command({"command": "register_to_storage"})
        if not response.get("success"):
            raise RuntimeError(f"Failed to register to storage: {response.get('message')}")
        return response["return_code"]

    async def confman_health(self) -> dict[str, Any] | None:
        response = await self.send_service_command("confman_health")
        if response.get("success"):
            return response.get("message")
        return None
