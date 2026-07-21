from __future__ import annotations

import rich
from asyncua import ua

from egse.hk import read_conversion_dict, convert_hk_names
from egse.ivs.tvac import (
    tvac_state_to_string,
    STORAGE_MNEMONIC,
    SAMPLE_INTERVAL,
    SERVICE_NAME,
    SERVICE_TYPE,
    clamp_setpoint_temperature,
)
import asyncio
import datetime as dt
import multiprocessing
import sys
from typing import Any

import typer

from egse.ivs.tvac.tvac_devif import OPC_UA_NODES, ThermalVacOpcUaInterface, ThermalVacError
from egse.metrics import DataPoint
from egse.settings import get_site_id
from egse.setup import load_setup
from egse.system import TyperAsyncCommand, str_to_datetime
from egse.zmq_ser import zmq_json_response
from rich.console import Console

from egse.async_control import AcquisitionAsyncControlServer
from egse.async_control import DeviceCommandRouter
from egse.async_control import ServiceCommandRouter
from egse.async_control import TypedAsyncControlClient
from egse.logger import remote_logging
from egse.metricshub.client import AsyncMetricsHubSender


"""Implementation of the ThermalVac Control Server.

**Key Architectural Components:**

1. `ThermalVacController` — A `DeviceCommandRouter` sub-class that handles device-specific commands (start-scan,
   stop-scan, scan-status, etc.). It implements a command guard pattern that blocks certain commands while a scan is
   running to prevent conflicts with ongoing DAQ operations.

2. `ThermalVacServices` — A `ServiceCommandRouter` for handling service-level commands like health checks and
   component info.

3. `ThermalVacControlServer` — An `AcquisitionAsyncControlServer` subc-lass that manages the lifecycle of DAQ
   operations, including the background scan loop that reads data and forwards it to metric sinks.
"""

SITE_ID = get_site_id()

# Cap [s] for the read-retry backoff in `_run_scan_loop` when the device connection is down.
SCAN_RETRY_BACKOFF_MAX = 30.0


