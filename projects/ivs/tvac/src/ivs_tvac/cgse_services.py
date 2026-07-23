import asyncio
import subprocess
import sys

import rich
import typer

from egse.system import all_logging_disabled
from egse.system import redirect_output_to_log

tvac = typer.Typer(name="tvac", help="Thermal Vacuum Chamber", no_args_is_help=True)


@tvac.command(name="start-cs")
def start_tvac_cs():
    """Starts the ThermalVac control server service."""

    rich.print("Starting ThermalVac control server service")

    out = redirect_output_to_log("tvac.start-cs.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_acs", "start"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="stop-cs")
def stop_tvac_cs():
    """Stops the ThermalVac control server service."""

    rich.print("Terminating the ThermalVac control server service")

    out = redirect_output_to_log("tvac.stop-cs.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_acs", "stop"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="start-sim")
def start_tvac_sim():
    """Starts the ThermalVac OPC UA simulator service."""

    rich.print("Starting ThermalVac OPC UA simulator service")

    out = redirect_output_to_log("tvac.start-sim.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_simulator", "start"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="stop-sim")
def stop_tvac_sim():
    """Stops the ThermalVac OPC UA simulator service."""

    rich.print("Terminating the ThermalVac OPC UA simulator service")

    out = redirect_output_to_log("tvac.stop-sim.log")

    cmd = [sys.executable, "-m", "egse.ivs.tvac.tvac_simulator", "stop"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tvac.command(name="status")
def status_tvac():
    """Prints status information for the ThermalVac service."""

    with all_logging_disabled():
        from egse.ivs.tvac import tvac_acs

        asyncio.run(tvac_acs.status())
