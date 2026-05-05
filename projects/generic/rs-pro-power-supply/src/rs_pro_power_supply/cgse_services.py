import subprocess
from typing import Annotated

import rich
import sys
import typer

from egse.system import redirect_output_to_log

rsd3000 = typer.Typer(name="rsd3000", help="RS-PRO, RS-D3000 power supply", no_args_is_help=True)


@rsd3000.command(name="start")
def start_rs3000(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """Starts the RS-D3000 service.

    Args:
        device_id: RS-D3000 identifier.
    """

    rich.print("Starting service RS-D3000")
    out = redirect_output_to_log("rsd3000.start.log")

    cmd = [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3000_cs", "start", device_id]
    if simulator:
        cmd.append("--simulator")
    subprocess.Popen(
        cmd,
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@rsd3000.command(name="stop")
def stop_rsd3000(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the RS-D3000 service.

    Args:
        device_id: RS-D3000 identifier.
    """

    rich.print("Terminating service RS-D3000")

    out = redirect_output_to_log("rsd3000_cs.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3000_cs", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@rsd3000.command(name="status")
def status_rsd3000(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Prints status information on the RS-D3000 service.

    Args:
        device_id: RS-D3000 identifier.
    """

    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3000_cs", "status", device_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end="")


@rsd3000.command(name="start-sim")
def start_rs3000_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Start the RS-D3000 Simulator.

    Args:
        device_id: RS-D3000 identifier.
    """

    rich.print("Starting service RS-D3000 Simulator")

    out = redirect_output_to_log("rsd3000_sim.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3000_sim", "start", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@rsd3000.command(name="stop-sim")
def stop_rs3000_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the RS-D3000 Simulator.

    Args:
        device_id: RS-D3000 identifier.
    """

    rich.print("Terminating the RS-D3000 simulator.")

    out = redirect_output_to_log("rsd3000_sim.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3000_sim", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


if __name__ == "__main__":
    rsd3000()
