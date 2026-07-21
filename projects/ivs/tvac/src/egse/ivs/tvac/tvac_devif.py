import asyncio
import logging
from typing import Any, Awaitable, Callable

from egse.device import DeviceConnectionError
from asyncua import Client, ua

from egse.ivs.tvac import DEVICE_SETTINGS

LOGGER = logging.getLogger(__name__)


# Look-up table, relating the name of the command with the actual OPC UA node id it corresponds to on the PLC.
# This table is shared between the real client (`ThermalVacOpcUaInterface`) and the `ThermalVacSimulator`, so both
# always agree on which nodes exist.

OPC_UA_NODES = {
    "is_vacuum_gauge_powered": "ns=4;s=MAIN.fbThermalVac.q_bVacuumGaugeOn",
    "is_vacuum_gauge_error": "ns=4;s=MAIN.fbThermalVac.stSTAT.bVacuumGaugeError",
    "get_vessel_pressure": "ns=4;s=MAIN.fbThermalVac.stSTAT.rVesselPressure",
    "get_filtered_vessel_pressure": "ns=4;s=MAIN.fbThermalVac.stSTAT.rVesselPressureFilt",
    "get_temperatures": "ns=4;s=MAIN.fbThermalVac.stSTAT.rPt100sTempCelcius",
    "get_dut_temperatures": "ns=4;s=MAIN.fbThermalVac.stSTAT.rDUTTempSensCelcius",
    "get_dut_temperature_weights": "ns=4;s=MAIN.fbThermalVac.stSTAT.iDUTTempSensWeight",
    "get_avg_temperature": "ns=4;s=PRG_PID_CALL.fbAverageTemp.output",
    "temperature_setpoint": "ns=4;s=PRG_PID_CALL.rSetpointTemp",
    "get_pid_output_cooling": "ns=4;s=PRG_CTRL_PID_Cooling.stPID_STAT.lrOutput",
    "get_pid_output_heating": "ns=4;s=PRG_CTRL_PID_Heating.stPID_STAT.lrOutput",
    "temperature_ctrl_active": "ns=4;s=MAIN.fbThermalVac.stCMD.bStartTemperatureControl",
    "is_scroll_pump_running": "ns=4;s=MAIN.fbThermalVac.stScrollPump_STAT.bRunning",
    "is_scroll_pump_alarm": "ns=4;s=MAIN.fbThermalVac.stScrollPump_STAT.bAlarm",
    "get_turbo_pump_rpm": "ns=4;s=MAIN.fbThermalVac.stTurboPump_STAT.udiRotorSpeed",
    "is_turbo_pump_error": "ns=4;s=MAIN.fbThermalVac.stTurboPump_STAT.bError",
    "get_tvac_state": "ns=4;s=MAIN.fbThermalVac.stSTAT.eState",
    "set_stop_pumps": "ns=4;s=MAIN.fbThermalVac.bStopPumps",
    "is_data_logging_active": "ns=4;s=PRG_DataLogging.bDataLoggingActive",
    "start_data_logging": "ns=4;s=GVL.bStartDataLogging",
    "stop_data_logging": "ns=4;s=GVL.bStopDataLogging",
    "get_data_logging_state": "ns=4;s=PRG_DataLogging.fbDataLogger.eState",
    "is_data_logging_error": "ns=4;s=PRG_DataLogging.fbDataLogger.bError",
    "get_data_logging_error_id": "ns=4;s=PRG_DataLogging.fbDataLogger.eErrorId",
    "get_data_logging_filename": "ns=4;s=PRG_DataLogging.sFileName",
    "get_data_logging_directory": "ns=4;s=GVL.sDataLoggingDir",
    "set_file_path_to_read": "ns=4;s=GVL.fbReadFileContents.sFilePath",
    "trigger_state": "ns=4;s=GVL.fbReadFileContents.eReadState",
    "get_file_content": "ns=4;s=GVL.fbReadFileContents.sFileContent",
}


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
        self._reconnect_lock = asyncio.Lock()

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
                try:
                    await self.client.disconnect()
                except Exception as e:
                    LOGGER.warning(f"{self.device_id}: error while disconnecting (ignoring): {e}")
                finally:
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

    async def _call_with_reconnect(self, op: Callable[[], Awaitable[Any]]) -> Any:
        """Runs `op`, and if it fails, reconnects to the device and retries `op` exactly once.

        This is what lets any read/write self-heal from a dropped OPC UA session (e.g. after the PLC or the
        simulator briefly drops the connection) without the caller having to know or care about reconnecting.

        Args:
            op: Zero-argument coroutine function performing the actual OPC UA call.

        Returns:
            The result of `op()`.

        Raises:
            Whatever `op()` raises on its second (post-reconnect) attempt.
        """

        try:
            return await op()
        except Exception as e:
            LOGGER.warning(f"{self.device_id}: I/O failed ({e}); reconnecting and retrying once")
            async with self._reconnect_lock:
                # Re-check: a concurrent caller may have already reconnected while we were waiting for the lock.
                if not await self.is_connected():
                    await self.reconnect()
            return await op()

    async def read_node(self, command: str) -> Any:
        """Transmits the given command to the device and returns the response.

        Returns:
            Response from the device.
        """

        async def _op():
            async with self._lock:
                variable = self.client.get_node(command)
                return await variable.read_value()

        return await self._call_with_reconnect(_op)

    async def write_node(self, command: str, value, data_type: ua.VariantType) -> None:
        async def _op():
            async with self._lock:
                variable = self.client.get_node(command)
                await variable.set_value(ua.DataValue(ua.Variant(value, data_type)))

        await self._call_with_reconnect(_op)

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
