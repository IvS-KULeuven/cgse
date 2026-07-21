"""A minimal OPC UA simulator for the ThermalVac PLC.

This exposes the same OPC UA nodes as the real device (see `OPC_UA_NODES` in `tvac_devif.py`), pre-loaded with
static, plausible values, so the ThermalVac Control Server can be developed and tested without access to the
physical hardware.

Nodes are read/write exactly like on the real device: unregistered node ids and writes to read-only nodes are
rejected by the OPC UA server itself (`BadNodeIdUnknown` / `BadNotWritable`), we don't need to implement that.

Only one bit of device-side behaviour is simulated for now: the `start_data_logging` / `stop_data_logging`
"pulse" bits are consumed by a background task, which updates `is_data_logging_active` accordingly and refuses to
start a scan that is already running (reflected as `is_data_logging_error` / `get_data_logging_error_id`, since on
a real OPC UA device a write to a command bit always succeeds — a busy/rejected command is reported back through
separate status nodes, not through a failed write).

The PLC file-read protocol (`trigger_state` and friends, see `ThermalVacDaq.read_file_from_plc`) is not simulated
yet: `trigger_state` just holds whatever was last written to it, so `read_file_from_plc()` will time out against
this simulator.
"""

from __future__ import annotations

import asyncio
import logging
import math
import multiprocessing
import os
import random
import signal
import time
from pathlib import Path
from typing import Any

import typer
from asyncua import Server, ua
from rich.console import Console

from egse.env import get_log_file_location
from egse.ivs.tvac import DEVICE_SETTINGS
from egse.ivs.tvac.tvac_devif import OPC_UA_NODES
from egse.process import kill_process
from egse.system import TyperAsyncCommand

LOGGER = logging.getLogger(__name__)

# Poll interval [s] for the background task that reacts to pulse-bit writes.
POLL_INTERVAL = 0.2

DATA_LOGGING_IDLE = 0
DATA_LOGGING_RUNNING = 1

# --- Simulated temperature/pressure profile ---------------------------------------------------
#
# A repeating 1-hour thermal cycle, so Grafana/MetricsHub dashboards fed by this simulator have
# something more realistic to show than a flat line: the chamber cools from room temperature down
# to -20 degC over 20 minutes, holds for 10 minutes, then heats back up to room temperature over
# 30 minutes. The vessel pressure follows the same phase timing, pumping down to a rough vacuum
# while the chamber cools and venting back to atmosphere while it heats up. Both curves are
# asymptotic (fast at first, slowing down towards the target), which is how pump-down/vent and
# thermal transients actually behave.

PROFILE_PERIOD = 3600.0  # s, total duration of one thermal cycle
COOLING_DURATION = 1200.0  # s, 20 min
STABLE_DURATION = 600.0  # s, 10 min
HEATING_DURATION = 1800.0  # s, 30 min

ROOM_TEMPERATURE = 20.0  # degC
COLD_TEMPERATURE = -20.0  # degC

ATMOSPHERIC_PRESSURE = 1000.0  # mbar, matches the simulator's baseline value
HIGH_VACUUM_PRESSURE = 1.0e-3  # mbar

# Per-sensor offsets so the individual channels don't all read exactly the same value.
PT100_OFFSETS = (0.0, 0.4, -0.3)
DUT_OFFSETS = (0.2, -0.5, 0.1)

TEMPERATURE_NOISE_STD = 0.05  # degC
PRESSURE_NOISE_FRAC = 0.02  # relative (2%) noise on the raw pressure reading

PROFILE_UPDATE_INTERVAL = 1.0  # s


def _asymptotic_approach(elapsed: float, duration: float, start: float, end: float) -> float:
    """Interpolates from `start` to `end` over `duration` seconds, changing quickly at first and
    slowing down as it nears `end` (exponential asymptote), landing exactly on `end` when
    `elapsed >= duration`.
    """

    if elapsed <= 0:
        return start
    if elapsed >= duration:
        return end

    tau = duration / 3.0
    raw = 1 - math.exp(-elapsed / tau)
    norm = 1 - math.exp(-duration / tau)
    return start + (end - start) * (raw / norm)


