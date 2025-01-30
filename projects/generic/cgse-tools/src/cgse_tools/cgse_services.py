# An example plugin for the `cgse {start,stop,status} service` command from `cgse-core`.
#
import rich
import typer

dev_x = typer.Typer(
    name="dev-x",
    help="device-x is an imaginary device that serves as an example",
    no_args_is_help=True
)


@dev_x.command(name="start")
def start_dev_x():
    """Start the dev-x service."""
    rich.print("Starting service dev_x")


@dev_x.command(name="stop")
def stop_dev_x():
    """Stop the dev-x service."""
    rich.print("Terminating service dev_x")


@dev_x.command(name="status")
def status_dev_x():
    """Print status information on the dev-x service."""
    rich.print("Printing the status of dev_x")
