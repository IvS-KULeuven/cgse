# An example plugin for the `cgse {start,stop,status} service` command from `cgse-core`.
#
import rich
import typer

puna = typer.Typer(
    name="puna",
    help="PUNA Positioning Hexapod, Symétrie",
    no_args_is_help=True
)


@puna.command(name="start")
def start_puna():
    """Start the PUNA service."""
    rich.print("Starting service PUNA")


@puna.command(name="stop")
def stop_puna():
    """Stop the PUNA service."""
    rich.print("Terminating service PUNA")


@puna.command(name="status")
def status_puna():
    """Print status information on the PUNA service."""
    rich.print("Printing the status of PUNA")


@puna.command(name="start-simulator")
def start_puna_sim():
    """Start the PUNA Simulator."""
    rich.print("Starting service PUNA Simulator")
