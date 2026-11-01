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
    """Starts the ThermalVac control server service."""

    rich.print("Starting ThermalVac control server service")

    out = redirect_output_to_log("tvac.start.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_acs", "start"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="stop")
def stop_tvac():
    """Stops the ThermalVac control server service."""

    rich.print("Terminating the ThermalVac control server service")

    out = redirect_output_to_log("tvac.stop.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_acs", "stop"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="status")
def status_tvac():
    """Prints status information for the ThermalVac service."""

    with all_logging_disabled():
        from egse.ivs.tvac import tvac_acs

        asyncio.run(tvac_acs.status())


@tvac.command(name="start-sim")
def start_tvac_sim():
    """Starts the ThermalVac OPC UA simulator service."""

    rich.print("Starting ThermalVac OPC UA simulator service")

    out = redirect_output_to_log("tvac.start-sim.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_sim", "start"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="stop-sim")
def stop_tvac_sim():
    """Stops the ThermalVac OPC UA simulator service."""

    rich.print("Terminating the ThermalVac OPC UA simulator service")

    out = redirect_output_to_log("tvac.stop-sim.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_sim", "stop"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="status-sim")
def status_tvac_sim():
    """Prints status information for the ThermalVac OPC UA simulator. The exit code is 1 when it is not running."""

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_sim", "status"]

    proc = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)

    rich.print(proc.stdout.decode(), end="")
    raise typer.Exit(proc.returncode)
