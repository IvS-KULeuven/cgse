"""
Keithley DAQ6510 Asynchronous Control Server.

The control server owns the connection to the DAQ6510. It runs a background scan on the instrument and keeps the
latest readings in memory, so requests are answered quickly, also while a scan is running.

Runtime model:

1. `start-scan` reads the scan configuration from the Setup (`gse.DAQ6510`), configures the instrument and starts
   a scan that repeats until it is aborted. The instrument stores the readings in its reading buffer.
2. A background task polls the buffer (`TRAC:ACT:END?`) and fetches only the new, complete scans with
   `TRAC:DATA?`. Each scan is passed to the acquisition pipeline of `AcquisitionAsyncControlServer`.
3. `handle_acquisition()` updates the latest readings, stores the scan with the Storage Manager and sends it to the
   Metrics Hub.
4. When the buffer is 90% full, the scan is restarted with an empty buffer. This avoids depending on the
   (unverified) index behaviour of a wrapped buffer, at the cost of a gap of at most one scan interval.

All communication with the instrument goes through one lock (the hardware lane), so a command and a buffer poll
never interleave on the socket.

While a scan is running, only read-only queries, `stop-scan` and `reset` are accepted. Other device commands are
rejected with a 'device-busy' error.

The control server is started from the command line:

    $ daq6510_cs start [--setup-file SETUP.yaml] [--auto-scan]

Use `daq6510_cs --help` to see all commands.
"""

__all__ = [
    "DAQ6510Client",
    "DAQ6510ControlServer",
    "DAQ6510Controller",
]

import asyncio
import datetime
import sys
from pathlib import Path
from typing import Any
from typing import Callable

import rich
import typer
from egse.async_control import AcquisitionAsyncControlServer
from egse.async_control import DeviceCommandRouter
from egse.async_control import ServiceCommandRouter
from egse.async_control import TypedAsyncControlClient
from egse.device import DeviceError
from egse.device import DeviceTimeoutError
from egse.log import logger
from egse.logger import remote_logging
from egse.metrics import DataPoint
from egse.metricshub.client import AsyncMetricsHubSender
from egse.settings import Settings
from egse.settings import get_site_id
from egse.system import TyperAsyncCommand
from egse.zmq_ser import zmq_json_response

from egse.tempcontrol.keithley.daq6510_adev import DAQ6510
from egse.tempcontrol.keithley.daq6510_adev import Reading
from egse.tempcontrol.keithley.daq6510_config import DEFAULT_BUFFER_CAPACITY
from egse.tempcontrol.keithley.daq6510_config import ScanConfig
from egse.tempcontrol.keithley.daq6510_config import scan_config_from_setup

cs_settings = Settings.load("Keithley Control Server")

SERVICE_TYPE = cs_settings.get("SERVICE_TYPE", "DAQ6510")
SERVICE_NAME = cs_settings.get("PROCESS_NAME", "daq6510_cs")
STORAGE_MNEMONIC = cs_settings.get("STORAGE_MNEMONIC", "DAQ6510")
POLL_INTERVAL = float(cs_settings.get("POLL_INTERVAL", 1.0))
"""Time between two polls of the reading buffer [s]."""
BUFFER_CAPACITY = int(cs_settings.get("BUFFER_CAPACITY", DEFAULT_BUFFER_CAPACITY))

ROLLOVER_FRACTION = 0.9
"""Restart the scan with an empty buffer when the buffer is filled to this fraction."""
MAX_READINGS_PER_REQUEST = 500
"""Maximum number of readings to fetch with one TRAC:DATA? request."""
RECONNECT_BACKOFF_MAX = 60.0
"""Maximum time between two attempts to (re)connect to the device [s]."""
CONNECTION_CHECK_INTERVAL = 10.0
"""Time between two connection checks while connected [s]."""

SITE_ID = get_site_id()


def success(message: Any) -> list:
    return zmq_json_response({"success": True, "message": message})


