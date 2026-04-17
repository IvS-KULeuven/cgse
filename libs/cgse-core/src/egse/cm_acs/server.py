"""Asynchronous Configuration Manager server."""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path
from typing import Any

import rich
import typer
from egse.env import bool_env
from egse.env import get_conf_data_location
from egse.log import logging
from egse.process import SubProcess
from egse.settings import Settings
from egse.system import TyperAsyncCommand
from rich.console import Console

import egse.cm_acs as cm_acs_module
from egse.async_control import AsyncControlServer
from egse.async_control import DeviceCommandRouter
from egse.async_control import ServiceCommandRouter
from egse.cm_acs.client import AsyncConfigurationManagerClient
from egse.cm_acs.controller import AsyncConfigurationManagerController
from egse.cm_acs.services import AsyncConfigurationManagerServices
from egse.logger import remote_logging
from egse.registry.client import AsyncRegistryClient
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy

try:
    from typing import override  # type: ignore[import]
except ImportError:
    from typing_extensions import override


logger = logging.getLogger("egse.cm_acs")

settings = Settings.load("Configuration Manager Control Server")


class AsyncConfigurationManagerControlServer(AsyncControlServer):
    """Async server that forwards commands to a native async controller."""

    service_type = cm_acs_module.SERVICE_TYPE
    service_name = cm_acs_module.PROCESS_NAME
    device_commanding_port = cm_acs_module.COMMANDING_PORT
    service_commanding_port = cm_acs_module.SERVICE_PORT

    def __init__(self):
        multiprocessing.current_process().name = cm_acs_module.PROCESS_NAME

        super().__init__()

        self.logger = logger

    def _create_device_command_router(self) -> DeviceCommandRouter:
        return AsyncConfigurationManagerController(self)

    def _create_service_command_router(self) -> ServiceCommandRouter:
        return AsyncConfigurationManagerServices(self, self.controller)

    @property
    def controller(self) -> AsyncConfigurationManagerController:
        return self._device_command_router  # type: ignore[return-value]

    @property
    def services(self) -> AsyncConfigurationManagerServices:
        return self._service_command_router  # type: ignore[return-value]

    @override
    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        info.update(
            {
                "controller": "native-async",
            }
        )
        return info

    def stop(self):
        self.controller.quit()
        super().stop()


app = typer.Typer(name=cm_acs_module.PROCESS_NAME)

console = Console(width=120)

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")


@app.command(cls=TyperAsyncCommand)
async def start():
    """Starts the asynchronous Configuration Manager control server."""

    multiprocessing.current_process().name = cm_acs_module.PROCESS_NAME

    with remote_logging():
        try:
            check_prerequisites()
        except RuntimeError as exc:
            logger.info(exc)
            return 0

        try:
            control_server = AsyncConfigurationManagerControlServer()
            await control_server.start()
        except KeyboardInterrupt:
            print("Shutdown requested...exiting")
        except SystemExit as exit_code:
            print(f"System Exit with code {exit_code}.")
            sys.exit(exit_code.code)
        except Exception as exc:
            if VERBOSE_DEBUG:
                import traceback

                traceback.print_exc(file=sys.stdout)
            else:
                console.print(f"[red]ERROR: Failed to start async configuration manager: {exc}[/]")

    return 0


@app.command()
def start_bg():
    """Start the asynchronous Configuration Manager control server in the background."""
    proc = SubProcess("cm_acs", [sys.executable, "-m", "egse.cm_acs.server", "start"])
    proc.execute()


@app.command(cls=TyperAsyncCommand)
async def stop():
    """Send a terminate command to the asynchronous Configuration Manager."""
    try:
        async with AsyncConfigurationManagerClient() as proxy:
            await proxy.stop_server()
    except Exception as exc:
        if VERBOSE_DEBUG:
            console.print(f"[red]ERROR: Couldn't connect to async configuration manager: {exc}[/]")
        else:
            console.print("[red]ERROR: Couldn't connect to async configuration manager.[/]")


