import asyncio
import logging
import time

import rich
import typer

from egse.registry.client import AsyncRegistryClient
from egse.system import TyperAsyncCommand
from ._start import start_rm_cs, start_log_cs, start_sm_cs, start_cm_cs, start_pm_cs
from ._status import status_rm_cs
from ._stop import stop_rm_cs, stop_log_cs, stop_sm_cs, stop_cm_cs, stop_pm_cs
from ._status import run_all_status

core = typer.Typer(
    name="core",
    help="handle core services: start, stop, status",
    no_args_is_help=True
)


@core.command(name="start")
def start_core_services(log_level: str = "WARNING"):
    """Start the core services in the background."""

    rich.print("[green]Starting the core services...[/]")

    start_rm_cs(log_level)
    start_log_cs()
    start_sm_cs()
    start_cm_cs()
    start_pm_cs()


@core.command(name="stop")
def stop_core_services():
    """Stop the core services."""

    rich.print("[green]Terminating the core services...[/]")

    stop_pm_cs()
    stop_cm_cs()
    stop_sm_cs()
    stop_log_cs()
    # We need the registry server to stop other core services, so leave it running for one second
    time.sleep(1.0)
    stop_rm_cs()


@core.command(name="status")
def status_core_services(full: bool = False, suppress_errors: bool = True):
    """Print the status of the core services."""
    # from scripts._status import status_log_cs, status_sm_cs, status_cm_cs

    logging.basicConfig(
        level=logging.WARNING,
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-20s %(lineno)5d:%(module)-20s %(message)s",
    )

    rich.print("[green]Status of the core services...[/]")

    asyncio.run(run_all_status(full, suppress_errors))


rm_cs = typer.Typer(
    name="rm_cs",
    help="handle registry services: start, stop, status, list-services",
    no_args_is_help=True
)


@rm_cs.command(name="start")
def rm_cs_start(log_level: str = "WARNING"):
    """Start the Service Registry Manager."""
    start_rm_cs(log_level)


@rm_cs.command(name="stop")
def rm_cs_stop():
    """Start the Service Registry Manager."""
    stop_rm_cs()


@rm_cs.command(cls=TyperAsyncCommand, name="status")
async def rm_cs_status(suppress_errors: bool = True):
    """Start the Service Registry Manager."""
    await status_rm_cs(suppress_errors)


@rm_cs.command(cls=TyperAsyncCommand, name="list-services")
async def reg_list_services():
    """Print the active services that are registered."""
    with AsyncRegistryClient() as client:
        services = await client.list_services()

        rich.print(services)
