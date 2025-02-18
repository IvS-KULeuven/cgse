import subprocess
import sys
from pathlib import Path
from typing import Annotated

import rich
import typer

from egse.env import get_log_file_location

puna = typer.Typer(
    name="puna",
    help="PUNA Positioning Hexapod, Symétrie",
    no_args_is_help=True
)


@puna.command(name="start")
def start_puna(
        simulator: Annotated[
            bool,
            typer.Option("--simulator", "--sim", help="start the hexapod PUNA simulator")
        ] = False
):
    """
    Start the PUNA hexapod control server. The control server is always started in the background.

    Args:
        - simulator: start the PUNA simulator to be used as the device simulator..

    """
    location = get_log_file_location()
    output_fn = 'puna_cs.start.out'
    output_path = Path(location, output_fn).expanduser()

    rich.print(f"Starting the PUNA hexapod control server – {simulator = }")
    rich.print(f"Output will be redirected to {output_path!s}")

    out = open(output_path, 'w')

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
    """Stop the PUNA hexapod control server."""
    rich.print("Terminating hexapod PUNA control server..")

    # out = open(Path('~/.puna_cs.stop.out').expanduser(), 'w')
    #
    # subprocess.Popen(
    #     [sys.executable, '-m', 'egse.hexapod.symetrie.puna_cs', 'stop'],
    #     stdout=out, stderr=out, stdin=subprocess.DEVNULL,
    #     close_fds=True
    # )

    from egse.hexapod.symetrie import puna_cs
    puna_cs.stop()


@puna.command(name="status")
def status_puna():
    """Print status information on the PUNA hexapod control server."""

    from egse.hexapod.symetrie import puna_cs
    puna_cs.status()