@app.command(cls=TyperAsyncCommand)
async def status():
    """Print the status of the asynchronous control server."""

    try:
        async with AsyncConfigurationManagerClient() as proxy:
            info = await proxy.info()
            health = await proxy.confman_health()
    except Exception as exc:
        if VERBOSE_DEBUG:
            rich.print(f"Async Configuration Manager Status: [red]not active[/] ({exc})")
        else:
            rich.print("Async Configuration Manager Status: [red]not active[/]")
        return

    service_name = info.get("name") if isinstance(info, dict) else cm_acs_module.PROCESS_NAME
    host = info.get("hostname") if isinstance(info, dict) else "unknown"
    cmd_port = info.get("device commanding port") if isinstance(info, dict) else "unknown"
    service_port = info.get("service commanding port") if isinstance(info, dict) else "unknown"

    confman_state = health.get("confman", {}) if isinstance(health, dict) else {}
    obsid = confman_state.get("obsid")
    setup_id = confman_state.get("setup_id")

    rich.print(
        "\n".join(
            [
                f"{service_name}:",
                "    Status: [green]active[/]",
                f"    Running observation: {obsid if obsid else 'none'}",
                f"    Setup loaded: {setup_id if setup_id is not None else 'unknown'}",
                f"    Hostname: {host}",
                f"    Commanding port: {cmd_port}",
                f"    Service port: {service_port}",
            ]
        )
    )


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True}, cls=TyperAsyncCommand)
async def list_setups(ctx: typer.Context):
    """List available setups from the async configuration manager."""
    console = Console()
    args = ctx.args
    if VERBOSE_DEBUG:
        for extra_arg in args:
            console.print(f"Got extra arg: {extra_arg}")

    try:
        async with AsyncConfigurationManagerClient() as cm:
            response = await cm.list_setups(attr={})
            console.print(f"Received response: {response}, {type(response)=}")

    except Exception as exc:
        if VERBOSE_DEBUG:
            console.print_exception(show_locals=True)
        else:
            console.print(f"[red]ERROR: Failed to list setups: {exc}[/]")
        return

    if response:
        setups = sorted(response, key=lambda x: (x[1], x[0]))
        print("\n".join(f"{setup}" for setup in setups))


@app.command(cls=TyperAsyncCommand)
async def load_setup(setup_id: int):
    """Load the given setup on the async configuration manager."""

    console = Console()

    try:
        async with AsyncConfigurationManagerClient() as cm:
            response = await cm.load_setup(setup_id)
    except Exception as exc:
        if VERBOSE_DEBUG:
            console.print_exception(show_locals=True)
        else:
            console.print(f"[red]ERROR: Failed to load setup: {exc}[/]")
        return

    loaded = response
    console.print(loaded)
    console.print(type(loaded))
    if isinstance(loaded, dict) and loaded.get("_setup_id"):
        console.print(f"{loaded['_setup_id']} loaded on async configuration manager.")
    else:
        console.print(response.get("message"))


@app.command(cls=TyperAsyncCommand)
async def reload_setups():
    """Clear cache and re-load available setups."""

    async with AsyncConfigurationManagerClient() as cm_proxy:
        await cm_proxy.reload_setups()


@app.command(cls=TyperAsyncCommand)
async def register_to_storage():
    # The service will register the control server to the storage, i.e. with the STORAGE_MNEMONIC from the Settings
    # of that control server.

    async with AsyncRegistryClient() as reg:
        service = await reg.discover_service(cm_acs_module.SERVICE_TYPE)

        if service:
            rich.print(
                f"Registering CM to the storage manager on {service['host']}:{service['metadata']['service_port']}"
            )
            with ServiceProxy(hostname=service["host"], port=service["metadata"]["service_port"]) as service_proxy:
                service_proxy.register_to_storage()  # register the control server
        else:
            rich.print("[red]ERROR: Couldn't connect to 'cm_acs', process probably not running.[/]")

    # The configuration manager controller will register the obsid table to the storage with the `obsid` name.

    async with AsyncConfigurationManagerClient() as cm_client:
        response = await cm_client.register_to_storage()
        logger.debug(f"Response from register_to_storage: {response}")
        if not response.get("success"):
            rich.print(f"[red]ERROR: {response.get('message')}[/]")


@app.command(cls=TyperAsyncCommand)
async def xregister_to_storage():
    """Register async configuration manager data to storage."""

    with RegistryClient() as reg:
        service = reg.discover_service(cm_acs_module.SERVICE_TYPE)
        if service:
            rich.print(
                f"Registering async CM to storage manager on {service['host']}:{service['metadata']['service_port']}"
            )
        else:
            rich.print("[red]ERROR: Couldn't connect to async configuration manager, process probably not running.[/]")

    async with AsyncConfigurationManagerClient() as cm_proxy:
        response = await cm_proxy.register_to_storage()
        logger.debug(f"Response from register_to_storage: {response}")
        if not response.get("success"):
            rich.print(f"[red]ERROR: {response.get('message')}[/]")


def check_prerequisites():
    """Checks if all prerequisites for running the Configuration Manager are met.

    - The location for the configuration data is defined and points to an existing directory.

    Raises:
        RuntimeError when one or more of the prerequisites is not met.

    """

    fails = 0

    location = get_conf_data_location()

    if not location:
        raise RuntimeError("The location for the configuration data is not defined. Please check your environment.")

    location = Path(location).expanduser()

    if not location.exists():
        logger.error(
            f"The directory {location} does not exist, provide a writable location for storing the configuration data."
        )
        fails += 1

    logger.debug(f"location = {location}")

    if fails:
        raise RuntimeError(
            "Some of the prerequisites for the Configuration Manager haven't met. Please check the logs."
        )


if __name__ == "__main__":
    sys.exit(app())
