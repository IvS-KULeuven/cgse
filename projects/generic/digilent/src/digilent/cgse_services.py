import subprocess
from typing import Annotated

import sys

import rich
import typer

from egse.system import redirect_output_to_log, all_logging_disabled

dt8874 = typer.Typer(
    name="dt8874", help="Digilent MEASURpoint DT8874, temperature and voltage monitoring", no_args_is_help=True
)


@dt8874.command(name="start")
def start_dt8874(
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """Start the Digilent MEASURpoint DT8874 Control Server.

    The Control Server is always started in the background.
    """

    rich.print(f"Starting the Digilent MEASURpoint DT8874 Control Server - {simulator = }")
    out = redirect_output_to_log("dt8874_cs.start.log")

    cmd = [sys.executable, "-m", "egse.digilent.measurpoint.dt8874.dt8874_cs", "start"]
    if simulator:
        cmd.append("--simulator")

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@dt8874.command(name="stop")
def stop_dt8874():
    """Stops the Digilent MEASURpoint DT8874 Control Server."""

    rich.print("Stopping the Digilent MEASURpoint DT8874 Control Server")
    out = redirect_output_to_log("dt8874_cs.stop.log")

    cmd = [sys.executable, "-m", "egse.digilent.measurpoint.dt8874.dt8874_cs", "stop"]
    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@dt8874.command(name="status")
def status_dt8874():
    """Prints the status information about the Digilent MEASURpoint DT8874 Control Server."""

    with all_logging_disabled():
        from egse.digilent.measurpoint.dt8874 import dt8874_cs

        dt8874_cs.status()


if __name__ == "__main__":
    dt8874()
