"""Starts, stops and restarts services with their `cgse <object> start|stop` command.

The `cgse <object>` command of a service is registered in the registry metadata (`cgse_object`); for the core services
that are not running it comes from `services.CORE_CGSE_OBJECTS`. The device identifier of the registration is passed
as argument, as required by the commands of devices with several instances, e.g. `cgse puna start PUNA_01`.

A command runs in a new session, so the services it starts don't belong to the terminal of the TUI. Its output goes to
a temporary file instead of a pipe: a started service could inherit the pipe, and reading it would never end.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cgse_tui.data.model import ServiceInfo

logger = logging.getLogger("cgse_tui.actions")

COMMAND_TIMEOUT = 30.0
"""Seconds a `cgse` command may take, the start commands return when the service process is launched."""

STATE_TIMEOUT = 30.0
"""Seconds to wait until a started service is registered, or a stopped service is no longer registered."""

SIMULATOR_TIMEOUT = 15.0
"""Seconds to wait until a simulator process that was started answers its status command."""

SIMULATOR_PROCESS = "process"
"""The simulator is a separate process, started with `cgse <object> start-sim` before the control server."""

SIMULATOR_OPTION = "option"
"""The control server runs the simulator itself, started with `cgse <object> start --sim`."""

OUTPUT_LINES = 5
"""Number of output lines of a failed command that are logged."""


@dataclass
class CommandResult:
    command: list[str]
    returncode: int | None
    """The exit code, None when the command didn't finish in time and was killed."""
    output: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def cgse_executable() -> str | None:
    """The `cgse` command of the Python environment of the TUI, or the one on the PATH."""
    candidate = Path(sys.executable).with_name("cgse")
    if candidate.exists():
        return str(candidate)
    return shutil.which("cgse")


def lifecycle_command(service: ServiceInfo, action: str, sim: bool = False) -> list[str] | None:
    """The command for the given action ("start", "stop", "status"), None when the service has no `cgse` command."""
    executable = cgse_executable()
    if not service.cgse_object or executable is None:
        return None
    command = [executable, service.cgse_object, action]
    if service.device_id:
        command.append(service.device_id)
    if sim:
        command.append("--sim")
    return command


def display(command: list[str]) -> str:
    """The command as the user would type it, e.g. "cgse puna stop PUNA_01"."""
    return " ".join(["cgse", *command[1:]])


