import subprocess
from typing import Annotated

import sys

import rich
import typer

from egse.system import redirect_output_to_log

pmx_a = typer.Typer(name="pmx_a", help="KIKUSUI PMX, Regulated DC Power Supply")


@pmx_a.command(name="start")
def start_pmx_a(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Starts the PMX-A service.

    Args:
        device_id: PMX-A identifier.
    """

    rich.print("Starting service pmx_a")

    out = redirect_output_to_log("pmx_a.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.kikusui.pmx_a.pmx_a_cs", "start", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@pmx_a.command(name="stop")
def stop_pmx_a(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the PMX-A service.

    Args:
        device_id: PMX-A identifier.
    """

    rich.print("Terminating service PMX")

    out = redirect_output_to_log("pmx_a_cs.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.kikusui.pmx_a.pmx_a_cs", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@pmx_a.command(name="status")
def status_pmx_a(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Prints status information on the PMX-A service.

    Args:
        device_id: PMX-A identifier.
    """

    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.kikusui.pmx_a.pmx_a_cs", "status", device_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end="")


@pmx_a.command(name="start-sim")
def start_pmx_a_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Start the PMX-A Simulator.

    Args:
        device_id: PMX identifier.
    """

    rich.print("Starting service PMX Simulator")

    out = redirect_output_to_log("pmx_a_sim.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.kikusui.pmx_a.pmx_a_sim", "start", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@pmx_a.command(name="stop-sim")
def stop_pmx_a_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the PMX-A Simulator.

    Args:
        device_id: PMX identifier.
    """

    rich.print("Terminating the PMX simulator.")

    out = redirect_output_to_log("pmx_a_sim.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.kikusui.pmx_a.pmx_a_sim", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


if __name__ == "__main__":
    pmx_a()
