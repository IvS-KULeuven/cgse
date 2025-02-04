# An example plugin for the `cgse {start,stop,status} service` command from `cgse-core`.
#
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
    rich.print("Printing the status of daq6510")


@daq6510.command(name="start-simulator")
def start_daq6510_sim():
    """Start the DAQ6510 Simulator."""
    rich.print("Starting service DAQ6510 Simulator")
