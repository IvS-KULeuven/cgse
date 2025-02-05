# An example plugin for the `cgse {start,stop,status} service` command from `cgse-core`.
#
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import rich
import typer

daq6510 = typer.Typer(
    name="daq6510",
    help="DAQ6510 Data Acquisition Unit, Keithley, temperature monitoring",
    no_args_is_help=True
)


@daq6510.command(name="start")
def start_daq6510():
    """Start the daq6510 service."""
    rich.print("Starting service daq6510")


@daq6510.command(name="stop")
def stop_daq6510():
    """Stop the daq6510 service."""
    rich.print("Terminating service daq6510")


@daq6510.command(name="status")
def status_daq6510():
    """Print status information on the daq6510 service."""

    proc = subprocess.Popen(
        [sys.executable, '-m', 'egse.tempcontrol.keithley.daq6510_sim', 'status'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end='')
    # if stderr:
    #     rich.print(f"[red]{stderr.decode()}[/]")


@daq6510.command(name="start-sim")
def start_daq6510_sim():
    """Start the DAQ6510 Simulator."""
    rich.print("Starting service DAQ6510 Simulator")

    out = open(Path('~/.daq6510_sim.start.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'egse.tempcontrol.keithley.daq6510_sim', 'start'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


@daq6510.command(name="stop-sim")
def stop_daq6510_sim():
    """Stop the DAQ6510 Simulator."""
    rich.print("Terminating the DAQ6510 simulator.")

    out = open(Path('~/.daq6510_sim.stop.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'egse.tempcontrol.keithley.daq6510_sim', 'stop'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


if __name__ == '__main__':
    daq6510()
