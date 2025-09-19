import subprocess
import sys
import textwrap
from typing import Annotated

import rich
import typer

from egse.system import all_logging_disabled
from egse.system import redirect_output_to_log

puna = typer.Typer(name="puna", help="PUNA Positioning Hexapod, Symétrie")

zonda = typer.Typer(name="zonda", help="ZONDA Positioning Hexapod, Symétrie")

joran = typer.Typer(name="joran", help="JORAN Positioning Hexapod, Symétrie")


def start_hexapod_cs_process(device_name, device_id, simulator):
    """Generic function to start the hexapod control server in the background."""

    rich.print(f"Starting the {device_name} hexapod control server for {device_id} – {simulator = }")

    out = redirect_output_to_log(f".{device_name.lower()}_cs.{device_id.lower()}.start.log")

    cmd = [sys.executable, "-m", f"egse.hexapod.symetrie.{device_name.lower()}_cs", "start", device_id]
    if simulator:
        cmd.append("--simulator")

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


def stop_hexapod_cs_process(device_name, device_id):
    """Generic function to stop the hexapod control server in the background."""

    rich.print(f"Terminating hexapod {device_name} control server for {device_id}...")

    out = redirect_output_to_log(f".{device_name.lower()}_cs.{device_id.lower()}.stop.log")

    cmd = [sys.executable, "-m", f"egse.hexapod.symetrie.{device_name.lower()}_cs", "stop", device_id]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


# ---------- PUNA Commands ---------------------------------------------------------------------------------------------


@puna.command(name="start")
def start_puna(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """
    Start the PUNA hexapod control server. The control server is always started in the background.
    """
    start_hexapod_cs_process("PUNA", device_id, simulator)


@puna.command(name="stop")
def stop_puna(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stop the PUNA hexapod control server."""

    stop_hexapod_cs_process("PUNA", device_id)


@puna.command(name="status")
def status_puna(device_id: str):
    """Print status information on the PUNA hexapod control server."""

    with all_logging_disabled():
        from egse.hexapod.symetrie import puna_cs

        puna_cs.status(device_id)


@puna.command(name="start-sim")
def start_puna_sim(device_id: str):
    """Start the PUNA Hexapod Simulator (the device simulator)."""

    rich.print(
        textwrap.dedent(
            f"""\
            [orange3]The PUNA simulator is in development, for now use the `--sim` option when starting the control 
            server.[/]
            
            The `--sim` option will use a Controller clas that doesn't send commands to the device, but simulates
            the requests by performing actions on the reference frames defined in the hexapod. This means you are 
            not exercising the actual device commanding, but the net result or outcome is the same.
            
            usage: cgse puna start --sim {device_id}
            """
        )
    )
    return

    rich.print("Starting service PUNA Simulator")

    out = redirect_output_to_log(f".puna_sim.{device_id.lower()}.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.hexapod.symetrie.puna_sim", "start", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


@puna.command(name="stop-sim")
def stop_puna_sim(device_id: str):
    """Stop the PUNA Hexapod Simulator."""
    rich.print("Terminating the PUNA simulator.")

    out = redirect_output_to_log(f".puna_sim.{device_id.lower()}.stop.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.hexapod.symetrie.puna_sim", "stop", device_id],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


# ---------- ZONDA Commands --------------------------------------------------------------------------------------------


@zonda.command(name="start")
def start_zonda(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="use a device simulator as the backend")
    ] = False,
):
    """
    Start the ZONDA hexapod control server. The control server is always started in the background.
    """

    start_hexapod_cs_process("ZONDA", device_id, simulator)


@zonda.command(name="stop")
def stop_zonda(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
):
    """Stop the ZONDA hexapod control server."""

    stop_hexapod_cs_process("ZONDA", device_id)


@zonda.command(name="status")
def status_zonda(device_id: str):
    """Print status information on the ZONDA hexapod control server."""

    with all_logging_disabled():
        from egse.hexapod.symetrie import zonda_cs

        zonda_cs.status(device_id)