def _base_temperature(elapsed_in_cycle: float) -> float:
    """The noise-free chamber temperature [degC] at a point in the 1-hour thermal cycle."""

    if elapsed_in_cycle < COOLING_DURATION:
        return _asymptotic_approach(elapsed_in_cycle, COOLING_DURATION, ROOM_TEMPERATURE, COLD_TEMPERATURE)
    elif elapsed_in_cycle < COOLING_DURATION + STABLE_DURATION:
        return COLD_TEMPERATURE
    else:
        heating_elapsed = elapsed_in_cycle - COOLING_DURATION - STABLE_DURATION
        return _asymptotic_approach(heating_elapsed, HEATING_DURATION, COLD_TEMPERATURE, ROOM_TEMPERATURE)


def _base_pressure(elapsed_in_cycle: float) -> float:
    """The noise-free vessel pressure [mbar] at a point in the 1-hour thermal cycle."""

    if elapsed_in_cycle < COOLING_DURATION:
        return _asymptotic_approach(elapsed_in_cycle, COOLING_DURATION, ATMOSPHERIC_PRESSURE, HIGH_VACUUM_PRESSURE)
    elif elapsed_in_cycle < COOLING_DURATION + STABLE_DURATION:
        return HIGH_VACUUM_PRESSURE
    else:
        heating_elapsed = elapsed_in_cycle - COOLING_DURATION - STABLE_DURATION
        return _asymptotic_approach(heating_elapsed, HEATING_DURATION, HIGH_VACUUM_PRESSURE, ATMOSPHERIC_PRESSURE)

# Variant type, initial value and read/write access for every node in OPC_UA_NODES.
#
# The variant type must be declared explicitly and must match what the client reads/writes: OPC UA is
# strongly typed, e.g. `ua.VariantType.Float` (32-bit) and `.Double` (64-bit) are NOT interchangeable, and a
# write with the "wrong" numeric variant is rejected with `BadTypeMismatch` — exactly as a real device would.

NODE_SPECS: dict[str, tuple[ua.VariantType, Any, bool]] = {
    "is_vacuum_gauge_powered": (ua.VariantType.Boolean, True, False),
    "is_vacuum_gauge_error": (ua.VariantType.Boolean, False, False),
    "get_vessel_pressure": (ua.VariantType.Float, 1000.0, False),
    "get_filtered_vessel_pressure": (ua.VariantType.Float, 1000.0, False),
    "get_temperatures": (ua.VariantType.Float, [20.0, 20.0, 20.0], False),
    "get_dut_temperatures": (ua.VariantType.Float, [20.0, 20.0, 20.0], False),
    "get_dut_temperature_weights": (ua.VariantType.Int32, [1, 1, 1], False),
    "get_avg_temperature": (ua.VariantType.Float, 20.0, False),
    "temperature_setpoint": (ua.VariantType.Float, 20.0, True),
    "get_pid_output_cooling": (ua.VariantType.Float, 0.0, False),
    "get_pid_output_heating": (ua.VariantType.Float, 0.0, False),
    "temperature_ctrl_active": (ua.VariantType.Boolean, False, True),
    "is_scroll_pump_running": (ua.VariantType.Boolean, False, False),
    "is_scroll_pump_alarm": (ua.VariantType.Boolean, False, False),
    "get_turbo_pump_rpm": (ua.VariantType.Int32, 0, False),
    "is_turbo_pump_error": (ua.VariantType.Boolean, False, False),
    "get_tvac_state": (ua.VariantType.Int32, 1, False),  # 1 = Idle, see `tvac_state_to_string`
    "set_stop_pumps": (ua.VariantType.Boolean, False, True),
    "is_data_logging_active": (ua.VariantType.Boolean, False, False),
    "start_data_logging": (ua.VariantType.Boolean, False, True),
    "stop_data_logging": (ua.VariantType.Boolean, False, True),
    "get_data_logging_state": (ua.VariantType.Int32, DATA_LOGGING_IDLE, False),
    "is_data_logging_error": (ua.VariantType.Boolean, False, False),
    "get_data_logging_error_id": (ua.VariantType.Int32, 0, False),
    "get_data_logging_filename": (ua.VariantType.String, "", False),
    "get_data_logging_directory": (ua.VariantType.String, "C:\\Logs", False),
    "set_file_path_to_read": (ua.VariantType.String, "", True),
    "trigger_state": (ua.VariantType.Int32, 0, True),
    "get_file_content": (ua.VariantType.String, "", False),
}


