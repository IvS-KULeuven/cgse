# An example plugin for the `cgse {start,stop,status} service` command from `cgse-core`.
#
import subprocess
import sys

import rich
import typer

from egse.system import redirect_output_to_log

daq6510 = typer.Typer(name="daq6510", help="DAQ6510 Data Acquisition Unit, Keithley, temperature monitoring")


@daq6510.command(name="start")
def start_daq6510():
    """Start the daq6510 service."""
    rich.print("Starting service daq6510")

    out = redirect_output_to_log("daq6510_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_acs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@daq6510.command(name="stop")
def stop_daq6510():
    """Stop the daq6510 service."""
    rich.print("Terminating service daq6510")

    out = redirect_output_to_log("daq6510_cs.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_acs", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@daq6510.command(name="status")
def status_daq6510():
    """Print status information on the daq6510 service."""

    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_acs", "status"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end="")
    # if stderr:
    #     rich.print(f"[red]{stderr.decode()}[/]")


@daq6510.command(name="start-sim")
def start_daq6510_sim():
    """Start the DAQ6510 Simulator."""
    rich.print("Starting service DAQ6510 Simulator")

    out = redirect_output_to_log("daq6510_sim.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_sim", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@daq6510.command(name="stop-sim")
def stop_daq6510_sim():
    """Stop the DAQ6510 Simulator."""
    rich.print("Terminating the DAQ6510 simulator.")

    out = redirect_output_to_log("daq6510_sim.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_sim", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@daq6510.command(name="status-sim")
def status_daq6510_sim():
    """Print status information on the DAQ6510 Simulator."""

    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_sim", "status"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end="")


@daq6510.command(name="start-scan")
def start_daq6510_scan():
    """Configure the DAQ6510 from the Setup and start a scan."""
    rich.print("Starting a scan on the DAQ6510")

    out = redirect_output_to_log("daq6510_cs.start_scan.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_acs", "start-scan"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@daq6510.command(name="stop-scan")
def stop_daq6510_scan():
    """Abort the scan on the DAQ6510."""
    rich.print("Stopping the scan on the DAQ6510")

    out = redirect_output_to_log("daq6510_cs.stop_scan.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.tempcontrol.keithley.daq6510_acs", "stop-scan"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


if __name__ == "__main__":
    daq6510()
