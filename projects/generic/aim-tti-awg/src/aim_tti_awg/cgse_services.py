import subprocess
from typing import Annotated

import sys

import rich
import typer

from egse.system import redirect_output_to_log

tgf4000 = typer.Typer(name="tgf4000", help="Aim -TTi, Dual-channel arbitrary function generator", no_args_is_help=True)


@tgf4000.command(name="start")
def start_tgf40000(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """Starts the TGF4000 service.

    Args:
        device_id: TGF4000-A identifier.
    """

    rich.print("Starting service tgf4000")
    out = redirect_output_to_log("tgf4000.start.log")

    cmd = [sys.executable, "-m", "egse.arbitrary_wave_generator.aim_tti.tgf4000_cs", "start", device_id]
    if simulator:
        cmd.append("--simulator")
    subprocess.Popen(
        cmd,
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@tgf4000.command(name="stop")
def stop_tgf4000(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the TGF4000 service.

    Args:
        device_id: TGF4000 identifier.
    """

    rich.print("Terminating service TGF4000")

    out = redirect_output_to_log("tgf4000_cs.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.arbitrary_wave_generator.aim_tti.tgf4000_cs", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@tgf4000.command(name="status")
def status_tgf4000(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Prints status information on the TGF4000 service.

    Args:
        device_id: TGF4000 identifier.
    """

    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.arbitrary_wave_generator.aim_tti.tgf4000_cs", "status", device_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end="")


@tgf4000.command(name="start-sim")
def start_tgf4000_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Start the TGF4000 Simulator.

    Args:
        device_id: TGF4000 identifier.
    """

    rich.print("Starting service TGF4000 Simulator")

    out = redirect_output_to_log("tgf4000_sim.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.arbitrary_wave_generator.aim_tti.tgf4000_sim", "start", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@tgf4000.command(name="stop-sim")
def stop_tgf4000_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the TGF4000 Simulator.

    Args:
        device_id: TGF4000 identifier.
    """

    rich.print("Terminating the TGF4000 simulator.")

    out = redirect_output_to_log("tgf4000_sim.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.arbitrary_wave_generator.aim_tti.tgf4000_sim", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


if __name__ == "__main__":
    tgf4000()
