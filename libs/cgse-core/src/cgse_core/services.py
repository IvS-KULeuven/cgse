import asyncio

import rich
import typer

from ._start import start_log_cs, start_sm_cs, start_cm_cs
from ._stop import stop_log_cs, stop_sm_cs, stop_cm_cs
from ._status import run_all_status

app = typer.Typer(
    name="core",
    help="handle core services: start, stop, status",
    no_args_is_help=True
)


@app.command(name="start")
def start_core_services():
    """Start the core services in the background."""

    rich.print("[green]Starting the core services...[/]")

    start_log_cs()
    start_sm_cs()
    start_cm_cs()


@app.command(name="stop")
def stop_core_services():
    """Stop the core services."""

    rich.print("[green]Terminating the core services...[/]")

    stop_cm_cs()
    stop_sm_cs()
    stop_log_cs()


@app.command(name="status")
def status_core_services(full: bool = False):
    """Print the status of the core services."""
    # from scripts._status import status_log_cs, status_sm_cs, status_cm_cs

    rich.print("[green]Status of the core services...[/]")

    asyncio.run(run_all_status(full))

    # status_log_cs()
    # status_sm_cs()
    # status_cm_cs()