async def run_command(command: list[str], timeout: float = COMMAND_TIMEOUT) -> CommandResult:
    """Runs a command in a new session and returns its exit code and output."""
    with tempfile.TemporaryFile() as output:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            start_new_session=True,
            env={**os.environ, "COLUMNS": "200"},  # no wrapped lines in the output of rich
        )
        try:
            returncode = await asyncio.wait_for(process.wait(), timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            returncode = None
        output.seek(0)
        return CommandResult(command, returncode, output.read().decode(errors="replace"))


class ServiceActions:
    """Runs the lifecycle commands of the services and follows the result in the collector.

    Args:
        collector: the `Collector` of the TUI, used to wait until a service is (no longer) running.
        run: coroutine function that runs a command, see `run_command()`.
        state_timeout: seconds to wait for the new state of a service.
        simulator_timeout: seconds to wait until a simulator that was started answers.
        simulator_interval: seconds between two status requests to a simulator that was started.
    """

    def __init__(
        self,
        collector,
        run=run_command,
        state_timeout: float = STATE_TIMEOUT,
        simulator_timeout: float = SIMULATOR_TIMEOUT,
        simulator_interval: float = 1.0,
    ):
        self.collector = collector
        self._run = run
        self.state_timeout = state_timeout
        self.simulator_timeout = simulator_timeout
        self.simulator_interval = simulator_interval
        self._busy: set[str] = set()
        self._simulator_support: dict[str, str | None] = {}

    def is_busy(self, service_type: str) -> bool:
        return service_type in self._busy

    async def perform(self, action: str, service: ServiceInfo, simulator: bool = False) -> bool:
        """Starts, stops or restarts the service, returns True when it reached the expected state.

        Args:
            action: "start", "stop" or "restart".
            service: the service.
            simulator: start the service with its simulator, see `simulator_support()`.
        """
        if self.is_busy(service.service_type):
            logger.warning(f"{service.name}: another action is still running.")
            return False
        self._busy.add(service.service_type)
        try:
            if action == "start":
                return await self._start(service, simulator)
            if action == "stop":
                return await self._stop(service)
            if action == "restart":
                return await self._stop(service) and await self._start(service, simulator)
            raise ValueError(f"Unknown action: {action}")
        finally:
            self._busy.discard(service.service_type)

    async def simulator_support(self, service: ServiceInfo) -> str | None:
        """How the service is started with a simulator: `SIMULATOR_PROCESS`, `SIMULATOR_OPTION` or None (no simulator).

        A simulator that is a separate process (e.g. DAQ6510, TVAC) has its own `start-sim` command, other drivers have
        a `--sim` option on the start command. The answer is kept per `cgse` command.
        """
        executable = cgse_executable()
        if not service.cgse_object or executable is None:
            return None
        if service.cgse_object not in self._simulator_support:
            commands = await self._run([executable, service.cgse_object, "--help"])
            if re.search(r"\bstart-sim\b", commands.output):
                support = SIMULATOR_PROCESS
            else:
                start = await self._run([executable, service.cgse_object, "start", "--help"])
                support = SIMULATOR_OPTION if re.search(r"--sim\b", start.output) else None  # not only `--simulator`
            self._simulator_support[service.cgse_object] = support
        return self._simulator_support[service.cgse_object]

    async def _start(self, service: ServiceInfo, simulator: bool = False) -> bool:
        sim_option = False
        if simulator:
            support = await self.simulator_support(service)
            if support == SIMULATOR_PROCESS:
                if not await self._start_simulator(service):
                    return False
            elif support == SIMULATOR_OPTION:
                sim_option = True
            else:
                logger.warning(f"{service.name}: no simulator is known for this service.")
                return False
        if not await self._command(service, "start", sim_option):
            return False
        if await self.collector.wait_until(service.service_type, running=True, timeout=self.state_timeout):
            logger.info(f"{service.name} is running.")
            return True
        logger.warning(f"{service.name} didn't register within {self.state_timeout:.0f} s after the start command.")
        return False

    async def _start_simulator(self, service: ServiceInfo) -> bool:
        """Starts the simulator process of the service, unless it is running. Waits until it answers."""
        status = [cgse_executable(), service.cgse_object, "status-sim"]
        if (await self._run(status)).ok:
            logger.info(f"{service.name}: the simulator is already running.")
            return True
        if not await self._run_logged(service, [cgse_executable(), service.cgse_object, "start-sim"]):
            return False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.simulator_timeout
        while not (await self._run(status)).ok:
            if loop.time() >= deadline:
                logger.warning(
                    f"{service.name}: the simulator doesn't answer {self.simulator_timeout:.0f} s after start-sim."
                )
                return False
            await asyncio.sleep(self.simulator_interval)
        logger.info(f"{service.name}: the simulator is running.")
        return True

    async def _stop(self, service: ServiceInfo) -> bool:
        if not await self._command(service, "stop"):
            return False
        if await self.collector.wait_until(service.service_type, running=False, timeout=self.state_timeout):
            logger.info(f"{service.name} stopped.")
            return True
        logger.warning(f"{service.name} is still running {self.state_timeout:.0f} s after the stop command.")
        return False

    async def _command(self, service: ServiceInfo, action: str, sim: bool = False) -> bool:
        command = lifecycle_command(service, action, sim)
        if command is None:
            logger.warning(f"{service.name}: no cgse command is known for this service.")
            return False
        return await self._run_logged(service, command)

    async def _run_logged(self, service: ServiceInfo, command: list[str]) -> bool:
        """Runs the command, logs it, and logs the end of its output when it fails."""
        logger.info(f"{service.name}: {display(command)}")
        result = await self._run(command)
        if result.ok:
            return True
        reason = "timed out" if result.returncode is None else f"failed with exit code {result.returncode}"
        lines = [line for line in result.output.splitlines() if line.strip()][-OUTPUT_LINES:]
        logger.warning(f"{display(command)} {reason}" + "".join(f"\n  {line}" for line in lines))
        return False
