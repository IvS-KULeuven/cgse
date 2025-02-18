import subprocess
import sys
from pathlib import Path
from typing import Annotated

import rich
import typer

puna = typer.Typer(
    name="puna",
    help="PUNA Positioning Hexapod, Symétrie",
    no_args_is_help=True
)


@puna.command(name="start")
def start_puna(
        simulator: Annotated[
            bool,
            typer.Option("--simulator", "--sim", help="start the hexapod PUNA simulator in the background")
        ] = False
):
    """Start the PUNA hexapod control server."""
    rich.print(f"Starting the PUNA hexapod control server – {simulator = }")

    out = open(Path('~/.puna_cs.start.out').expanduser(), 'w')

    cmd = [sys.executable, '-m', 'egse.hexapod.symetrie.puna_cs', 'start']
    if simulator:
        cmd.append("--simulator")

    subprocess.Popen(
        cmd,
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@puna.command(name="stop")
def stop_puna():
    """Stop the PUNA service."""
    rich.print("Terminating hexapod PUNA control server..")

    out = open(Path('~/.puna_cs.stop.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'egse.hexapod.symetrie.puna_cs', 'stop'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@puna.command(name="status")
def status_puna():
    """Print status information on the PUNA service."""
    rich.print("Printing the status of PUNA")
