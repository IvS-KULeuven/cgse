import asyncio
import subprocess
import sys

import rich
import typer

from egse.system import all_logging_disabled
from egse.system import redirect_output_to_log

thermalvac = typer.Typer(name="thermalvac", help="Thermal Vacuum Chamber")


@thermalvac.command(name="start")
def start_thermalvac():
    """Starts the ThermalVac service."""

    rich.print("Starting ThermalVac service")

    out = redirect_output_to_log("thermalvac.start.log")

    cmd = [sys.executable, "-m", "egse.ivs.thermalvac.async_thermalvac", "start"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@thermalvac.command(name="stop")
def stop_thermalvac():
    """Stops the ThermalVac service."""

    rich.print("Terminating the ThermalVac service")

    out = redirect_output_to_log("thermalvac.stop.log")

    cmd = [sys.executable, "-m", "egse.ivs.thermalvac.async_thermalvac", "stop"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@thermalvac.command(name="status")
def status_thermalvac():
    """Prints status information for the ThermalVac service."""

    with all_logging_disabled():
        from egse.ivs.thermalvac import async_thermalvac

        asyncio.run(async_thermalvac.status())