class ThermalVacDaq:
    def __init__(self):
        """Initialisation of Data Acquisition (DAQ) for the ThermalVac device."""

        self._running = False  # No scan is running
        self._scan_index = 0  # No scan has been performed yet

        self.opcua_interface = ThermalVacOpcUaInterface()

    # Communication via the OPC UA interface

    async def connect_to_opcua(self) -> None:
        """Establishes the connection to the OPC UA server of the ThermalVac device.

        This connection is established in the `start` method of the ThermalVac Control Server.
        """

        await self.opcua_interface.connect()

    async def disconnect_from_opcua(self) -> None:
        """Closes the connection to the OPC UA server of the ThermalVac device.

        This connection is closed in the `stop` method of the ThermalVac Control Server.
        """

        await self.opcua_interface.disconnect()

    async def _read_node(self, key: str) -> Any:
        """Transmits the given read command to the device and returns the response.

        The exact command that is transmitted to the OPC UA server is extracted from the `OPC_UA_NODES` look-up table
        (dictionary), based on the given key.

        Args:
            key (str): Key in the `OPC_UA_NODES` dictionary, for which the value is the read command to be transmitted.

        Returns:
            Response from the ThermalVac device.
        """

        if key not in OPC_UA_NODES:
            raise ThermalVacError(f"Unknown read command: {key}")

        try:
            return await self.opcua_interface.read_node(OPC_UA_NODES[key])
        except Exception as e:
            raise ThermalVacError(f"Error reading node for command {key}: {OPC_UA_NODES[key]}") from e

    async def _write_node(self, key: str, value, data_type: ua.VariantType) -> None:
        """Transmits the given write command to the device.

        The exact command that is transmitted to the OPC UA server is extracted from the `OPC_UA_NODES` look-up table
        (dictionary), based on the given key.

        Args:
            key (str): Key in the `OPC_UA_NODES` dictionary, for which the value is the write command to be transmitted.
            value: Argument that is passed to the write command.
            data_type (ua.VariantType): Data type of the argument that is passed to the write command.
        """

        if key not in OPC_UA_NODES:
            raise ThermalVacError(f"Unknown write_command: {key}")

        await self.opcua_interface.write_node(OPC_UA_NODES[key], value, data_type)

    # Pressure readings

    async def is_vacuum_gauge_powered(self) -> bool:
        """Checks whether the thermal vacuum gauge is powered.

        Returns:
            True if the vacuum gauge is powered, False otherwise.
        """

        return bool(await self._read_node("is_vacuum_gauge_powered"))

    async def is_vacuum_gauge_error(self) -> bool:
        """Checks whether the thermal vacuum gauge shows an error.

        Returns:
            True if the vacuum gauge shows an error, False otherwise.
        """

        return bool(await self._read_node("is_vacuum_gauge_error"))

    async def get_vessel_pressure(self) -> float:
        """Returns the vessel pressure.

        Returns:
            Vessel pressure [mbar].
        """

        return float(await self._read_node("get_vessel_pressure"))

    async def get_filtered_vessel_pressure(self) -> float:
        """Returns the filtered vessel pressure.

        Returns:
            Filtered vessel pressure [mbar].
        """

        return float(await self._read_node("get_filtered_vessel_pressure"))

    # Temperature readings

    async def get_temperatures(self) -> list[float]:
        """Returns the temperature readings of the vacuum chamber.

        There are three temperature readings, which can be queried individually with the following commands:
            - `get_temperature1`,
            - `get_temperature2`,
            - `get_temperature3`.

        Returns:
            Temperature readings of the vacuum chamber [°C].
        """

        return list(await self._read_node("get_temperatures"))

    async def get_temperature1(self) -> float:
        """Returns the temperature reading of the first temperature sensor in the vacuum chamber.

        Returns:
            Temperature reading of the first temperature sensor in the vacuum chamber [°C].
        """

        temperatures = await self.get_temperatures()
        return float(temperatures[0])

    async def get_temperature2(self) -> float:
        """Returns the temperature reading of the second temperature sensor in the vacuum chamber.

        Returns:
            Temperature reading of the second temperature sensor in the vacuum chamber [°C].
        """

        temperatures = await self.get_temperatures()
        return float(temperatures[1])

    async def get_dut_temperatures(self) -> list[float]:
        """Returns the temperature readings of the Device Under Test (DUT).

        There are three DUT temperature readings, which can be queried individually with the following commands:
            - `get_dut_temperatures1`,
            - `get_dut_temperatures2`,
            - `get_dut_temperatures3`.

        Returns:
            Temperature readings of the Device Under Test (DUT).
        """

        return list(await self._read_node("get_dut_temperatures"))

    async def get_dut_temperature1(self) -> float:
        """Returns the temperature reading of the first temperature sensor of the Device Under Test (DUT).

        Returns:
            Temperature reading of the first temperature sensor of the Device Under Test (DUT) [°C].
        """

        temperatures = await self.get_dut_temperatures()
        return float(temperatures[0])

    async def get_dut_temperature2(self) -> float:
        """Returns the temperature reading of the second temperature sensor of the Device Under Test (DUT).

        Returns:
            Temperature reading of the second temperature sensor of the Device Under Test (DUT) [°C].
        """

        temperatures = await self.get_dut_temperatures()
        return float(temperatures[1])

    async def get_dut_temperature3(self) -> float:
        """Returns the temperature reading of the third temperature sensor of the Device Under Test (DUT).

        Returns:
            Temperature reading of the third temperature sensor of the Device Under Test (DUT) [°C].
        """

        temperatures = await self.get_dut_temperatures()
        return float(temperatures[2])

    async def get_dut_temperature_weights(self) -> list[int]:
        """Returns the list of weights for the temperature sensors of the Device Under Test (DUT).

        These weights are used for the average temperature calculation of the DUT.

        There are three DUT temperature weights, which can be queried individually with the following commands:
            - `get_dut_temperature_weight1`,
            - `get_dut_temperature_weight2`,
            - `get_dut_temperature_weight3`.

        Returns:
            List of weights for the temperature sensors of the Device Under Test (DUT).
        """

        return list(await self._read_node("get_dut_temperature_weights"))

    async def get_dut_temperature_weight1(self) -> int:
        """Returns the weight for the first temperature sensor of the Device Under Test (DUT).

        Returns:
            Weight for the first temperature sensor of the Device Under Test (DUT).
        """

        weights = await self.get_dut_temperature_weights()
        return int(weights[0])

    async def get_dut_temperature_weight2(self) -> int:
        """Returns the weight for the second temperature sensor of the Device Under Test (DUT).

        Returns:
            Weight for the second temperature sensor of the Device Under Test (DUT).
        """

        weights = await self.get_dut_temperature_weights()
        return int(weights[1])

    async def get_dut_temperature_weight3(self) -> int:
        """Returns the weight for the third temperature sensor of the Device Under Test (DUT).

        Returns:
            Weight for the third temperature sensor of the Device Under Test (DUT).
        """

        weights = await self.get_dut_temperature_weights()
        return int(weights[2])

    async def get_avg_temperature(self) -> float:
        """Returns the average temperature.

        Returns:
            Average temperature [°C].
        """

        return float(await self._read_node("get_avg_temperature"))

    # Temperature control

    async def get_temperature_setpoint(self) -> float:
        """Returns the temperature setpoint.

        Returns:
            Temperature setpoint [°C].
        """

        return float(await self._read_node("temperature_setpoint"))

    async def set_temperature_setpoint(self, temperature: float) -> None:
        """Sets the temperature setpoint to the given value.

        If the given temperature setpoint is outside the allowed range (according to the limits from the setup), it
        will be clamped to the nearest limit from the settings.

        Args:
            temperature (float): Temperature setpoint [°C].
        """

        safe_temperature = clamp_setpoint_temperature(float(temperature))
        await self._write_node("temperature_setpoint", safe_temperature, ua.VariantType.Float)

    async def get_pid_output_cooling(self) -> float:
        """Returns the PID output for cooling.

        A PID output for cooling adjusts a system's output power based on the temperature error. It continuously
        calculates three factors to achieve precise, steady-state temperature control:
            -Proportional (P): Output based on the current gap between the actual temperature and the setpoint.
            - Integral (I): Output based on the duration of past errors to prevent steady-state offsets.
            - Derivative (D): Output based on the rate of change to prevent overshoot and system oscillations.

        Returns:
            PID output for cooling [%].
        """

        return float(await self._read_node("get_pid_output_cooling"))

    async def get_pid_output_heating(self) -> float:
        """Returns the PID (Proportional-Integral-Derivative) output for heating.

        A PID output for heating adjusts a system's output power based on the temperature error. It continuously
        calculates three factors to achieve precise, steady-state temperature control:
            -Proportional (P): Output based on the current gap between the actual temperature and the setpoint.
            - Integral (I): Output based on the duration of past errors to prevent steady-state offsets.
            - Derivative (D): Output based on the rate of change to prevent overshoot and system oscillations.

        Returns:
            PID output for heating [%].
        """

        return float(await self._read_node("get_pid_output_heating"))

    async def is_temperature_ctrl_active(self) -> bool:
        """Checks whether temperature control is active or not.

        Returns:
            True if temperature control is active, False otherwise.
        """

        return bool(await self._read_node("temperature_ctrl_active"))

    async def set_temperature_ctrl_active(self, active: bool) -> None:
        """Enables or disables temperature control.

        Args:
            active (bool): Indicates whether temperature control should be enabled (when True) or disabled (when False).
        """

        await self._write_node("temperature_ctrl_active", active, ua.VariantType.Boolean)

    async def enable_temperature_ctrl(self) -> None:
        """Enables temperature control."""

        await self.set_temperature_ctrl_active(True)

    async def disable_temperature_ctrl(self) -> None:
        """Disables temperature control."""

        await self.set_temperature_ctrl_active(False)

    # Pumps

    async def is_scroll_pump_running(self) -> bool:
        """Checks whether scroll pump is running or not.

        Returns:
            True if scroll pump is running, False otherwise.
        """

        return bool(await self._read_node("is_scroll_pump_running"))

    async def is_scroll_pump_alarm(self) -> bool:
        """Checks whether the scroll pump shows an alarm or not.

        Returns:
            True if scroll pump shows an alarm, False otherwise.
        """

        return bool(await self._read_node("is_scroll_pump_alarm"))

    async def get_turbo_pump_rpm(self) -> int:
        """Returns the speed of the turbo pump.

        Returns:
            Speed of the turbo pump [rpm].
        """

        return int(await self._read_node("get_turbo_pump_rpm"))

    async def is_turbo_pump_error(self) -> bool:
        """Checks if the turbo pump shows an error or not.

        Returns:
            True if turbo pump shows an error, False otherwise.
        """

        return bool(await self._read_node("is_turbo_pump_error"))

    # TVAC state

    async def get_tvac_state(self) -> int:
        """Returns the state of the TVAC.

        Returns:
            State of the TVAC.
        """

        return int(await self._read_node("get_tvac_state"))

    # Vessel evacuation

    async def set_stop_pumps(self, stop: bool) -> None:
        """Starts or stops the pumps.

        Args:
            stop (bool): Indicates whether the pumps should be stopped (True) or started (False).
        """
        await self._write_node("set_stop_pumps", stop, ua.VariantType.Boolean)

    async def start_pumps(self) -> None:
        """Starts the pumps."""

        await self.set_stop_pumps(False)

    async def stop_pumps(self) -> None:
        """Stops the pumps."""

        await self.set_stop_pumps(True)

    # Data logging

    async def is_data_logging_active(self) -> bool:
        """Checks whether data logging is active or not.

        Returns:
            True if data logging is active, False otherwise.
        """

        return bool(await self._read_node("is_data_logging_active"))

    async def start_data_logging(self) -> None:
        """Starts the data logging."""

        await self._write_node("start_data_logging", True, ua.VariantType.Boolean)

    async def stop_data_logging(self) -> None:
        """Stops the data logging."""

        await self._write_node("stop_data_logging", True, ua.VariantType.Boolean)

    async def get_data_logging_state(self) -> int:
        """Returns the state of the data logging.

        Returns:
            State of the data logging, -1 if not available.
        """

        try:
            return int(await self._read_node("get_data_logging_state"))
        except ThermalVacError:
            return -1

    async def is_data_logging_error(self) -> bool:
        """Checks whether data logging shows an error or not.

        Returns:
            True if data logging shows an error, False otherwise.
        """

        try:
            return bool(await self._read_node("is_data_logging_error"))
        except ThermalVacError:
            return False

    async def get_data_logging_error_id(self) -> int:
        """Returns the error ID of the data logging.

        Returns:
            Error ID of the data logging, -1 if not available.
        """

        try:
            return int(await self._read_node("get_data_logging_error_id"))
        except ThermalVacError:
            return -1

    async def get_data_logging_filename(self) -> str:
        """Returns the filename of the data logging file.

        Returns:
            Filename of the data logging file, empty string if not available.
        """

        try:
            return await self._read_node("get_data_logging_filename")
        except ThermalVacError:
            return ""

    async def get_data_logging_directory(self) -> str:
        """Returns the directory of the data logging file.

        Returns:
            Directory of the data logging file, empty string if not available.
        """

        try:
            return await self._read_node("get_data_logging_directory")
        except ThermalVacError:
            return ""

    async def read_file_from_plc(self, file_path: str) -> str:
        """Reads a PLC file.

        Args:
            file_path (str): Path to the PLC file.

        Returns:
            Contents of the PLC file.

        Raises:
            ThermalVacError when the PLC file cannot be read.
        """

        try:
            # Set the file path to read
            await self._write_node("set_file_path_to_read", file_path, ua.VariantType.String)

            # Ensure we're in WAIT_FOR_TRIGGER state first (state 0)
            await self._write_node("trigger_state", 0, ua.VariantType.Int32)
            await asyncio.sleep(0.1)

            # Trigger file read by setting the state to TRIGGER_FILE_OPEN (state 1)
            # The state enum: WAIT_FOR_TRIGGER = 0, TRIGGER_FILE_OPEN = 1, FILE_OPEN = 2,
            # TRIGGER_READ_EVENT = 3, READ_EVENT = 4, FILE_CLOSE = 5, ERROR = 6
            await self._write_node("trigger_state", 1, ua.VariantType.Int32)

            # Wait a bit for the PLC to process
            await asyncio.sleep(0.2)

            # Poll until read is complete (state returns to WAIT_FOR_TRIGGER (0) or ERROR (6))
            max_attempts = 100  # 10 seconds max wait time
            for attempt in range(max_attempts):
                await asyncio.sleep(0.1)
                try:
                    state = await self._read_node("trigger_state")
                    if state == 0:  # WAIT_FOR_TRIGGER - read complete
                        break
                    if state == 6:  # ERROR state (assuming 6 is ERROR based on enum)
                        raise ThermalVacError("PLC file read error: State indicates error")
                    if state == 5:  # FILE_CLOSE - about to complete
                        await asyncio.sleep(0.1)
                        continue
                except Exception as read_error:
                    # If we can't read the state, continue polling
                    if attempt > 10:  # Only log after a few attempts
                        raise ThermalVacError(f"Cannot read PLC state: {read_error}")
                    continue

            # Read the file content
            content = await self._read_node("get_file_content")
            return str(content) if content else ""
        except Exception as e:
            error_msg = str(e)
            if "BadNodeIdUnknown" in error_msg or "does not exist" in error_msg:
                raise ThermalVacError(
                    "PLC OPC-UA nodes not exposed. Please modify PLC code to expose:\n"
                    "- GVL.fbReadFileContents.sFilePath\n"
                    "- GVL.fbReadFileContents.eReadState\n"
                    "- GVL.fbReadFileContents.sFileContent\n"
                    "See PLC_MODIFICATIONS_NEEDED.md for instructions."
                )
            raise ThermalVacError(f"Failed to read file from PLC: {error_msg}")

    # Scanning

    def is_running(self) -> bool:
        """Checks whether a scan is running or not.

        Returns:
            True if scan is running or not, False otherwise.
        """

        return self._running

    def start_scan(self) -> None:
        """Starts a scan.

        Note that this resets the scan index (to 0).
        """

        self._running = True
        self._scan_index = 0

    def stop_scan(self) -> None:
        """Stops the scan if one is running."""

        self._running = False

    async def read_buffer_chunk(self) -> dict[str, Any]:
        """Gathers all ThermalVac housekeeping information during a scan.

        Returns:
            Dictionary with all ThermalVac housekeeping information if a scan is running, an empty dictionary otherwise.
        """

        # Simulate blocking hardware I/O call.
        await asyncio.sleep(min(SAMPLE_INTERVAL, 0.2))  # TODO Do we need this?

        if not self.is_running():
            return {}

        self._scan_index += 1

        raw_tvac_state = await self.get_tvac_state()

        temperatures = await self.get_temperatures()
        dut_temperatures = await self.get_dut_temperatures()
        dut_temperature_weights = await self.get_dut_temperature_weights()

        chunk = {
            "vacuum_gauge_powered": await self.is_vacuum_gauge_powered(),
            "vacuum_gauge_error": await self.is_vacuum_gauge_error(),
            "vessel_pressure": await self.get_vessel_pressure(),
            "vessel_pressure_filtered": await self.get_filtered_vessel_pressure(),
            "temperature1": float(temperatures[0]),
            "temperature2": float(temperatures[1]),
            "dut_temperature1": float(dut_temperatures[0]),
            "dut_temperature2": float(dut_temperatures[1]),
            "dut_temperature3": float(dut_temperatures[2]),
            "dut_temp_sensor_weight1": int(dut_temperature_weights[0]),
            "dut_temp_sensor_weight2": int(dut_temperature_weights[1]),
            "dut_temp_sensor_weight3": int(dut_temperature_weights[2]),
            "average_temperature": await self.get_avg_temperature(),
            "temperature_setpoint": await self.get_temperature_setpoint(),
            "pid_output_cooling": await self.get_pid_output_cooling(),
            "pid_output_heating": await self.get_pid_output_heating(),
            "temperature_ctrl_active": await self.is_temperature_ctrl_active(),
            "scroll_pump_running": await self.is_scroll_pump_running(),
            "scroll_pump_alarm": await self.is_scroll_pump_alarm(),
            "turbo_pump_rpm": await self.get_turbo_pump_rpm(),
            "turbo_pump_error": await self.is_turbo_pump_error(),
            "tvac_state_code": raw_tvac_state,
            "tvac_state_text": tvac_state_to_string(raw_tvac_state),
            "data_logging_active": await self.is_data_logging_active(),
            "data_logging_state": await self.get_data_logging_state(),
            "data_logging_error": await self.is_data_logging_error(),
            "data_logging_error_id": await self.get_data_logging_error_id(),
            "data_logging_filename": await self.get_data_logging_filename(),
            "data_logging_directory": await self.get_data_logging_directory(),
        }

        return chunk


