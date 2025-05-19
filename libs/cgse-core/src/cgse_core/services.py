import asyncio
import logging

import rich
import typer

from egse.registry.client import AsyncRegistryClient
from egse.system import TyperAsyncCommand
from ._start import start_rs_cs, start_log_cs, start_sm_cs, start_cm_cs
from ._stop import stop_rs_cs, stop_log_cs, stop_sm_cs, stop_cm_cs
from ._status import run_all_status

core = typer.Typer(
    name="core",
    help="handle core services: start, stop, status",
    no_args_is_help=True
)


@core.command(name="start")
def start_core_services():
    """Start the core services in the background."""

    rich.print("[green]Starting the core services...[/]")

    start_rs_cs()
    start_log_cs()
    start_sm_cs()
    start_cm_cs()


@core.command(name="stop")
def stop_core_services():
    """Stop the core services."""

    rich.print("[green]Terminating the core services...[/]")

    stop_cm_cs()
    stop_sm_cs()
    stop_log_cs()
    stop_rs_cs()


@core.command(name="status")
def status_core_services(full: bool = False):
    """Print the status of the core services."""
    # from scripts._status import status_log_cs, status_sm_cs, status_cm_cs

    logging.basicConfig(
        level=logging.WARNING,
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-20s %(lineno)5d:%(module)-20s %(message)s",
    )

    rich.print("[green]Status of the core services...[/]")

    asyncio.run(run_all_status(full))


reg = typer.Typer(
    name="registry",
    help="handle registry services: start, stop, status",
    no_args_is_help=True
)


@reg.command(cls=TyperAsyncCommand, name="show-services")
async def reg_show_services():
    """Print the active services that are registered."""
    with AsyncRegistryClient() as client:
        services = await client.list_services()

        rich.print(services)
