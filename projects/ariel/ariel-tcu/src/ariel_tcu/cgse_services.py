import subprocess
from pathlib import Path
from typing import TextIO, Annotated

import sys
import rich
import typer

from egse.system import all_logging_disabled, redirect_output_to_log

tcu = typer.Typer(name="tcu", help="Ariel Telescope Control Unit (TCU)", no_args_is_help=True)


@tcu.command(name="start")
def start_tcu(
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """Start the Ariel TCU Control Server.

    The Control Server is always started in the background.
    """

    rich.print(f"Starting the Ariel TCU Control Server - {simulator = }")
    out = redirect_output_to_log("tcu_cs.start.log")

    cmd = [sys.executable, "-m", "egse.ariel.tcu.tcu_cs", "start"]
    if simulator:
        cmd.append("--simulator")

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tcu.command(name="stop")
def stop_tcu():
    """Stops the Ariel TCU Control Server."""

    rich.print("Stopping the Ariel TCU Control Server")
    out = redirect_output_to_log("tcu_cs.stop.log")

    cmd = [sys.executable, "-m", "egse.ariel.tcu.tcu_cs", "stop"]
    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tcu.command(name="status")
def status_tcu():
    """Prints the status information about the Ariel TCU Control Server."""

    with all_logging_disabled():
        from egse.ariel.tcu import tcu_cs

        tcu_cs.status()


if __name__ == "__main__":
    tcu()
