import subprocess
from typing import Annotated

import rich
import sys
import typer

from egse.system import redirect_output_to_log

t7 = typer.Typer(name="t7", help="LabJack T7, Data Acquisition", no_args_is_help=True)


@t7.command(name="start")
def start_t7(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """Starts the T7 service.

    Args:
        device_id: T7 identifier.
    """

    rich.print("Starting service T7")
    out = redirect_output_to_log("t7.start.log")

    cmd = [sys.executable, "-m", "egse.daq.labjack.t7_cs", "start", device_id]
    if simulator:
        cmd.append("--simulator")
    subprocess.Popen(
        cmd,
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@t7.command(name="stop")
def stop_t7(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the T7 service.

    Args:
        device_id: T7 identifier.
    """

    rich.print("Terminating service T7")

    out = redirect_output_to_log("t7_cs.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.daq.labjack.t7_cs", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@t7.command(name="status")
def status_t7(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Prints status information on the T7 service.

    Args:
        device_id: T7 identifier.
    """

    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.daq.labjack.t7_cs", "status", device_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end="")


@t7.command(name="start-sim")
def start_t7_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Start the T7 Simulator.

    Args:
        device_id: T7 identifier.
    """

    rich.print("Starting service T7 Simulator")

    out = redirect_output_to_log("t7_sim.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.daq.labjack.t7_sim", "start", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@t7.command(name="stop-sim")
def stop_t7_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the T7 Simulator.

    Args:
        device_id: T7 identifier.
    """

    rich.print("Terminating the T7 simulator.")

    out = redirect_output_to_log("t7_sim.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.daq.labjack.t7_sim", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


if __name__ == "__main__":
    t7()