class ThermalVacSimulator:
    """A minimal OPC UA server standing in for the ThermalVac PLC."""

    def __init__(self, hostname: str | None = None, port: int | None = None):
        """Initialisation of the ThermalVac simulator.

        Args:
            hostname (str | None): Hostname to listen on. If None, read from the settings.
            port (int | None): Port to listen on. If None, read from the settings.
        """

        self.hostname = DEVICE_SETTINGS["HOSTNAME"] if hostname is None else hostname
        self.port = DEVICE_SETTINGS["PORT"] if port is None else port

        self.server = Server()
        self._nodes: dict[str, Any] = {}
        self._poll_task: asyncio.Task | None = None
        self._profile_task: asyncio.Task | None = None

    @property
    def server_url(self) -> str:
        return f"opc.tcp://{self.hostname}:{self.port}"

    async def start(self) -> None:
        """Initialises the OPC UA server, registers all simulated nodes and starts listening."""

        multiprocessing.current_process().name = "tvac_sim"

        await self.server.init()
        self.server.set_endpoint(self.server_url)

        objects = self.server.get_objects_node()

        for key, node_id in OPC_UA_NODES.items():
            variant_type, initial_value, writable = NODE_SPECS[key]
            node = await objects.add_variable(node_id, f"4:{key}", initial_value, varianttype=variant_type)
            if writable:
                await node.set_writable()
            self._nodes[key] = node

        await self.server.start()

        self._poll_task = asyncio.create_task(self._poll_loop(), name="tvac-simulator-poll")
        self._profile_task = asyncio.create_task(self._profile_loop(), name="tvac-simulator-profile")

        LOGGER.info(f"ThermalVac simulator listening on {self.server_url}")

    async def stop(self) -> None:
        """Stops the background tasks and the OPC UA server."""

        tasks = [t for t in (self._poll_task, self._profile_task) if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._poll_task = None
        self._profile_task = None

        await self.server.stop()

        LOGGER.info("ThermalVac simulator stopped")

    async def _write(self, key: str, value: Any) -> None:
        """Writes a node's value using its declared OPC UA variant type.

        `Node.write_value()` infers a variant type from the Python type of `value` when none is given, which
        does not necessarily match the node's declared type (e.g. a Python `int` is inferred as `Int64`, not
        `Int32`) and would be rejected with `BadTypeMismatch`. Always writing with the type from `NODE_SPECS`
        avoids that.
        """

        variant_type, _, _ = NODE_SPECS[key]
        await self._nodes[key].write_value(value, varianttype=variant_type)

    async def _poll_loop(self) -> None:
        """Background task that plays the role of the PLC logic reacting to command bits."""

        while True:
            try:
                await self._handle_data_logging_commands()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("ThermalVac simulator poll loop iteration failed")

            await asyncio.sleep(POLL_INTERVAL)

    async def _handle_data_logging_commands(self) -> None:
        """Consumes the start/stop data-logging pulse bits and updates the logging status nodes."""

        start_requested = await self._nodes["start_data_logging"].read_value()
        stop_requested = await self._nodes["stop_data_logging"].read_value()
        is_active = await self._nodes["is_data_logging_active"].read_value()

        if start_requested:
            await self._write("start_data_logging", False)  # command bits are one-shot pulses

            if is_active:
                # Not allowed: a scan is already running. A real write never fails for this; the PLC
                # reports the rejection through the error nodes instead.
                await self._write("is_data_logging_error", True)
                await self._write("get_data_logging_error_id", 1)
            else:
                await self._write("is_data_logging_active", True)
                await self._write("get_data_logging_state", DATA_LOGGING_RUNNING)
                await self._write("is_data_logging_error", False)

        if stop_requested:
            await self._write("stop_data_logging", False)

            if is_active:
                await self._write("is_data_logging_active", False)
                await self._write("get_data_logging_state", DATA_LOGGING_IDLE)
            # Stopping while not running: the real PLC would just ignore this, so we do too.

    async def _profile_loop(self) -> None:
        """Background task that continuously writes a repeating 1-hour temperature/pressure profile
        to the simulated housekeeping nodes (see the module docstring above `PROFILE_PERIOD`).
        """

        start_time = time.monotonic()

        while True:
            try:
                elapsed_in_cycle = (time.monotonic() - start_time) % PROFILE_PERIOD
                await self._update_temperatures(elapsed_in_cycle)
                await self._update_pressures(elapsed_in_cycle)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("ThermalVac simulator profile loop iteration failed")

            await asyncio.sleep(PROFILE_UPDATE_INTERVAL)

    async def _update_temperatures(self, elapsed_in_cycle: float) -> None:
        base = _base_temperature(elapsed_in_cycle)

        pt100_temperatures = [base + offset + random.gauss(0.0, TEMPERATURE_NOISE_STD) for offset in PT100_OFFSETS]
        dut_temperatures = [base + offset + random.gauss(0.0, TEMPERATURE_NOISE_STD) for offset in DUT_OFFSETS]

        await self._write("get_temperatures", pt100_temperatures)
        await self._write("get_dut_temperatures", dut_temperatures)
        await self._write("get_avg_temperature", base)

    async def _update_pressures(self, elapsed_in_cycle: float) -> None:
        base = _base_pressure(elapsed_in_cycle)
        noisy = base * (1 + random.gauss(0.0, PRESSURE_NOISE_FRAC))

        await self._write("get_vessel_pressure", noisy)
        await self._write("get_filtered_vessel_pressure", base)

    async def __aenter__(self) -> "ThermalVacSimulator":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()


# ----- CLI Commands ------------------------------------------------------------------------------------------------

app = typer.Typer()


def _simulator_pid_file() -> Path:
    """Location of the ThermalVac simulator's pid file, used by `stop` to find the running process.

    A pid file (write our own pid on start, read + kill that exact pid on stop) is used instead of matching
    processes by name/command line: a `start`/`stop` substring search can accidentally match unrelated
    processes whose command line happens to mention those words (e.g. a shell running a script that itself
    contains the text "tvac_sim start", such as this very CLI's own test/dev tooling).
    """

    return Path(get_log_file_location()).expanduser() / "tvac-simulator.pid"


@app.command(cls=TyperAsyncCommand)
async def start():
    """Starts the ThermalVac OPC UA simulator (blocks until interrupted)."""

    console = Console()
    simulator = ThermalVacSimulator()

    pid_file = _simulator_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    # SIGINT (Ctrl-C) is turned into a KeyboardInterrupt automatically, but SIGTERM (what `stop` sends via
    # `kill_process`) is not: by default it kills the process immediately, without running this coroutine's
    # `finally` block below. Handling both explicitly guarantees `simulator.stop()` always runs, mirroring
    # the pattern `reg_cs` uses (see `egse.registry.server.start`).
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await simulator.start()
        console.print(f"ThermalVac simulator listening on [green]{simulator.server_url}[/]. Press Ctrl-C to stop.")
        await stop_event.wait()
    finally:
        await simulator.stop()
        pid_file.unlink(missing_ok=True)


@app.command(cls=TyperAsyncCommand)
async def stop():
    """Terminates a running ThermalVac OPC UA simulator process."""

    console = Console()
    pid_file = _simulator_pid_file()

    if not pid_file.exists():
        console.print("No running ThermalVac simulator process found.", style="yellow")
        return

    pid = int(pid_file.read_text().strip())

    if kill_process(pid):
        console.print(f"Stopped ThermalVac simulator (pid={pid}).")
    else:
        console.print(f"ThermalVac simulator (pid={pid}) was not running.", style="yellow")

    pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    app()
