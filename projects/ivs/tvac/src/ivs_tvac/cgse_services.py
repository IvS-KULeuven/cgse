import asyncio
import subprocess
import sys

import rich
import typer

from egse.system import all_logging_disabled
from egse.system import redirect_output_to_log

tvac = typer.Typer(name="tvac", help="Thermal Vacuum Chamber", no_args_is_help=True)


@tvac.command(name="start")
def start_tvac():
    """Starts the ThermalVac service."""

    rich.print("Starting ThermalVac service")

    out = redirect_output_to_log("tvac.start.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.async_tvac", "start"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="stop")
def stop_tvac():
    """Stops the ThermalVac service."""

    rich.print("Terminating the ThermalVac service")

    out = redirect_output_to_log("tvac.stop.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.async_tvac", "stop"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="status")
def status_tvac():
    """Prints status information for the ThermalVac service."""

    with all_logging_disabled():
        from egse.ivs.tvac import async_tvac

        asyncio.run(async_tvac.status())
