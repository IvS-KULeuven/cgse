import subprocess

import sys
from pathlib import Path
from typing import Annotated

import rich
import typer

from egse.env import get_log_file_location

lakeshore336 = typer.Typer(
    name="LakeShore336",
    help="LakeShore336 Data Acquisition Unit, LakeShore, temperature monitoring",
)


@lakeshore336.command(name="start")
def start_lakeshore336(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="Start the LakeShore336 simulator as the backend")
    ] = False,
    background: Annotated[bool, typer.Option(help="Start the LakeShore336 in the background")] = False,
):
    """Starts the LakeShore336 Control Server.

    This Control Server is started in the background by default.

    Args:
        device_id (str): Device identifier
        simulator (bool): Indicates whether the LakeShore336 Control Server should be started in simulator mode
        background (bool): Indicates whether the LakeShore336 Control Server should be started in the background
    """

    rich.print(f"Starting service LakeShore336 {device_id}")

    if background:
        location = get_log_file_location()
        output_filename = "lakeshore336_cs.start.out"
        output_path = Path(location, output_filename).expanduser()

        rich.print(f"Starting the LakeShore336 Control Server ({device_id}) – {simulator = }")
        rich.print(f"Output will be redirected to {output_path!s}")

        out = open(output_path, "w")

        cmd = [sys.executable, "-m", "egse.tempcontrol.lakeshore.lakeshore336_cs", "start", device_id]
        if simulator:
            cmd.append("--simulator")

        subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)

    else:
        from egse.tempcontrol.lakeshore import lakeshore336_cs

        lakeshore336_cs.start(device_id, simulator)


@lakeshore336.command(name="stop")
def stop_lakeshore336(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stops the LakeShore336 service.

    Args:
        device_id (str): Device identifier
    """

    rich.print(f"Terminating service LakeShore336 {device_id}")

    from egse.tempcontrol.lakeshore import lakeshore336_cs

    lakeshore336_cs.stop(device_id)


@lakeshore336.command(name="status")
def status_lakeshore336(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Prints status information on the LakeShore336 service.

    Args:
        device_id (str): Device identifier
    """

    rich.print(f"Status of LakeShore336 {device_id}")

    from egse.tempcontrol.lakeshore import lakeshore336_cs

    lakeshore336_cs.status(device_id)


@lakeshore336.command(name="start-simulator")
def start_lakeshore336_sim(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Starts the LakeShore336 Simulator.

    Args:
        device_id (str): Device identifier
    """

    rich.print("Starting service LakeShore336 Simulator")

    from egse.tempcontrol.lakeshore import lakeshore336_cs

    lakeshore336_cs.status(device_id)
