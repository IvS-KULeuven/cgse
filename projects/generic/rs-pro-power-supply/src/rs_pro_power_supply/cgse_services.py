import subprocess
from typing import Annotated

import rich
import sys
import typer

from egse.system import redirect_output_to_log

rsd3305p = typer.Typer(name="rsd3305p", help="RS-PRO, RS-D3305P power supply", no_args_is_help=True)


@rsd3305p.command(name="start")
def start_rs3305p(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """Starts the RS-D3305P service.

    Args:
        device_id: RS-D3305P identifier.
    """

    rich.print("Starting service RS-D3305P")
    out = redirect_output_to_log("rsd3305p.start.log")

    cmd = [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3305p_cs", "start", device_id]
    if simulator:
        cmd.append("--simulator")
    subprocess.Popen(
        cmd,
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@rsd3305p.command(name="stop")
def stop_rsd3305p(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the RS-D3305P service.

    Args:
        device_id: RS-D3305P identifier.
    """

    rich.print("Terminating service RS-D3305P")

    out = redirect_output_to_log("rsd3305p_cs.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3305p_cs", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@rsd3305p.command(name="status")
def status_rsd3305p(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Prints status information on the RS-D3305P service.

    Args:
        device_id: RS-D3305P identifier.
    """

    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3305p_cs", "status", device_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end="")


@rsd3305p.command(name="start-sim")
def start_rs3305p_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Start the RS-D3305P Simulator.

    Args:
        device_id: RS-D3305P identifier.
    """

    rich.print("Starting service RS-D3305P Simulator")

    out = redirect_output_to_log("rsd3305p_sim.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3305p", "start", device_id, " --sim"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@rsd3305p.command(name="stop-sim")
def stop_rs3305p_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the RS-D3305P Simulator.

    Args:
        device_id: RS-D3305P identifier.
    """

    rich.print("Terminating the RS-D3305P simulator.")

    out = redirect_output_to_log("rsd3305p_sim.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.power_supply.rs_pro.rsd3305p", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


if __name__ == "__main__":
    rsd3305p()