class ThermalVacController(DeviceCommandRouter):
    ALLOWED_DURING_SCAN: set[str] = {"scan-status", "stop-scan", "get-latest"}

    def __init__(self, control_server: ThermalVacControlServer):
        """Initialisation of the ThermalVac Controller.

        Args:
            control_server (ThermalVacControlServer): ThermalVac Control Server.
        """

        super().__init__(control_server)

        self._cs = control_server
        self.daq = ThermalVacDaq()
        self.scan_task: asyncio.Task | None = None
        self.scan_stop_event = asyncio.Event()

    def register_handlers(self) -> None:
        """Registers all handlers for the ThermalVac."""

        self.add_handler("start-scan", self.do_start_scan)
        self.add_handler("stop-scan", self.do_stop_scan)
        self.add_handler("scan-status", self.do_scan_status)

        self.add_handler("get-latest", self.do_get_latest)

        self.add_handler("is-vacuum-gauge-powered", self.do_is_vacuum_gauge_powered)
        self.add_handler("is-vacuum-gauge-error", self.do_is_vacuum_gauge_error)
        self.add_handler("get-vessel-pressure", self.do_get_vessel_pressure)
        self.add_handler("get-filtered-vessel-pressure", self.do_get_filtered_vessel_pressure)
        self.add_handler("get-temperatures", self.do_get_temperatures)
        self.add_handler("get-temperature1", self.do_get_temperature1)
        self.add_handler("get-temperature2", self.do_get_temperature2)
        self.add_handler("get-dut-temperatures", self.do_get_dut_temperatures)
        self.add_handler("get-dut-temperature1", self.do_get_dut_temperature1)
        self.add_handler("get-dut-temperature2", self.do_get_dut_temperature2)
        self.add_handler("get-dut-temperature3", self.do_get_dut_temperature3)
        self.add_handler("get-dut-temperature-weights", self.do_get_dut_temperature_weights)
        self.add_handler("get-dut-temperature-weight1", self.do_get_dut_temperature_weight1)
        self.add_handler("get-dut-temperature-weight2", self.do_get_dut_temperature_weight2)
        self.add_handler("get-dut-temperature-weight3", self.do_get_dut_temperature_weight3)
        self.add_handler("get-avg-temperature", self.do_get_avg_temperature)
        self.add_handler("get-temperature-setpoint", self.do_get_temperature_setpoint)
        self.add_handler("set-temperature-setpoint", self.do_set_temperature_setpoint)
        self.add_handler("get-pid-output-cooling", self.do_get_pid_output_cooling)
        self.add_handler("get-pid-output-heating", self.do_get_pid_output_heating)
        self.add_handler("is-temperature-ctrl-active", self.do_is_temperature_ctrl_active)
        self.add_handler("set-temperature-ctrl-active", self.do_set_temperature_ctrl_active)
        self.add_handler("enable-temperature-ctrl", self.do_enable_temperature_ctrl)
        self.add_handler("disable-temperature-ctrl", self.do_disable_temperature_ctrl)
        self.add_handler("is-scroll-pump-running", self.do_is_scroll_pump_running)
        self.add_handler("is-scroll-pump-alarm", self.do_is_scroll_pump_alarm)
        self.add_handler("get-turbo-pump-rpm", self.do_get_turbo_pump_rpm)
        self.add_handler("is-turbo-pump-error", self.do_is_turbo_pump_error)
        self.add_handler("get-tvac-state", self.do_get_tvac_state)
        self.add_handler("set-stop-pumps", self.do_set_stop_pumps)
        self.add_handler("start-pumps", self.do_start_pumps)
        self.add_handler("stop-pumps", self.do_stop_pumps)
        self.add_handler("is-data-logging-active", self.do_is_data_logging_active)
        self.add_handler("start-data-logging", self.do_start_data_logging)
        self.add_handler("stop-data-logging", self.do_stop_data_logging)
        self.add_handler("get-data-logging-state", self.do_get_data_logging_state)
        self.add_handler("is-data-logging-error", self.do_is_data_logging_error)
        self.add_handler("get-data-logging-error-id", self.do_get_data_logging_error_id)
        self.add_handler("get-data-logging-filename", self.do_get_data_logging_filename)
        self.add_handler("get-data-logging-directory", self.do_get_data_logging_directory)
        self.add_handler("read-file-from-plc", self.do_read_file_from_plc)

    def _deny_if_not_allowed_during_scan(self, command_name: str) -> list | None:
        """Checks whether the given command is allowed during a data acquisition scan.

        Returns:
            JSON response indicating the device is busy if the command is not allowed during a scan, None otherwise.
        """

        if self.is_scan_running() and command_name not in self.ALLOWED_DURING_SCAN:
            return zmq_json_response(
                {
                    "success": False,
                    "message": {
                        "error": "device-busy",
                        "state": "scanning",
                        "detail": f"Command '{command_name}' is blocked while scan is running.",
                        "allowed_during_scan": sorted(self.ALLOWED_DURING_SCAN),
                    },
                }
            )

        return None

    # noinspection PyUnusedLocal
    async def do_start_scan(self, cmd: dict[str, Any]) -> list:
        """Starts a data acquisition scan.

        The command will be rejected if a scan is already running to avoid conflicts.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that a data
            acquisition scan was started. Otherwise, a JSON response will be returned, indicating that a data
            acquisition scan was already ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("start-scan")
        if blocked:
            return blocked

        started = await self.start_scan()

        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "running": self.is_scan_running(),
                    "started": started,
                    "status": self.get_scan_status(),
                },
            }
        )

    # noinspection PyUnusedLocal
    async def do_stop_scan(self, cmd: dict[str, Any]) -> list:
        """Stops the data acquisition scan, if it is running.

        Returns:
            JSON response indicating that the data acquisition scan was stopped.
        """

        stopped = await self.stop_scan()

        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "stopped": stopped,
                    "status": self.get_scan_status(),
                },
            }
        )

    # noinspection PyUnusedLocal
    async def do_scan_status(self, cmd: dict[str, Any]) -> list:
        """Checks the status of the data acquisition scan.

        Returns:
            JSON response indicating the status of the data acquisition scan.
        """

        return zmq_json_response({"success": True, "message": self.get_scan_status()})

    # noinspection PyUnusedLocal
    async def do_get_latest(self, cmd: dict[str, Any]) -> list:
        """Retrieves the latest data acquisition scan.

        Returns:
            JSON response indicating whether the latest data acquisition scan was successful.
        """

        return zmq_json_response({"success": True, "message": {"latest": self._cs.latest_sample}})

    # noinspection PyUnusedLocal
    async def do_is_vacuum_gauge_powered(self, cmd: dict[str, Any]) -> list:
        """Checks whether the thermal vacuum gauge is powered.

        Returns:
            JSON response indicating whether the thermal vacuum gauge is powered or not.
        """

        vacuum_gauge_powered = await self.daq.is_vacuum_gauge_powered()
        return zmq_json_response({"success": True, "message": {"vacuum_gauge_powered": vacuum_gauge_powered}})

    # noinspection PyUnusedLocal
    async def do_is_vacuum_gauge_error(self, cmd: dict[str, Any]) -> list:
        """Checks whether the thermal vacuum gauge shows an error.

        Returns:
            JSON response indicating whether the thermal vacuum gauge shows an error or not.
        """

        vacuum_gauge_error = await self.daq.is_vacuum_gauge_error()
        return zmq_json_response({"success": True, "message": {"vacuum_gauge_error": vacuum_gauge_error}})

    # noinspection PyUnusedLocal
    async def do_get_vessel_pressure(self, cmd: dict[str, Any]) -> list:
        """Retrieves the vessel pressure.

        Returns:
            JSON response indicating the vessel pressure [mbar].
        """

        vessel_pressure = await self.daq.get_vessel_pressure()
        return zmq_json_response({"success": True, "message": {"vessel_pressure": vessel_pressure}})

    # noinspection PyUnusedLocal
    async def do_get_filtered_vessel_pressure(self, cmd: dict[str, Any]) -> list:
        """Retrieves the filtered vessel pressure.

        Returns:
            JSON response indicating the filtered vessel pressure [mbar].
        """

        filtered_vessel_pressure = await self.daq.get_filtered_vessel_pressure()
        return zmq_json_response({"success": True, "message": {"filtered_vessel_pressure": filtered_vessel_pressure}})

    # noinspection PyUnusedLocal
    async def do_get_temperatures(self, cmd: dict[str, Any]) -> list:
        """Retrieves the temperature readings of the vacuum chamber.

        Returns:
            JSON response indicating the temperature readings of the vacuum chamber [°C].
        """

        temperatures = await self.daq.get_temperatures()
        return zmq_json_response({"success": True, "message": {"temperatures": temperatures}})

    # noinspection PyUnusedLocal
    async def do_get_temperature1(self, cmd: dict[str, Any]) -> list:
        """Retrieves the temperature reading of the first temperature sensor in the vacuum chamber.

        Returns:
            JSON response indicating the temperature reading of the first temperature sensor in the vacuum chamber [°C].
        """

        temperature1 = await self.daq.get_temperature1()
        return zmq_json_response({"success": True, "message": {"temperature1": temperature1}})

    # noinspection PyUnusedLocal
    async def do_get_temperature2(self, cmd: dict[str, Any]) -> list:
        """Retrieves the temperature reading of the second temperature sensor in the vacuum chamber.

        Returns:
            JSON response indicating the temperature reading of the second temperature sensor in the vacuum chamber [°C].
        """

        temperature2 = await self.daq.get_temperature2()
        return zmq_json_response({"success": True, "message": {"temperature2": temperature2}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperatures(self, cmd: dict[str, Any]) -> list:
        """Retrieves the temperature readings of the Device Under Test (DUT).

        Returns:
            JSON response indicating the temperature readings of the Device Under Test (DUT) [°C].
        """

        dut_temperatures = await self.daq.get_dut_temperatures()
        return zmq_json_response({"success": True, "message": {"dut_temperatures": dut_temperatures}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperature1(self, cmd: dict[str, Any]) -> list:
        """Retrieves the temperature reading of the first temperature sensor of the Device Under Test (DUT).

        Returns:
            JSON response indicating the temperature reading of the first temperature sensor of the Device Under Test
            (DUT) [°C].
        """

        dut_temperature1 = await self.daq.get_dut_temperature1()
        return zmq_json_response({"success": True, "message": {"dut_temperature1": dut_temperature1}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperature2(self, cmd: dict[str, Any]) -> list:
        """Retrieves the temperature reading of the second temperature sensor of the Device Under Test (DUT).

        Returns:
            JSON response indicating the temperature reading of the second temperature sensor of the Device Under Test
            (DUT) [°C].
        """

        dut_temperature2 = await self.daq.get_dut_temperature2()
        return zmq_json_response({"success": True, "message": {"dut_temperature2": dut_temperature2}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperature3(self, cmd: dict[str, Any]) -> list:
        """Retrieves the temperature reading of the third temperature sensor of the Device Under Test (DUT).

        Returns:
            JSON response indicating the temperature reading of the third temperature sensor of the Device Under Test
            (DUT) [°C].
        """

        dut_temperature3 = await self.daq.get_dut_temperature3()
        return zmq_json_response({"success": True, "message": {"dut_temperature3": dut_temperature3}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperature_weights(self, cmd: dict[str, Any]) -> list:
        """Retrieves the list of weights for the temperature sensors of the Device Under Test (DUT).

        Returns:
            JSON response indicating the list of weights for the temperature sensors of the Device Under Test (DUT).
        """

        dut_temperature_weights = await self.daq.get_dut_temperature_weights()
        return zmq_json_response({"success": True, "message": {"dut_temperature_weights": dut_temperature_weights}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperature_weight1(self, cmd: dict[str, Any]) -> list:
        """Retrieves the weight for the first temperature sensor of the Device Under Test (DUT).

        Returns:
            JSON response indicating the weight for the first temperature sensor of the Device Under Test (DUT).
        """

        dut_temperature_weight1 = await self.daq.get_dut_temperature_weight1()
        return zmq_json_response({"success": True, "message": {"dut_temperature_weight1": dut_temperature_weight1}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperature_weight2(self, cmd: dict[str, Any]) -> list:
        """Retrieves the weight for the second temperature sensor of the Device Under Test (DUT).

        Returns:
            JSON response indicating the weight for the second temperature sensor of the Device Under Test (DUT).
        """

        dut_temperature_weight2 = await self.daq.get_dut_temperature_weight2()
        return zmq_json_response({"success": True, "message": {"dut_temperature_weight2": dut_temperature_weight2}})

    # noinspection PyUnusedLocal
    async def do_get_dut_temperature_weight3(self, cmd: dict[str, Any]) -> list:
        """Retrieves the weight for the third temperature sensor of the Device Under Test (DUT).

        Returns:
            JSON response indicating the weight for the third temperature sensor of the Device Under Test (DUT).
        """

        dut_temperature_weight3 = await self.daq.get_dut_temperature_weight3()
        return zmq_json_response({"success": True, "message": {"dut_temperature_weight3": dut_temperature_weight3}})

    # noinspection PyUnusedLocal
    async def do_get_avg_temperature(self, cmd: dict[str, Any]) -> list:
        """Retrieves the average temperature.

        Returns:
            JSON response indicating the average temperature [°C].
        """

        avg_temperature = await self.daq.get_avg_temperature()
        return zmq_json_response({"success": True, "message": {"avg_temperature": avg_temperature}})

    # noinspection PyUnusedLocal
    async def do_get_temperature_setpoint(self, cmd: dict[str, Any]) -> list:
        """Retrieves the setpoint.

        Returns:
            JSON response indicating the temperature setpoint.
        """

        temperature_setpoint = await self.daq.get_temperature_setpoint()
        return zmq_json_response({"success": True, "message": {"temperature_setpoint": temperature_setpoint}})

    async def do_set_temperature_setpoint(self, cmd: dict[str, Any]) -> list:
        """Sets the temperature setpoint.

        Args:
            cmd (dict): Dictionary containing the temperature setpoint.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating the temperature
            setpoint. Otherwise, a JSON response will be returned, indicating that a data acquisition scan was ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("set-temperature-setpoint")
        if blocked:
            return blocked

        temperature_setpoint = float(cmd["temperature_setpoint"])
        await self.daq.set_temperature_setpoint(temperature_setpoint)

        return zmq_json_response({"success": True, "message": {"temperature_setpoint": temperature_setpoint}})

    # noinspection PyUnusedLocal
    async def do_get_pid_output_cooling(self, cmd: dict[str, Any]) -> list:
        """Retrieves the PID output for cooling.

        A PID output for cooling adjusts a system's output power based on the temperature error. It continuously
        calculates three factors to achieve precise, steady-state temperature control:
            -Proportional (P): Output based on the current gap between the actual temperature and the setpoint.
            - Integral (I): Output based on the duration of past errors to prevent steady-state offsets.
            - Derivative (D): Output based on the rate of change to prevent overshoot and system oscillations.

        Returns:
            JSON response indicating the PID output for cooling [%].
        """

        pid_output_cooling = await self.daq.get_pid_output_cooling()
        return zmq_json_response({"success": True, "message": {"pid_output_cooling": pid_output_cooling}})

    # noinspection PyUnusedLocal
    async def do_get_pid_output_heating(self, cmd: dict[str, Any]) -> list:
        """Retrieves the PID output for heating.

        A PID output for heating adjusts a system's output power based on the temperature error. It continuously
        calculates three factors to achieve precise, steady-state temperature control:
            -Proportional (P): Output based on the current gap between the actual temperature and the setpoint.
            - Integral (I): Output based on the duration of past errors to prevent steady-state offsets.
            - Derivative (D): Output based on the rate of change to prevent overshoot and system oscillations.

        Returns:
            JSON response indicating the PID output for heating [%].
        """

        pid_output_heating = await self.daq.get_pid_output_heating()
        return zmq_json_response({"success": True, "message": {"pid_output_heating": pid_output_heating}})

    # noinspection PyUnusedLocal
    async def do_is_temperature_ctrl_active(self, cmd: dict[str, Any]) -> list:
        """Checks if the temperature controlling is active or not.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the temperature
            control was activated/de-activated. Otherwise, a JSON response will be returned, indicating that a data
            acquisition scan was ongoing.
        """

        temperature_ctrl_active = await self.daq.is_temperature_ctrl_active()
        return zmq_json_response({"success": True, "message": {"temperature_ctrl_active": temperature_ctrl_active}})

    async def do_set_temperature_ctrl_active(self, cmd: dict[str, Any]) -> list:
        """Activates/de-activates the temperature control.

        Args:
            cmd (dict): Dictionary in which it is specified whether the temperature control should be activated or
                        de-activated.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the temperature
            control was activated/de-activated. Otherwise, a JSON response will be returned, indicating that a data
            acquisition scan was ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("set-temperature-ctrl-active")
        if blocked:
            return blocked

        temperature_ctrl_active = cmd.get("active", True)
        await self.daq.set_temperature_ctrl_active(temperature_ctrl_active)

        return zmq_json_response({"success": True, "message": {"temperature_ctrl_active": temperature_ctrl_active}})

    # noinspection PyUnusedLocal
    async def do_enable_temperature_ctrl(self, cmd: dict[str, Any]) -> list:
        """Activates the temperature control.

        Args:
            cmd (dict): Dictionary containing the temperature controlling to be activated.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the temperature
            control was activated. Otherwise, a JSON response will be returned, indicating that a data acquisition scan
            was ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("enable-temperature-ctrl")
        if blocked:
            return blocked

        await self.daq.enable_temperature_ctrl()
        return zmq_json_response({"success": True, "message": {"temperature_ctrl_active": True}})

    # noinspection PyUnusedLocal
    async def do_disable_temperature_ctrl(self, cmd: dict[str, Any]) -> list:
        """De-activates the temperature control.

        Args:
            cmd (dict): Dictionary containing the temperature controlling to be activated.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the temperature
            control was de-activated. Otherwise, a JSON response will be returned, indicating that a data acquisition
            scan was ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("disable-temperature-ctrl")
        if blocked:
            return blocked

        await self.daq.disable_temperature_ctrl()
        return zmq_json_response({"success": True, "message": {"temperature_ctrl_active": False}})

    # noinspection PyUnusedLocal
    async def do_is_scroll_pump_running(self, cmd: dict[str, Any]) -> list:
        """Checks if the scroll pump is running or not.

        Returns:
            JSON response indicating if the scroll pump is running or not.
        """

        scroll_pump_running = await self.daq.is_scroll_pump_running()
        return zmq_json_response({"success": True, "message": {"scroll_pump_running": scroll_pump_running}})

    # noinspection PyUnusedLocal
    async def do_is_scroll_pump_alarm(self, cmd: dict[str, Any]) -> list:
        """Checks if the scroll pump is alarm or not.

        Returns:
            JSON response indicating if the scroll pump shows an alarm or not.
        """

        scroll_pump_alarm = await self.daq.is_scroll_pump_alarm()
        return zmq_json_response({"success": True, "message": {"scroll_pump_alarm": scroll_pump_alarm}})

    # noinspection PyUnusedLocal
    async def do_get_turbo_pump_rpm(self, cmd: dict[str, Any]) -> list:
        """Retrieves the speed of the turbo pump.

        Returns:
            JSON response indicating the speed of the turbo pump [rpm].
        """

        turbo_pump_rpm = await self.daq.get_turbo_pump_rpm()
        return zmq_json_response({"success": True, "message": {"turbo_pump_rpm": turbo_pump_rpm}})

    # noinspection PyUnusedLocal
    async def do_is_turbo_pump_error(self, cmd: dict[str, Any]) -> list:
        """Checks if the turbo pump shows an error or not.

        Returns:
            JSON response indicating if the turbo pump shows an error or not.
        """

        turbo_pump_error = await self.daq.is_turbo_pump_error()
        return zmq_json_response({"success": True, "message": {"turbo_pump_error": turbo_pump_error}})

    # noinspection PyUnusedLocal
    async def do_get_tvac_state(self, cmd: dict[str, Any]) -> list:
        """Retrieves the state of the TVAC.

        Returns:
            JSON response indicating the state of the TVAC.
        """

        tvac_state = await self.daq.get_tvac_state()
        return zmq_json_response({"success": True, "message": {"tvac_state": tvac_state}})

    async def do_set_stop_pumps(self, cmd: dict[str, Any]) -> list:
        """Starts or stops the pumps.

        Args:
            cmd (dict): Dictionary in which it is specified whether the pumps should be stopped or started.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the pumps were
            stopped/started. Otherwise, a JSON response will be returned, indicating that a data acquisition scan was
            ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("set-stop-pumps")
        if blocked:
            return blocked

        stop = cmd.get("stop", True)
        await self.daq.set_stop_pumps(stop)
        return zmq_json_response({"success": True, "message": {"pumps_stopped": stop}})

    # noinspection PyUnusedLocal
    async def do_start_pumps(self, cmd: dict[str, Any]) -> list:
        """Starts the pumps.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the pumps were
            started. Otherwise, a JSON response will be returned, indicating that a data acquisition scan was ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("start-pumps")
        if blocked:
            return blocked

        await self.daq.start_pumps()
        return zmq_json_response({"success": True, "message": {"pumps_stopped": False}})

    # noinspection PyUnusedLocal
    async def do_stop_pumps(self, cmd: dict[str, Any]) -> list:
        """Stops the pumps.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the pumps were
            stopped. Otherwise, a JSON response will be returned, indicating that a data acquisition scan was ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("stop-pumps")
        if blocked:
            return blocked

        await self.daq.stop_pumps()
        return zmq_json_response({"success": True, "message": {"pumps_stopped": True}})

    # noinspection PyUnusedLocal
    async def do_is_data_logging_active(self, cmd: dict[str, Any]) -> list:
        """Checks if the data logging is active or not.

        Returns:
            JSON response indicating if the data logging is active or not.
        """

        is_data_logging_active = await self.daq.is_data_logging_active()
        return zmq_json_response({"success": True, "message": {"is_data_logging_active": is_data_logging_active}})

    # noinspection PyUnusedLocal
    async def do_start_data_logging(self, cmd: dict[str, Any]) -> list:
        """Starts the data logging.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the data logging
            was started. Otherwise, a JSON response will be returned, indicating that a data acquisition scan was
            ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("start-data-logging")
        if blocked:
            return blocked

        await self.daq.start_data_logging()
        return zmq_json_response({"success": True, "message": {"data_logging_started": True}})

    # noinspection PyUnusedLocal
    async def do_stop_data_logging(self, cmd: dict[str, Any]) -> list:
        """Stops the data logging.

        Returns:
            If no data acquisition scan was running, a JSON response will be returned, indicating that the data logging
            was stopped. Otherwise, a JSON response will be returned, indicating that a data acquisition scan was
            ongoing.
        """

        blocked = self._deny_if_not_allowed_during_scan("stop-data-logging")
        if blocked:
            return blocked

        await self.daq.stop_data_logging()
        return zmq_json_response({"success": True, "message": {"data_logging_stopped": True}})

    # noinspection PyUnusedLocal
    async def do_get_data_logging_state(self, cmd: dict[str, Any]) -> list:
        """Retrieves the data logging state.

        Returns:
            JSON response indicating if the data logging is active or not.
        """

        data_logging_state = await self.daq.get_data_logging_state()
        return zmq_json_response({"success": True, "message": {"data_logging_state": data_logging_state}})

    # noinspection PyUnusedLocal
    async def do_is_data_logging_error(self, cmd: dict[str, Any]) -> list:
        """Checks if the data logging shows an error or not.

        Returns:
            JSON response indicating if the data logging shows an error or not.
        """

        data_logging_error = await self.daq.is_data_logging_error()
        return zmq_json_response({"success": True, "message": {"data_logging_error": data_logging_error}})

    # noinspection PyUnusedLocal
    async def do_get_data_logging_error_id(self, cmd: dict[str, Any]) -> list:
        """Retrieves the error ID of the data logging.

        Returns:
            JSON response indicating the error ID of the data logging.
        """

        data_logging_error_id = await self.daq.get_data_logging_error_id()
        return zmq_json_response({"success": True, "message": {"data_logging_error_id": data_logging_error_id}})

    # noinspection PyUnusedLocal
    async def do_get_data_logging_filename(self, cmd: dict[str, Any]) -> list:
        """Retrieves the filename of the data logging.

        Returns:
            JSON response indicating the filename of the data logging.
        """

        data_logging_filename = await self.daq.get_data_logging_filename()
        return zmq_json_response({"success": True, "message": {"data_logging_filename": data_logging_filename}})

    # noinspection PyUnusedLocal
    async def do_get_data_logging_directory(self, cmd: dict[str, Any]) -> list:
        """Retrieves the directory of the data logging.

        Returns:
            JSON response indicating the directory of the data logging.
        """

        data_logging_directory = await self.daq.get_data_logging_directory()
        return zmq_json_response({"success": True, "message": {"data_logging_directory": data_logging_directory}})

    async def do_read_file_from_plc(self, cmd: dict[str, Any]) -> list:
        """Reads a PLC file.

        Args:
            cmd (dict): Dictionary containing the path to the PLC file.

        Returns:
            JSON response indicating the content of the PLC file.

        Raises:
            ThermalVacError when the PLC file cannot be read.
        """

        file_path = cmd.get("file_path", "")
        content = await self.daq.read_file_from_plc(file_path)
        return zmq_json_response({"success": True, "message": {"content": content}})

    def is_scan_running(self) -> bool:
        """Checks if the data acquisition scan is running.

        Returns:
            True if the data acquisition scan is running, False otherwise.
        """

        task = self.scan_task
        return task is not None and not task.done()

    def get_scan_status(self) -> dict[str, Any]:
        """Returns the status of the data acquisition scan.

        Returns:
            Status of the data acquisition scan.
        """

        return {
            "running": self.is_scan_running(),
            "daq running": self.daq.is_running(),
            "task": {
                "name": self.scan_task.get_name() if self.scan_task is not None else None,
                "done": self.scan_task.done() if self.scan_task is not None else True,
                "cancelled": self.scan_task.cancelled() if self.scan_task is not None else False,
            },
        }

    async def start_scan(self) -> bool:
        """Starts the data acquisition scan.

        The scan is started in the background and runs until `stop_scan()` is called.

        Returns:
            True if the data acquisition scan was started, False if a data acquisition scan was already running.
        """

        # No need to do anything when a scan is already running

        if self.is_scan_running():
            return False

        # Clear the flag that is set by the `stop_scan` co-routine (as a way to request to stop the scan)
        # This boils down to acknowledging that such an event had been set and taking action accordingly, while
        # listening for such events in the future

        self.scan_stop_event.clear()

        # From now onwards, `read_buffer_chunk` will return an empty dictionary

        await asyncio.to_thread(self.daq.start_scan)

        # Start the actual scan

        self.scan_task = asyncio.create_task(
            self._run_scan_loop(),
            name="tvac-buffered-scan",
        )

        return True

    async def stop_scan(self) -> bool:
        """Stops the data acquisition scan.

        Returns:
            True if the data acquisition scan was stopped, False if no data acquisition scan was not running.
        """

        was_running = self.is_scan_running() or self.daq.is_running()

        # Set the flag, indicating that a request was made to stop the scan

        self.scan_stop_event.set()

        await asyncio.to_thread(self.daq.stop_scan)

        # Stop the scan task

        task = self.scan_task
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
            self.scan_task = None

        return was_running

    async def _run_scan_loop(self) -> None:
        """Data acquisition scan loop.

        When calling `start_scan`, this co-routine is schedule (in a spawn task), meaning that - in a loop - the DAQ
        acquires the data in a dictionary, which is handled by the `on_acquisition_data` method of the Control Server.
        This keeps on going as long as the DAQ is running and as long as the `stop_scan` co-routine has not been called.

        A failed read (e.g. the OPC UA connection to the device dropped) does not end the scan: it's retried with
        a growing backoff (capped at `SCAN_RETRY_BACKOFF_MAX`) until it succeeds or the scan is stopped, so an
        unattended scan self-heals from a transient device outage instead of silently dying.
        """

        backoff = SAMPLE_INTERVAL

        try:
            while not self.scan_stop_event.is_set() and self.daq.is_running():
                # Data acquisition -> Dictionary with the data

                try:
                    data = await self.daq.read_buffer_chunk()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._cs.logger.error(
                        f"Buffered scan loop: read failed ({exc}); retrying in {backoff:.0f}s", exc_info=True
                    )
                    try:
                        await asyncio.wait_for(self.scan_stop_event.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass
                    backoff = min(backoff * 2, SCAN_RETRY_BACKOFF_MAX)
                    continue

                backoff = SAMPLE_INTERVAL

                # Now handle the data by passing it to `on_acquisition_data`

                self._cs.on_acquisition_data(data, source="tvac-buffer", metadata={"mode": "buffered-scan"})

                await asyncio.sleep(SAMPLE_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._cs.logger.error(f"Buffered scan loop failed: {exc}", exc_info=True)
        finally:
            await asyncio.to_thread(self.daq.stop_scan)


class ThermalVacServices(ServiceCommandRouter):
    def __init__(self, control_server: ThermalVacControlServer):
        """Initialisation of ThermalVac services.

        Args:
            control_server (ThermalVacControlServer): ThermalVac Control Server.
        """

        super().__init__(control_server)
        self._cs = control_server

    def register_handlers(self) -> None:
        """Registers handlers for the ThermalVac service commands."""

        self.add_handler("health", self._health)

    # noinspection PyUnusedLocal
    async def _health(self, cmd: dict[str, Any]) -> list:
        """Health command handler.

        Returns:
            JSON response indicating the health of the ThermalVac Control Server.
        """

        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "status": "ok",
                    "written_csv": self._cs.csv_count,
                    "sent_metrics": self._cs.metrics_count,
                    "failed_metrics": self._cs.metrics_failed_count,
                },
            }
        )


class ThermalVacControlServer(AcquisitionAsyncControlServer):
    service_type = SERVICE_TYPE
    service_name = SERVICE_NAME

    def __init__(self):
        """Initialisation of ThermalVac Control Server."""

        self.csv_count = 0
        self.metrics_count = 0
        self.metrics_failed_count = 0
        self.latest_sample: dict[str, Any] = {}
        self._metrics_sender: AsyncMetricsHubSender | None = None

        super().__init__()

        # Buffered scans can produce bursts; optional batching helps reduce overhead.
        # These variables are used in the acquisition pipeline to control batch behaviour.
        self.acquisition_batch_enabled = True
        self.acquisition_batch_max_size = 200

        # We prefer using the column names as defined in the telemetry dictionary, rather than the original ones.  If
        # there are no entries in the telemetry dictionary for the ThermalVac, we keep the original names.

        # noinspection PyBroadException
        try:
            self.hk_conversion_dict = read_conversion_dict(STORAGE_MNEMONIC, use_site=False, setup=load_setup())
        except:
            self.hk_conversion_dict = None

    # noinspection PyMethodMayBeStatic
    def get_storage_mnemonic(self) -> str:
        """Returns the storage mnemonic for the ThermalVac Control Server.

        Returns:
            Storage mnemonic for the ThermalVac Control Server.
        """

        return STORAGE_MNEMONIC

    # noinspection PyMethodMayBeStatic
    def is_storage_manager_active(self) -> bool:
        """Checks whether the Storage Manager is active or not.

        Returns:
            True if the Storage Manager is active, False otherwise.
        """

        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def register_to_storage_manager(self) -> None:
        """Registers the Thermal Vac Control Server to the Storage Manager."""

        from egse.storage import register_to_storage_manager
        from egse.storage.persistence import TYPES

        column_names = [
            "timestamp",
            "vacuum_gauge_powered",
            "vacuum_gauge_error",
            "vessel_pressure",
            "vessel_pressure_filtered",
            "temperature1",
            "temperature2",
            "dut_temperature1",
            "dut_temperature2",
            "dut_temperature3",
            "dut_temp_sensor_weight1",
            "dut_temp_sensor_weight2",
            "dut_temp_sensor_weight3",
            "average_temperature",
            "temperature_setpoint",
            "pid_output_cooling",
            "pid_output_heating",
            "temperature_ctrl_active",
            "scroll_pump_running",
            "scroll_pump_alarm",
            "turbo_pump_rpm",
            "turbo_pump_error",
            "tvac_state_code",
            "tvac_state_text",
            "data_logging_active",
            "data_logging_state",
            "data_logging_error",
            "data_logging_error_id",
            "data_logging_filename",
            "data_logging_directory",
        ]

        # Convert the column names to use them as defined in the telemetry dictionary.  For the columns for which there
        # is no entry in the telemetry dictionary for the ThermalVac, we use the original name.

        if self.hk_conversion_dict:
            column_names = [self.hk_conversion_dict.get(col, col) for col in column_names]

        register_to_storage_manager(
            origin=self.get_storage_mnemonic(),
            persistence_class=TYPES["CSV"],
            prep={
                "column_names": list(column_names),
                "mode": "a",
            },
        )

    def unregister_from_storage_manager(self) -> None:
        """Unregisters the Thermal Vac Control Server from the Storage Manager."""

        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=self.get_storage_mnemonic())

    def create_device_command_router(self) -> DeviceCommandRouter:
        """Creates the device command router for the ThermalVac Control Server.

        This command router is used for the device commands.

        Returns:
            Device command router for the ThermalVac Control Server.
        """

        return ThermalVacController(self)

    def create_service_command_router(self) -> ServiceCommandRouter:
        """Creates the service command router for the ThermalVac Control Server.

        This command router is used for the service commands.

        Returns:
            Service command router for the ThermalVac Control Server.
        """

        return ThermalVacServices(self)

    @property
    def controller(self) -> ThermalVacController:
        """Returns the controller for the ThermalVac Control Server.

        Returns:
            Controller (device command router) for the ThermalVac Control Server.
        """

        return self._device_command_router  # type: ignore[return-value]

    def get_component_status(self) -> dict[str, Any]:
        """Returns the component status of the ThermalVac Control Server.

        The returned status reports the state of the Control Server and its sinks, not live device telemetry.

        Returns:
            Component status of the ThermalVac Control Server.
        """

        components = super().get_component_status()

        components["scan"] = {
            **self.controller.get_scan_status(),
            "task": {
                "name": self.controller.scan_task.get_name() if self.controller.scan_task is not None else None,
                "done": self.controller.scan_task.done() if self.controller.scan_task is not None else True,
                "cancelled": (
                    self.controller.scan_task.cancelled() if self.controller.scan_task is not None else False
                ),
            },
            "stop_requested": self.controller.scan_stop_event.is_set(),
        }
        components["acquisition"] = {
            "queue_size": self._acquisition_queue.qsize(),
            "queue_maxsize": self.acquisition_queue_maxsize,
            "dropped": self.acquisition_dropped_count,
            "batch_enabled": self.acquisition_batch_enabled,
            "batch_size": self.acquisition_batch_max_size,
        }
        components["sinks"] = {
            "written_csv": self.csv_count,
            "sent_metrics": self.metrics_count,
            "failed_metrics": self.metrics_failed_count,
            "metrics_sender_connected": self._metrics_sender is not None,
        }

        return components

    async def handle_acquisition(
        self,
        data: Any,
        *,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Handles the data acquired during the data acquisition scan.

        Args:
            data (Any): Dictionary of data acquired during a data acquisition scan.
            source (str, None): Indicates where the data originate from.
            metadata (dict[str, Any], None): Metadata.
            timestamp (str, None): Timestamp at which the data acquisition scan started.
        """

        self.latest_sample = data

        timestamped_data = {"timestamp": timestamp or dt.datetime.now(dt.timezone.utc).isoformat()} | data

        # Convert the column names to use them as defined in the telemetry dictionary.  For the columns for which there
        # is no entry in the telemetry dictionary for the ThermalVac, we use the original name.

        if self.hk_conversion_dict:
            timestamped_data = convert_hk_names(timestamped_data, self.hk_conversion_dict)
        else:
            timestamped_data = timestamped_data

        # 1) Store to CSV (offload file I/O to thread)
        await asyncio.to_thread(self._append_csv_row, timestamped_data)
        self.csv_count += 1

        # 2) Send to metrics hub (replace with your real client call)
        sent = await self._send_metrics(timestamped_data, tags={"source": source or "TVAC"})
        if sent:
            self.metrics_count += 1
        else:
            self.metrics_failed_count += 1

    # noinspection PyMethodMayBeStatic
    def _append_csv_row(self, data: dict[str, Any]) -> None:
        """Appends the given data as a row to the CSV file.

        The keys in the given dictionary correspond to the column names, before a potential re-naming to make them
        compatible with the telemetry dictionary.

        Args:
            data (dict[str, Any]): Dictionary of data acquired during a data acquisition scan.
        """

        from egse.storage import store_housekeeping_information

        store_housekeeping_information(STORAGE_MNEMONIC, data)

    async def _send_metrics(self, data: dict[str, Any], tags: dict[str, str]) -> bool:
        """Propagates the given data to the metrics database.

        The keys in the given dictionary correspond to the column names in the CSV files, before a potential re-naming
        to make them compatible with the telemetry dictionary.

        Args:
            data (dict[str, Any]): Dictionary of data acquired during a data acquisition scan.

        Returns:
            True if the data was successfully sent, False otherwise.
        """

        # Best-effort metrics propagation: never block acquisition on sink failures.
        if self._metrics_sender is None:
            self._metrics_sender = AsyncMetricsHubSender()
            self._metrics_sender.connect()  # noqa

        try:
            point = (
                DataPoint.measurement(SERVICE_NAME)
                .tag("site_id", SITE_ID)
                .tag("origin", SERVICE_TYPE)
                .time(str_to_datetime(data["timestamp"]))
            )
            for hk_name, hk_value in data.items():
                if hk_name != "timestamp":
                    point.field(hk_name.lower(), hk_value)

            for key, tag_value in tags.items():
                if tag_value is not None:
                    point.tag(str(key), str(tag_value))

            return await self._metrics_sender.send(point)  # noqa
        except Exception as exc:
            self.logger.warning(f"Failed to send metric to Metrics Hub: {exc!r}")
            return False

    def create_background_tasks(self) -> list[asyncio.Task]:
        """Creates the base server tasks plus a task that connects to the OPC UA interface and starts scanning.

        `AsyncControlServer.start()` blocks in its own keep-alive loop until the server is stopped, so connecting
        to the OPC UA interface and starting the scan cannot be done by simply awaiting them after `super().start()`
        in `start()` below - that code would only run once the server is already shutting down. Instead, they run
        as one of the concurrently-scheduled background tasks, like the base class already does for its own tasks.
        """

        tasks = super().create_background_tasks()
        tasks.append(asyncio.create_task(self._connect_and_start_scan(), name="tvac-connect-and-start-scan"))
        return tasks

    async def _connect_and_start_scan(self) -> None:
        """Connects to the OPC UA interface and starts the data acquisition scan."""

        await self.controller.daq.connect_to_opcua()
        await self.controller.start_scan()

    async def start(self) -> None:
        """Starts the asynchronous ThermalVac Control Server.

        This includes:

            - Connecting to the OPC UA interface,
            - Starting a data acquisition scan.
        """

        multiprocessing.current_process().name = "tvac_cs"

        await super().start()

    def stop(self) -> None:
        """Stops the asynchronous ThermalVac Control Server.

        This includes:

            - Stopping the scanning,
            - Closing the connection to the metrics hub,
            - Closing the connection to the OPC UA interface.
        """

        if self.controller.is_scan_running() and self._loop is not None and self._loop.is_running():
            self._loop.create_task(self.controller.stop_scan())
        elif self.controller.daq.is_running():
            self.controller.daq.stop_scan()

        if self._metrics_sender is not None:
            self._metrics_sender.close()
            self._metrics_sender = None

        if self._loop is not None and self._loop.is_running():
            # `stop()` is invoked from the (async) "terminate" service command handler, i.e. from inside the
            # already-running event loop, so `asyncio.run()` would raise "cannot be called from a running
            # event loop". Schedule the disconnect on that loop instead.
            self._loop.create_task(self.controller.daq.disconnect_from_opcua())
        else:
            asyncio.run(self.controller.daq.disconnect_from_opcua())

        super().stop()


