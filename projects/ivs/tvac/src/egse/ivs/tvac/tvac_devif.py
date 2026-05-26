import asyncio
import logging
from typing import Any

from egse.device import DeviceConnectionError
from asyncua import Client, ua

from egse.ivs.tvac import DEVICE_SETTINGS

LOGGER = logging.getLogger(__name__)


class ThermalVacError(Exception):
    """A TVAC-specific error."""

    pass


class ThermalVacOpcUaInterface:
    def __init__(self, hostname: str = None, port: int = None):
        """Initialisation of a OPC UA connection to the ThermalVac device.

        Args:
            hostname (str | None): Hostname to connect to.  If this is None, the hostname will be read from the settings.
            port (int | None): Port to connect to.  If this is None, the port will be read from the settings.
        """

        self.hostname = DEVICE_SETTINGS["HOSTNAME"] if hostname is None else hostname
        self.port = DEVICE_SETTINGS["PORT"] if port is None else port
        self.device_id = "TVAC"

        self._is_connection_open = False
        self.client = Client(self.server_url)
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish the connection to the device."""

        if self._is_connection_open:
            LOGGER.warning(f"Device {self.device_id} already connected")
            return

        if self.hostname in (None, ""):
            raise ValueError(f"{self.device_id}: hostname is not initialised.")

        if self.port in (None, 0):
            raise ValueError(f"{self.device_id}: port number is not initialised.")

        async with self._lock:
            await self.client.connect()

            self._is_connection_open = True

            if not await self.is_connected():
                self._is_connection_open = False
                raise DeviceConnectionError(
                    self.device_id, "Device is not connected, check logging messages for the cause."
                )

    async def disconnect(self) -> None:
        """Closes the connection to the device."""

        async with self._lock:
            if self._is_connection_open:
                await self.client.disconnect()
                self._is_connection_open = False

    async def reconnect(self) -> None:
        """Re-establishes the connection to the device."""

        if self._is_connection_open:
            await self.disconnect()
        await self.connect()

    async def is_connected(self) -> bool:
        """Checks whether the device is connected (and responsive).

        Verifies whether the connection is active by attempting to read the server node.

        Returns:
            True if the device is connected and responsive, False otherwise.
        """

        try:
            if not self._is_connection_open:
                return False
            # Try to read the root node as a health check
            root = self.client.get_root_node()
            await root.read_browse_name()
            return True
        except Exception as e:
            LOGGER.error(f"Connection health check failed: {e}")
            return False

    async def read_node(self, command: str) -> Any:
        """Transmits the given command to the device and returns the response.

        Returns:
            Response from the device.
        """

        async with self._lock:
            variable = self.client.get_node(command)
            return await variable.read_value()

    async def write_node(self, command: str, value, data_type: ua.VariantType) -> None:
        async with self._lock:
            variable = self.client.get_node(command)
            await variable.set_value(ua.DataValue(ua.Variant(value, data_type)))

    @property
    def server_url(self):
        return f"opc.tcp://{self.hostname}:{self.port}"

    async def __aenter__(self):
        """Asynchronous context manager entry.

        This establishes the connection to the H/W unit.
        """

        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Asynchronous context manager exit.

        This ensures the connection to the H/W unit is properly closed.
        """

        await self.disconnect()