def failure(error: str, **details: Any) -> list:
    return zmq_json_response({"success": False, "message": {"error": error, **details}})


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class DAQ6510Controller(DeviceCommandRouter):
    """Device command router for the DAQ6510, it owns the device and the scan loop."""

    ALLOWED_DURING_SCAN = frozenset(
        {
            "scan-status",
            "get-latest",
            "stop-scan",
            "reset",
            "get-idn",
            "get-time",
            "get-buffer-count",
            "get-errors",
        }
    )

    def __init__(self, control_server: "DAQ6510ControlServer", daq: DAQ6510 | None = None):
        super().__init__(control_server)
        self._cs = control_server
        self.daq = daq or DAQ6510()

        self.hw_lock = asyncio.Lock()
        """The hardware lane, hold this lock for every exchange with the device."""

        self.scan_config: ScanConfig | None = None
        self.scan_task: asyncio.Task | None = None
        self.scan_stop_event = asyncio.Event()
        self.next_index = 1
        """Index of the next reading to fetch from the buffer."""
        self.scan_started_at: datetime.datetime | None = None
        self.scans_received = 0
        self.rollovers = 0
        self.last_error: str | None = None

        self.poll_interval = POLL_INTERVAL
        self.rollover_fraction = ROLLOVER_FRACTION

    def register_handlers(self):
        self.add_handler("start-scan", self.do_start_scan)
        self.add_handler("stop-scan", self.do_stop_scan)
        self.add_handler("reset", self.do_reset)
        self.add_handler("scan-status", self.do_scan_status)
        self.add_handler("get-latest", self.do_get_latest)
        self.add_handler("get-idn", self.do_get_idn)
        self.add_handler("get-time", self.do_get_time)
        self.add_handler("set-time", self.do_set_time)
        self.add_handler("get-buffer-count", self.do_get_buffer_count)
        self.add_handler("get-errors", self.do_get_errors)
        self.add_handler("send-command", self.do_send_command)

    async def process_command(self, cmd: dict[str, Any]) -> list:
        """Rejects commands that are not allowed during a scan, before they are dispatched."""
        command = cmd.get("command")
        if command in self.handlers and self.is_scan_running() and command not in self.ALLOWED_DURING_SCAN:
            return failure(
                "device-busy",
                state="scanning",
                detail=f"Command '{command}' is blocked while a scan is running.",
                allowed_during_scan=sorted(self.ALLOWED_DURING_SCAN),
            )
        return await super().process_command(cmd)

    async def _device_call(self, func: Callable, *args, **kwargs) -> list:
        """Executes a device call in the hardware lane and wraps the result or the error in a response."""
        if not self.daq.is_connection_open:
            return failure("device-not-connected", detail=f"Not connected to {self.daq.hostname}:{self.daq.port}")
        try:
            async with self.hw_lock:
                result = await func(*args, **kwargs)
        except DeviceError as exc:
            return failure("device-error", detail=str(exc))
        return success(result)

    # ----- command handlers ----------------------------------------------------------------------------------------

    async def do_start_scan(self, cmd: dict[str, Any]) -> list:
        try:
            started = await self.start_scan()
        except (ValueError, DeviceError) as exc:
            return failure("start-scan-failed", detail=str(exc))
        return success({"started": started, "status": self.get_scan_status()})

    async def do_stop_scan(self, cmd: dict[str, Any]) -> list:
        stopped = await self.stop_scan()
        return success({"stopped": stopped, "status": self.get_scan_status()})

    async def do_reset(self, cmd: dict[str, Any]) -> list:
        await self.stop_scan()
        return await self._device_call(self.daq.reset)

    async def do_scan_status(self, cmd: dict[str, Any]) -> list:
        return success(self.get_scan_status())

    async def do_get_latest(self, cmd: dict[str, Any]) -> list:
        return success(self._cs.latest)

    async def do_get_idn(self, cmd: dict[str, Any]) -> list:
        return await self._device_call(self.daq.get_idn)

    async def do_get_time(self, cmd: dict[str, Any]) -> list:
        return await self._device_call(self.daq.get_time)

    async def do_set_time(self, cmd: dict[str, Any]) -> list:
        """Sets the device time to the given ISO time (UTC), or to the current UTC time when no time is given."""
        try:
            dt = datetime.datetime.fromisoformat(cmd["time"]) if cmd.get("time") else None
        except ValueError as exc:
            return failure("invalid-argument", detail=str(exc))
        return await self._device_call(self.daq.set_time, dt)

    async def do_get_buffer_count(self, cmd: dict[str, Any]) -> list:
        buffer_name = self.scan_config.buffer_name if self.scan_config else "defbuffer1"
        return await self._device_call(self.daq.get_buffer_count, buffer_name)

    async def do_get_errors(self, cmd: dict[str, Any]) -> list:
        return await self._device_call(self.daq.get_errors)

    async def do_send_command(self, cmd: dict[str, Any]) -> list:
        """Sends a raw SCPI command. Pass `"response": true` when the command returns a response."""
        command_string = cmd.get("command_string")
        if not command_string:
            return failure("invalid-argument", detail="command_string is required")
        if cmd.get("response", False):
            return await self._device_call(self.daq.query_str, command_string)
        return await self._device_call(self.daq.write, command_string)

    # ----- scan management -----------------------------------------------------------------------------------------

    def is_scan_running(self) -> bool:
        return self.scan_task is not None and not self.scan_task.done()

    def get_scan_status(self) -> dict[str, Any]:
        config = self.scan_config
        return {
            "running": self.is_scan_running(),
            "connected": self.daq.is_connection_open,
            "channels": config.channel_names if config else [],
            "interval": config.interval if config else None,
            "buffer": config.buffer_name if config else None,
            "next_index": self.next_index,
            "scan_started_at": self.scan_started_at.isoformat() if self.scan_started_at else None,
            "scans_received": self.scans_received,
            "rollovers": self.rollovers,
            "last_error": self.last_error,
        }

    async def start_scan(self, config: ScanConfig | None = None) -> bool:
        """Configures the instrument and starts a scan that repeats until aborted.

        Args:
            config: the scan configuration, by default it is loaded from the Setup.

        Returns:
            True when the scan was started, False when a scan was already running.

        Raises:
            ValueError: when the scan configuration could not be loaded or the instrument reported errors.
            DeviceError: when the communication with the device fails.
        """
        if self.is_scan_running():
            return False

        if not self.daq.is_connection_open:
            raise DeviceError(self.daq.device_name, "Device is not connected.")

        config = config or await self._cs.load_scan_config()

        async with self.hw_lock:
            await self.daq.abort()
            await self.daq.get_errors()  # start with an empty error queue
            await self.daq.set_time()
            await self.daq.configure_scan(config)
            errors = await self.daq.get_errors()
            if errors:
                raise ValueError(f"The DAQ6510 reported errors while configuring the scan: {errors}")
            await self.daq.start_scan()

        self.scan_config = config
        self.next_index = 1
        self.scans_received = 0
        self.rollovers = 0
        self.last_error = None
        self.scan_started_at = utc_now()

        await self._cs.on_scan_started(config)

        self.scan_stop_event.clear()
        self.scan_task = asyncio.create_task(self._run_scan_loop(), name="daq6510-scan-loop")

        logger.info(f"Scan started on channels {config.channel_list} with an interval of {config.interval}s.")

        return True

    async def stop_scan(self) -> bool:
        """Stops the scan loop and aborts the scan on the instrument.

        Returns:
            True when a scan was running, False otherwise.
        """
        was_running = self.is_scan_running()

        self.scan_stop_event.set()
        if self.scan_task is not None:
            await asyncio.gather(self.scan_task, return_exceptions=True)
            self.scan_task = None

        if was_running and self.daq.is_connection_open:
            try:
                async with self.hw_lock:
                    await self.daq.abort()
            except DeviceError as exc:
                logger.warning(f"Could not abort the scan on the DAQ6510: {exc}")

        return was_running

    async def _run_scan_loop(self):
        """Polls the reading buffer and forwards complete scans to the acquisition pipeline.

        Errors don't end the loop, the next poll is retried with a growing backoff. On a timeout the connection is
        re-established to discard a late response that would otherwise be read as the answer to the next query.
        The instrument keeps scanning on its own meanwhile, so no data is lost when the connection recovers.
        """
        backoff = self.poll_interval

        while not self.scan_stop_event.is_set():
            try:
                if not self.daq.is_connection_open:
                    async with self.hw_lock:
                        await self.daq.connect()
                await self.poll_buffer()
                backoff = self.poll_interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001, any failure is retried, the loop must not die
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.error(f"Scan loop: polling the DAQ6510 failed ({exc}), retrying in {backoff:.1f}s.")
                if isinstance(exc, DeviceTimeoutError):
                    await self._drop_connection()
                await self._wait_for_stop(backoff)
                backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)
                continue

            await self._wait_for_stop(self.poll_interval)

    async def _wait_for_stop(self, timeout: float):
        try:
            await asyncio.wait_for(self.scan_stop_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

    async def _drop_connection(self):
        try:
            async with self.hw_lock:
                await self.daq.disconnect()
        except DeviceError as exc:
            logger.warning(f"Error while disconnecting from the DAQ6510: {exc}")

    async def poll_buffer(self) -> int:
        """Fetches all new complete scans from the buffer and passes them to the acquisition pipeline.

        Returns:
            The number of scans that were fetched.
        """
        config = self.scan_config
        assert config is not None
        n_channels = len(config.channel_names)
        buffer = config.buffer_name

        async with self.hw_lock:
            end = await self.daq.get_buffer_end(buffer)

            if end < self.next_index - 1:
                # The buffer has fewer readings than we already fetched, it was cleared or reset behind our back.
                logger.warning(
                    f"The DAQ6510 buffer {buffer!r} has {end} readings, but {self.next_index - 1} were already "
                    f"fetched. The buffer was cleared or the instrument was reset, starting again from index 1."
                )
                self.next_index = 1

            readings = []
            n_complete = ((end - self.next_index + 1) // n_channels) * n_channels
            chunk_size = max(n_channels, (MAX_READINGS_PER_REQUEST // n_channels) * n_channels)
            while n_complete > 0:
                count = min(n_complete, chunk_size)
                readings.extend(await self.daq.read_buffer(self.next_index, self.next_index + count - 1, buffer))
                self.next_index += count
                n_complete -= count

            if end >= self.rollover_fraction * config.buffer_capacity:
                readings.extend(await self._rollover(config))

        scans = [readings[idx : idx + n_channels] for idx in range(0, len(readings), n_channels)]
        for scan in scans:
            self._cs.on_acquisition_data(scan_record(scan), source="daq6510-buffer")
        self.scans_received += len(scans)

        return len(scans)

    async def _rollover(self, config: ScanConfig) -> list[Reading]:
        """Restarts the scan with an empty buffer. Must be called while holding the hardware lock.

        Returns:
            The complete scans that were added to the buffer before the scan was aborted.
        """
        logger.info(f"The DAQ6510 buffer {config.buffer_name!r} is almost full, restarting the scan.")

        await self.daq.abort()

        readings = []
        end = await self.daq.get_buffer_end(config.buffer_name)
        n_channels = len(config.channel_names)
        n_complete = ((end - self.next_index + 1) // n_channels) * n_channels
        if n_complete > 0:
            readings = await self.daq.read_buffer(self.next_index, self.next_index + n_complete - 1, config.buffer_name)

        await self.daq.clear_buffer(config.buffer_name)
        await self.daq.start_scan()

        self.next_index = 1
        self.rollovers += 1

        return readings


def scan_record(readings: list[Reading]) -> dict[str, Any]:
    """Converts the readings of one scan into an acquisition record."""
    return {
        "timestamp": readings[0].timestamp.isoformat(),
        "readings": {r.channel: r.value for r in readings},
        "units": {r.channel: r.unit for r in readings},
    }


class DAQ6510Services(ServiceCommandRouter):
    def __init__(self, control_server: "DAQ6510ControlServer"):
        super().__init__(control_server)
        self._cs = control_server

    def register_handlers(self):
        self.add_handler("health", self._health)

    async def _health(self, cmd: dict[str, Any]) -> list:
        return success(
            {
                "status": "ok",
                "connected": self._cs.controller.daq.is_connection_open,
                "scan running": self._cs.controller.is_scan_running(),
                "stored": self._cs.stored_count,
                "sent_metrics": self._cs.metrics_count,
                "failed_metrics": self._cs.metrics_failed_count,
            }
        )


class DAQ6510ControlServer(AcquisitionAsyncControlServer):
    """Asynchronous control server for the Keithley DAQ6510.

    Args:
        daq: the device to use, by default a DAQ6510 using the hostname and port from the settings
        setup_file: read the scan configuration from this Setup file instead of the current Setup
        auto_scan: start scanning as soon as the device is connected
    """

    service_type = SERVICE_TYPE
    service_name = SERVICE_NAME

    def __init__(self, daq: DAQ6510 | None = None, setup_file: str | Path | None = None, auto_scan: bool = False):
        self._daq = daq
        self.setup_file = Path(setup_file) if setup_file else None
        self.auto_scan = auto_scan

        self.latest: dict[str, Any] = {}
        """The latest readings per channel, and the latest complete scan."""
        self.hk_names: dict[str, str] = {}
        """Mapping of channel names to housekeeping names, from the telemetry dictionary."""
        self.storage_registered = False
        self.storage_columns: list[str] = []
        """The column names the control server is registered with at the Storage Manager."""
        self.stored_count = 0
        self.metrics_count = 0
        self.metrics_failed_count = 0
        self._metrics_sender: AsyncMetricsHubSender | None = None

        super().__init__()

    def create_device_command_router(self) -> DeviceCommandRouter:
        return DAQ6510Controller(self, daq=self._daq)

    def create_service_command_router(self) -> ServiceCommandRouter:
        return DAQ6510Services(self)

    @property
    def controller(self) -> DAQ6510Controller:
        return self._device_command_router  # type: ignore[return-value]

    def create_background_tasks(self) -> list[asyncio.Task]:
        tasks = super().create_background_tasks()
        tasks.append(asyncio.create_task(self.maintain_connection(), name="daq6510-connection"))
        return tasks

    def get_component_status(self) -> dict[str, Any]:
        components = super().get_component_status()
        components["scan"] = self.controller.get_scan_status()
        components["acquisition"] = {
            "queue_size": self._acquisition_queue.qsize(),
            "dropped": self.acquisition_dropped_count,
        }
        components["sinks"] = {
            "stored": self.stored_count,
            "sent_metrics": self.metrics_count,
            "failed_metrics": self.metrics_failed_count,
        }
        return components

    # ----- device connection ---------------------------------------------------------------------------------------

    async def maintain_connection(self):
        """Connects to the device and keeps checking the connection while no scan is running.

        The control server starts and stays responsive when the device is not available. While a scan is running,
        the scan loop takes care of the connection.
        """
        controller = self.controller
        backoff = 1.0

        while not self.interrupted.is_set():
            if not controller.is_scan_running():
                try:
                    async with controller.hw_lock:
                        if controller.daq.is_connection_open:
                            connected = await controller.daq.is_connected()
                        else:
                            await controller.daq.connect()
                            connected = True
                            logger.info(f"Connected to the DAQ6510 at {controller.daq.hostname}:{controller.daq.port}")
                    backoff = 1.0
                except DeviceError as exc:
                    connected = False
                    logger.warning(f"Could not connect to the DAQ6510: {exc}, retrying in {backoff:.0f}s.")

                if connected and self.auto_scan:
                    self.auto_scan = False  # only once, a stopped scan is not restarted automatically
                    try:
                        await controller.start_scan()
                    except (ValueError, DeviceError) as exc:
                        controller.last_error = str(exc)
                        logger.error(f"Could not start the scan automatically: {exc}")

                delay = CONNECTION_CHECK_INTERVAL if connected else backoff
                if not connected:
                    backoff = min(backoff * 2, RECONNECT_BACKOFF_MAX)
            else:
                delay = CONNECTION_CHECK_INTERVAL

            try:
                await asyncio.wait_for(self.interrupted.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    # ----- configuration -------------------------------------------------------------------------------------------

    async def load_scan_config(self) -> ScanConfig:
        """Loads the scan configuration from the Setup file or the current Setup."""
        setup = await asyncio.to_thread(self._load_setup)
        if setup is None:
            raise ValueError("No Setup available to configure the DAQ6510.")
        return scan_config_from_setup(setup, buffer_capacity=BUFFER_CAPACITY)

    def _load_setup(self):
        from egse.setup import Setup
        from egse.setup import load_setup

        if self.setup_file:
            return Setup.from_yaml_file(self.setup_file)
        return load_setup()

    async def on_scan_started(self, config: ScanConfig):
        """Prepares the data sinks for the given scan configuration."""
        self.hk_names = await asyncio.to_thread(self._read_hk_names, config)
        self.latest = {}

        # The columns change when the channels in the Setup changed since the previous scan
        columns = self._column_names(config)
        if self.storage_registered and columns != self.storage_columns:
            await asyncio.to_thread(self.unregister_from_storage_manager)

        if not self.storage_registered and await asyncio.to_thread(self.is_storage_manager_active):
            await asyncio.to_thread(self._register_to_storage_manager, columns)

    def _read_hk_names(self, config: ScanConfig) -> dict[str, str]:
        from egse.hk import read_conversion_dict

        try:
            setup = self._load_setup()
            conversion = read_conversion_dict(STORAGE_MNEMONIC, use_site=True, setup=setup)
        except Exception as exc:  # noqa: BLE001, the telemetry dictionary is optional
            logger.warning(f"No telemetry dictionary entries for {STORAGE_MNEMONIC}, using the channel names: {exc}")
            conversion = {}
        return {channel: conversion.get(channel, f"{STORAGE_MNEMONIC}_{channel}") for channel in config.channel_names}

    # ----- storage manager -----------------------------------------------------------------------------------------

    def get_storage_mnemonic(self) -> str:
        return STORAGE_MNEMONIC

    def is_storage_manager_active(self) -> bool:
        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def register_to_storage_manager(self) -> None:
        """The columns depend on the scan configuration, registration is done when the scan is started."""

    def _column_names(self, config: ScanConfig) -> list[str]:
        return ["timestamp", *[self.hk_names[channel] for channel in config.channel_names]]

    def _register_to_storage_manager(self, columns: list[str]) -> None:
        from egse.storage import register_to_storage_manager
        from egse.storage.persistence import TYPES

        register_to_storage_manager(
            origin=STORAGE_MNEMONIC,
            persistence_class=TYPES["CSV"],
            prep={"column_names": columns, "mode": "a"},
        )
        self.storage_registered = True
        self.storage_columns = columns

    def unregister_from_storage_manager(self) -> None:
        if not self.storage_registered:
            return

        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=STORAGE_MNEMONIC)
        self.storage_registered = False
        self.storage_columns = []

    # ----- acquisition ---------------------------------------------------------------------------------------------

    async def handle_acquisition(
        self,
        data: Any,
        *,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ):
        """Handles one complete scan: updates the latest readings and sends the scan to the data sinks."""

        scan_timestamp = data["timestamp"]
        for channel, value in data["readings"].items():
            self.latest[channel] = {"value": value, "unit": data["units"].get(channel), "timestamp": scan_timestamp}

        hk = {"timestamp": scan_timestamp}
        hk.update({self.hk_names.get(ch, ch): value for ch, value in data["readings"].items()})

        if self.storage_registered:
            try:
                await asyncio.to_thread(self._store, hk)
                self.stored_count += 1
            except Exception as exc:  # noqa: BLE001, never let a sink failure stop the acquisition
                logger.warning(f"Failed to store DAQ6510 housekeeping: {exc!r}")

        if await self._send_metrics(hk):
            self.metrics_count += 1
        else:
            self.metrics_failed_count += 1

    def _store(self, hk: dict[str, Any]):
        from egse.storage import store_housekeeping_information

        store_housekeeping_information(STORAGE_MNEMONIC, hk)

    async def _send_metrics(self, hk: dict[str, Any]) -> bool:
        """Best-effort propagation to the Metrics Hub."""
        try:
            if self._metrics_sender is None:
                self._metrics_sender = AsyncMetricsHubSender()
                self._metrics_sender.connect()

            point = (
                DataPoint.measurement(STORAGE_MNEMONIC.lower())
                .tag("site_id", SITE_ID)
                .tag("origin", STORAGE_MNEMONIC)
                .time(datetime.datetime.fromisoformat(hk["timestamp"]))
            )
            for name, value in hk.items():
                if name != "timestamp":
                    point.field(name.lower(), value)

            return await self._metrics_sender.send(point)
        except Exception as exc:  # noqa: BLE001, never let a sink failure stop the acquisition
            logger.warning(f"Failed to send DAQ6510 metrics to the Metrics Hub: {exc!r}")
            return False

    # ----- shutdown ------------------------------------------------------------------------------------------------

    async def _cleanup_running_tasks(self):
        # Abort the scan on the instrument before the tasks are cancelled
        await self.controller.stop_scan()
        await super()._cleanup_running_tasks()

        # The base class only unregisters when the Storage Manager was active at startup, we register at scan start
        await asyncio.to_thread(self.unregister_from_storage_manager)

        if self.controller.daq.is_connection_open:
            try:
                await self.controller.daq.disconnect()
            except DeviceError as exc:
                logger.warning(f"Error while disconnecting from the DAQ6510: {exc}")

        if self._metrics_sender is not None:
            self._metrics_sender.close()
            self._metrics_sender = None


class DAQ6510Client(TypedAsyncControlClient):
    """Typed client for the DAQ6510 control server."""

    service_type = SERVICE_TYPE

    async def _device_command(self, command: str, timeout: float | None = None, **kwargs) -> Any:
        response = await self.send_device_command({"command": command, **kwargs}, timeout=timeout)
        return self._success_message(response, command)

    async def start_scan(self, timeout: float | None = 30.0) -> dict[str, Any] | None:
        return await self._device_command("start-scan", timeout=timeout)

    async def stop_scan(self, timeout: float | None = None) -> dict[str, Any] | None:
        return await self._device_command("stop-scan", timeout=timeout)

    async def reset(self, timeout: float | None = None) -> Any:
        return await self._device_command("reset", timeout=timeout)

    async def scan_status(self, timeout: float | None = None) -> dict[str, Any] | None:
        return await self._device_command("scan-status", timeout=timeout)

    async def get_latest(self, timeout: float | None = None) -> dict[str, Any] | None:
        return await self._device_command("get-latest", timeout=timeout)

    async def get_idn(self, timeout: float | None = None) -> str | None:
        return await self._device_command("get-idn", timeout=timeout)

    async def get_time(self, timeout: float | None = None) -> str | None:
        return await self._device_command("get-time", timeout=timeout)

    async def set_time(self, time: datetime.datetime | None = None, timeout: float | None = None) -> Any:
        return await self._device_command("set-time", timeout=timeout, time=time.isoformat() if time else None)

    async def get_buffer_count(self, timeout: float | None = None) -> int | None:
        return await self._device_command("get-buffer-count", timeout=timeout)

    async def get_errors(self, timeout: float | None = None) -> list[str] | None:
        return await self._device_command("get-errors", timeout=timeout)

    async def send_command(self, command_string: str, response: bool = False, timeout: float | None = None) -> Any:
        return await self._device_command(
            "send-command", timeout=timeout, command_string=command_string, response=response
        )

    async def health(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_service_command("health", timeout=timeout)
        return self._success_message_as_dict(response, "health")


# ----- CLI Commands ------------------------------------------------------------------------------------------------

app = typer.Typer(name="daq6510_cs", help="Keithley DAQ6510 asynchronous control server", no_args_is_help=True)


@app.command(cls=TyperAsyncCommand)
async def start(
    setup_file: str = typer.Option("", help="Read the scan configuration from this Setup YAML file."),
    auto_scan: bool = typer.Option(False, help="Start scanning as soon as the device is connected."),
):
    """Starts the DAQ6510 control server."""

    with remote_logging():
        from egse.env import setup_env

        setup_env()

        try:
            control_server = DAQ6510ControlServer(setup_file=setup_file or None, auto_scan=auto_scan)
            await control_server.start()
        except KeyboardInterrupt:
            logger.debug("Shutdown requested...exiting")
        except Exception:
            msg = "Cannot start the DAQ6510 Control Server"
            logger.exception(msg)
            rich.print(f"[red]{msg}.")


async def _run_client(func: Callable, error_message: str):
    try:
        async with DAQ6510Client() as client:
            rich.print(await func(client))
    except Exception as exc:  # noqa: BLE001
        rich.print(f"[red]{error_message}: {exc}")


@app.command(cls=TyperAsyncCommand)
async def stop():
    """Stops the DAQ6510 control server, this also aborts a running scan."""
    await _run_client(lambda client: client.stop_server(), "Could not stop the DAQ6510 control server")


@app.command(cls=TyperAsyncCommand)
async def status():
    """Prints status information of the DAQ6510 control server."""

    async def _status(client: DAQ6510Client):
        return {"info": await client.info(), "health": await client.health(), "scan": await client.scan_status()}

    try:
        async with DAQ6510Client() as client:
            rich.print("DAQ6510 CS: [green]active")
            rich.print(await _status(client))
    except Exception:  # noqa: BLE001
        rich.print("DAQ6510 CS: [red]not active")


@app.command(cls=TyperAsyncCommand)
async def start_scan():
    """Configures the DAQ6510 from the Setup and starts a scan."""
    await _run_client(lambda client: client.start_scan(), "Could not start the scan")


@app.command(cls=TyperAsyncCommand)
async def stop_scan():
    """Aborts the scan on the DAQ6510."""
    await _run_client(lambda client: client.stop_scan(), "Could not stop the scan")


@app.command(cls=TyperAsyncCommand)
async def get_latest():
    """Prints the latest readings."""
    await _run_client(lambda client: client.get_latest(), "Could not get the latest readings")


@app.command(cls=TyperAsyncCommand)
async def reset():
    """Aborts the scan and resets the DAQ6510 to its default settings."""
    await _run_client(lambda client: client.reset(), "Could not reset the DAQ6510")


if __name__ == "__main__":
    sys.exit(app())
