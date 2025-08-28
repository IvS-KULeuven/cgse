import asyncio
import logging
import time
from pathlib import Path

import rich
import typer

from egse.registry.client import AsyncRegistryClient
from egse.signal import DEFAULT_SIGNAL_DIR
from egse.signal import create_signal_command_file
from egse.system import TyperAsyncCommand
from ._start import start_cm_cs
from ._start import start_log_cs
from ._start import start_notifyhub
from ._start import start_pm_cs
from ._start import start_rm_cs
from ._start import start_sm_cs
from ._status import run_all_status
from ._status import status_cm_cs
from ._status import status_log_cs
from ._status import status_pm_cs
from ._status import status_rm_cs
from ._status import status_sm_cs
from ._stop import stop_cm_cs
from ._stop import stop_log_cs
from ._stop import stop_notifyhub
from ._stop import stop_pm_cs
from ._stop import stop_rm_cs
from ._stop import stop_sm_cs

core = typer.Typer(
    name="core",
    help="handle core services: start, stop, status, re-register",
)


@core.command(name="start")
def start_core_services(log_level: str = "WARNING"):
    """Start the core services in the background."""

    rich.print("[green]Starting the core services...[/]")

    start_rm_cs(log_level)
    start_log_cs()
    start_notifyhub()
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
    stop_notifyhub()

    # We need the logger for logging the termination process for other services, so leave it running for a while
    time.sleep(1.0)
    stop_log_cs()

    # We need the registry server to stop other core services, so leave it running for a while
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


@core.command(name="re-register")
def core_reregister(force: bool = False):
    """Command all core services to re-register as a service."""

    log_cs_reregister(force)
    cm_cs_reregister(force)
    sm_cs_reregister(force)
    pm_cs_reregister(force)


rm_cs = typer.Typer(
    name="rm_cs",
    help="handle registry services: start, stop, status, list-services",
)


@rm_cs.command(name="start")
def rm_cs_start(log_level: str = "WARNING"):
    """Start the Service Registry Manager."""
    start_rm_cs(log_level)


@rm_cs.command(name="stop")
def rm_cs_stop():
    """Stop the Service Registry Manager."""
    stop_rm_cs()


@rm_cs.command(cls=TyperAsyncCommand, name="status")
async def rm_cs_status(suppress_errors: bool = True):
    """Print the status of the Service Registry Manager."""
    await status_rm_cs(suppress_errors)


@rm_cs.command(cls=TyperAsyncCommand, name="list-services")
async def reg_list_services():
    """Print the active services that are registered."""
    with AsyncRegistryClient() as client:
        services = await client.list_services()

        rich.print(services)


log_cs = typer.Typer(
    name="log_cs",
    help="handle log services: start, stop, status, re-register",
)


@log_cs.command(name="start")
def log_cs_start():
    """Start the Logger."""
    start_log_cs()


@log_cs.command(name="stop")
def log_cs_stop():
    """Stop the Logger."""
    stop_log_cs()


@log_cs.command(cls=TyperAsyncCommand, name="status")
async def log_cs_status(suppress_errors: bool = True):
    """Return the status of the Logger."""
    await status_log_cs(suppress_errors)


@log_cs.command(name="re-register")
def log_cs_reregister(force: bool = False):
    """Command the Logger to re-register as a service."""

    from egse.logger.log_cs import app_name

    create_signal_command_file(
        Path(DEFAULT_SIGNAL_DIR),
        app_name,
        {"action": "reregister", "params": {"force": force}},
    )


cm_cs = typer.Typer(
    name="cm_cs",
    help="handle configuration manager: start, stop, status, re-register",
)


@cm_cs.command(name="start")
def cm_cs_start():
    """Start the Configuration Manager."""
    start_cm_cs()


@cm_cs.command(name="stop")
def cm_cs_stop():
    """Stop the Configuration Manager."""
    stop_cm_cs()


@cm_cs.command(cls=TyperAsyncCommand, name="status")
async def cm_cs_status(suppress_errors: bool = True):
    """Print the status of the Configuration Manager."""
    await status_cm_cs(suppress_errors)


@cm_cs.command(name="re-register")
def cm_cs_reregister(force: bool = False):
    """Command the Configuration Manager to re-register as a service."""

    from egse.confman.confman_cs import app_name

    create_signal_command_file(
        Path(DEFAULT_SIGNAL_DIR),
        app_name,
        {"action": "reregister", "params": {"force": force}},
    )


@cm_cs.command(name="register-to-storage")
def cm_cs_register_to_storage():
    from egse.confman.confman_cs import register_to_storage

    register_to_storage()


sm_cs = typer.Typer(
    name="sm_cs",
    help="handle storage manager: start, stop, status, re-register",
)


@sm_cs.command(name="start")
def sm_cs_start():
    """Start the Storage Manager."""
    start_sm_cs()


@sm_cs.command(name="stop")
def sm_cs_stop():
    """Stop the Storage Manager."""
    stop_sm_cs()


@sm_cs.command(cls=TyperAsyncCommand, name="status")
async def sm_cs_status(suppress_errors: bool = True):
    """Print the status of the Storage Manager."""
    await status_sm_cs(suppress_errors)


@sm_cs.command(name="re-register")
def sm_cs_reregister(force: bool = False):
    """Command the Storage Manager to re-register as a service."""

    from egse.storage.storage_cs import app_name

    create_signal_command_file(
        Path(DEFAULT_SIGNAL_DIR),
        app_name,
        {"action": "reregister", "params": {"force": force}},
    )


pm_cs = typer.Typer(
    name="pm_cs",
    help="handle process manager: start, stop, status, re-register",
)


@pm_cs.command(name="start")
def pm_cs_start():
    """Start the Process Manager."""
    start_pm_cs()


@pm_cs.command(name="stop")
def pm_cs_stop():
    """Stop the Process Manager."""
    stop_pm_cs()


@pm_cs.command(cls=TyperAsyncCommand, name="status")
async def pm_cs_status(suppress_errors: bool = True):
    """Print the status of the Process Manager."""
    await status_pm_cs(suppress_errors)


@pm_cs.command(name="re-register")
def pm_cs_reregister(force: bool = False):
    """Command the Storage Manager to re-register as a service."""

    from egse.procman.procman_cs import app_name

    create_signal_command_file(
        Path(DEFAULT_SIGNAL_DIR),
        app_name,
        {"action": "reregister", "params": {"force": force}},
    )


notifyhub = typer.Typer(
    name="notifyhub",
    help="handle notification hub: start, stop, status, re-register",
)


@notifyhub.command(name="start")
def notifyhub_start():
    """Start the Process Manager."""
    start_notifyhub()


@notifyhub.command(name="stop")
def notifyhub_stop():
    """Stop the Process Manager."""
    stop_notifyhub()