class ThermalVacControlClient(TypedAsyncControlClient):
    """Typed client wrapper for ThermalVacControlServer commands."""

    service_type = SERVICE_TYPE

    async def start_scan(self, *, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command(
            {
                "command": "start-scan",
            },
            timeout=timeout,
        )
        return self._success_message_as_dict(response, "start-scan")

    async def stop_scan(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command({"command": "stop-scan"}, timeout=timeout)
        return self._success_message_as_dict(response, "stop-scan")

    async def scan_status(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command({"command": "scan-status"}, timeout=timeout)
        return self._success_message_as_dict(response, "scan-status")

    async def get_latest(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command({"command": "get-latest"}, timeout=timeout)
        return self._success_message_as_dict(response, "get-latest")

    async def health(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_service_command("health", timeout=timeout)
        return self._success_message_as_dict(response, "health")

    async def _get_value(self, command: str, key: str, timeout: float | None = None):
        response = await self.send_device_command(command, timeout=timeout)

        return get_value_from_success_message(self._success_message_as_dict(response, command), key)

    async def is_vacuum_gauge_powered(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-vacuum-gauge-powered", "vacuum_gauge_powered", timeout=timeout))

    async def is_vacuum_gauge_error(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-vacuum-gauge-error", "vacuum_gauge_error", timeout=timeout))

    async def get_vessel_pressure(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-vessel-pressure", "vessel_pressure", timeout=timeout))

    async def get_filtered_vessel_pressure(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-filtered-vessel-pressure", "filtered_vessel_pressure", timeout=timeout))

    async def get_temperatures(self, timeout: float | None = None) -> list[float]:
        return await self._get_value("get-temperatures", "temperatures", timeout=timeout)

    async def get_temperature1(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-temperature1", "temperature1", timeout=timeout))

    async def get_temperature2(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-temperature2", "temperature2", timeout=timeout))

    async def get_dut_temperatures(self, timeout: float | None = None) -> list[float]:
        return await self._get_value("get-dut-temperatures", "dut_temperatures", timeout=timeout)

    async def get_dut_temperature1(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-dut-temperature1", "dut_temperature1", timeout=timeout))

    async def get_dut_temperature2(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-dut-temperature2", "dut_temperature2", timeout=timeout))

    async def get_dut_temperature3(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-dut-temperature3", "dut_temperature3", timeout=timeout))

    async def get_dut_temperature_weights(self, timeout: float | None = None) -> list[int]:
        return await self._get_value("get-dut-temperature-weights", "dut_temperature_weights", timeout=timeout)

    async def get_dut_temperature_weight1(self, timeout: float | None = None) -> int:
        return int(await self._get_value("get-dut-temperature-weight1", "dut_temperature_weight1", timeout=timeout))

    async def get_dut_temperature_weight2(self, timeout: float | None = None) -> int:
        return int(await self._get_value("get-dut-temperature-weight2", "dut_temperature_weight2", timeout=timeout))

    async def get_dut_temperature_weight3(self, timeout: float | None = None) -> int:
        return int(await self._get_value("get-dut-temperature-weight3", "dut_temperature_weight3", timeout=timeout))

    async def get_avg_temperature(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-avg-temperature", "avg_temperature", timeout=timeout))

    async def get_temperature_setpoint(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-temperature-setpoint", "temperature_setpoint", timeout=timeout))

    async def set_temperature_setpoint(self, temperature_setpoint: float, timeout: float | None = None) -> None:
        await self.send_device_command(
            {"command": "set-temperature-setpoint", "temperature_setpoint": temperature_setpoint}, timeout=timeout
        )
        # TODO Do I really need to return something here?

    async def get_pid_output_cooling(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-pid-output-cooling", "pid_output_cooling", timeout=timeout))

    async def get_pid_output_heating(self, timeout: float | None = None) -> float:
        return float(await self._get_value("get-pid-output-heating", "pid_output_heating", timeout=timeout))

    async def is_temperature_ctrl_active(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-temperature-ctrl-active", "temperature_ctrl_active", timeout=timeout))

    async def set_temperature_ctrl_active(self, active: bool, timeout: float | None = None) -> None:
        await self.send_device_command({"command": "set-temperature-ctrl-active", "active": active}, timeout=timeout)
        # TODO Do I really need to return something here?

    async def enable_temperature_ctrl(self, timeout: float | None = None) -> None:
        await self.send_device_command({"command": "enable-temperature-ctrl"}, timeout=timeout)
        # TODO Do I really need to return something here?

    async def disable_temperature_ctrl(self, timeout: float | None = None) -> None:
        await self.send_device_command("disable-temperature-ctrl", timeout=timeout)
        # TODO Do I really need to return something here?

    async def is_scroll_pump_running(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-scroll-pump-running", "scroll_pump_running", timeout=timeout))

    async def is_scroll_pump_alarm(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-scroll-pump-alarm", "scroll_pump_alarm", timeout=timeout))

    async def get_turbo_pump_rpm(self, timeout: float | None = None) -> int:
        return int(await self._get_value("get-turbo-pump-rpm", "turbo_pump_rpm", timeout=timeout))

    async def is_turbo_pump_error(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-turbo-pump-error", "turbo_pump_error", timeout=timeout))

    async def get_tvac_state(self, timeout: float | None = None) -> int:
        return int(await self._get_value("get-tvac-state", "tvac_state", timeout=timeout))

    async def set_stop_pumps(self, stop: bool, timeout: float | None = None) -> None:
        await self.send_device_command({"command": "set-stop-pumps", "stop": stop}, timeout=timeout)
        # TODO Do I really need to return something here?

    async def stop_pumps(self, timeout: float | None = None) -> None:
        await self.send_device_command("stop-pumps", timeout=timeout)
        # TODO Do I really need to return something here?

    async def start_pumps(self, timeout: float | None = None) -> None:
        await self.send_device_command("start-pumps", timeout=timeout)
        # TODO Do I really need to return something here?

    async def is_data_logging_active(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-data-logging-active", "is_data_logging_active", timeout=timeout))

    async def start_data_logging(self, timeout: float | None = None) -> None:
        await self.send_device_command("start-data-logging", timeout=timeout)
        # TODO Do I really need to return something here?

    async def stop_data_logging(self, timeout: float | None = None) -> None:
        await self.send_device_command("stop-data-logging", timeout=timeout)
        # TODO Do I really need to return something here?

    async def get_data_logging_state(self, timeout: float | None = None):
        return await self._get_value("get-data-logging-state", "data_logging_state", timeout=timeout)

    async def is_data_logging_error(self, timeout: float | None = None) -> bool:
        return bool(await self._get_value("is-data-logging-error", "data_logging_error", timeout=timeout))

    async def get_data_logging_error_id(self, timeout: float | None = None):
        return await self._get_value("get-data-logging-error-id", "data_logging_error_id", timeout=timeout)

    async def get_data_logging_filename(self, timeout: float | None = None) -> str:
        return await self._get_value("get-data-logging-filename", "data_logging_filename", timeout=timeout)

    async def get_data_logging_directory(self, timeout: float | None = None) -> str:
        return await self._get_value("get-data-logging-directory", "data_logging_directory", timeout=timeout)

    async def read_file_from_plc(self, file_path: str, timeout: float | None = None) -> str:
        response = await self.send_device_command(
            {"command": "read-file-from-plc", "file_path": file_path}, timeout=timeout
        )

        return get_value_from_success_message(self._success_message_as_dict(response, "read-file-from-plc"), "content")


def get_value_from_success_message(success_message_as_dict: dict[str, Any] | None, key: str) -> Any:
    if success_message_as_dict is None:
        raise ThermalVacError("Success message is empty")

    if key not in success_message_as_dict:
        raise ThermalVacError(f"Key {key} not found in success message ({success_message_as_dict})")

    return success_message_as_dict[key]


# ----- CLI Commands ------------------------------------------------------------------------------------------------

app = typer.Typer()


@app.command(cls=TyperAsyncCommand)
async def start():
    """Starts the asynchronous ThermalVac Control Server."""

    with remote_logging():
        try:
            control_server = ThermalVacControlServer()
            await control_server.start()
        except KeyboardInterrupt:
            print("Shutdown requested...exiting")
        except SystemExit as exit_code:
            print(f"System Exit with code {exit_code}.")
            sys.exit(-1)
        except Exception:  # noqa
            import traceback

            traceback.print_exc(file=sys.stdout)


@app.command(cls=TyperAsyncCommand)
async def stop():
    """Sends terminate command to the asynchronous ThermalVac Control Server.

    This includes:
        - Stopping the scanning,
        - Closing the connection to the metrics hub,
        - Closing the connection to the OPC UA interface.
    """

    console = Console()
    try:
        async with ThermalVacControlClient() as client:
            await client.stop_server()
    except Exception as exc:
        console.print(f"Error occurred while sending stop command: {exc}", style="red")


@app.command(cls=TyperAsyncCommand)
async def status():
    """Gets the status of the asynchronous ThermalVac Control Server."""

    console = Console()

    # noinspection PyBroadException
    try:
        async with ThermalVacControlClient() as client:
            info = await client.info()
            health = await client.health()
            scan = await client.scan_status()
            console.print({"info": info, "health": health, "scan": scan})
    except Exception:
        rich.print(
            f"[red]TVAC isn't registered as a service. I cannot contact the Control "
            f"Server without the required info from the service registry.[/]"
        )
        rich.print("TVAC: [red]not active")
        return


@app.command(cls=TyperAsyncCommand)
async def get_latest():
    """Prints the latest temperature readings from the asynchronous ThermalVac Control Server."""

    console = Console()
    try:
        async with ThermalVacControlClient() as client:
            latest = await client.get_latest()
            console.print({"latest": latest})
    except Exception as exc:
        console.print(f"Error occurred while fetching latest readings: {exc}", style="red")


if __name__ == "__main__":
    app()
