import subprocess
from pathlib import Path
from typing import TextIO, Annotated

import sys
import rich
import typer

from egse.env import get_log_file_location
from egse.system import all_logging_disabled

tcu = typer.Typer(name="tcu", help="Ariel Telescope Control Unit (TCU)", no_args_is_help=True)


def redirect_output_to(output_fn: str) -> TextIO:
    """Opens a file in the log folder where process output will be re-directed to."""

    location = get_log_file_location()
    output_path = Path(location, output_fn).expanduser()

    rich.print(f"Output will be redirected to {output_path!s}")

    out = open(output_path, "w")

    return out


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
    out = redirect_output_to("tcu_cs.start.out")

    cmd = [sys.executable, "-m", "egse.ariel.tcu.tcu_cs", "start"]
    if simulator:
        cmd.append("--simulator")

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@tcu.command(name="stop")
def stop_tcu():
    """Stops the Ariel TCU Control Server."""

    rich.print("Stopping the Ariel TCU Control Server")
    out = redirect_output_to("tcu_cs.stop.out")

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
