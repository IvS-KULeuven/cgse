"""
The Configuration Manager is a server that controls and distributes configuration settings.

The following functionality is provided:

* creation and distribution of observation identifiers
* start and end of observations or tests
* maintain proper Setups and distribute the latest Setup on demand

"""
import logging
import multiprocessing
import sys
from pathlib import Path
from typing import Annotated

import rich
import typer
import zmq
from prometheus_client import start_http_server

from egse.confman import ConfigurationManagerProtocol
from egse.confman import ConfigurationManagerProxy
from egse.control import ControlServer
from egse.env import get_conf_data_location
from egse.process import SubProcess
from egse.response import Failure
from egse.response import Response
from egse.settings import Settings
from egse.storage import store_housekeeping_information

# Use explicit name here otherwise the logger will probably be called __main__

logger = logging.getLogger("egse.confman.confman_cs")

CTRL_SETTINGS = Settings.load("Configuration Manager Control Server")


class ConfigurationManagerControlServer(ControlServer):
    def __init__(self):
        super().__init__()

        self.device_protocol = ConfigurationManagerProtocol(self)

        self.logger = logger
        self.logger.debug(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.set_hk_delay(10.0)

        self.logger.info(f"CM housekeeping saved every {self.hk_delay / 1000:.1f} seconds.")

    def get_communication_protocol(self):
        return CTRL_SETTINGS.PROTOCOL

    def get_commanding_port(self):
        return CTRL_SETTINGS.COMMANDING_PORT

    def get_service_port(self):
        return CTRL_SETTINGS.SERVICE_PORT

    def get_monitoring_port(self):
        return CTRL_SETTINGS.MONITORING_PORT

    def get_storage_mnemonic(self):
        try:
            return CTRL_SETTINGS.STORAGE_MNEMONIC
        except AttributeError:
            return "CM"

    def is_storage_manager_active(self):
        from egse.storage import is_storage_manager_active
        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Send housekeeping information to the Storage manager."""

        origin = self.get_storage_mnemonic()
        store_housekeeping_information(origin, data)

    def register_to_storage_manager(self):
        from egse.storage import register_to_storage_manager
        from egse.storage.persistence import TYPES

        register_to_storage_manager(
            origin=self.get_storage_mnemonic(),
            persistence_class=TYPES["CSV"],
            prep={
                "column_names": list(self.device_protocol.get_housekeeping().keys()),
                "mode": "a",
            }
        )

    def unregister_from_storage_manager(self):
        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=self.get_storage_mnemonic())

    def before_serve(self):
        start_http_server(CTRL_SETTINGS.METRICS_PORT)


app = typer.Typer(name="cm_cs", no_args_is_help=True)


@app.command()
def start():
    """
    Starts the Configuration Manager (cm_cs). The cm_cs is a server which handles the
    configuration (aka Setup) of your test system.

    The cm_cs is normally started automatically on egse-server boot.
    """

    multiprocessing.current_process().name = "cm_cs"

    try:
        check_prerequisites()
    except RuntimeError as exc:
        logger.info(exc)
        return 0

    try:
        control_server = ConfigurationManagerControlServer()
        control_server.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exit_code:
        print(f"System Exit with code {exit_code}.")
        sys.exit(exit_code.code)
    except Exception:
        import traceback

        traceback.print_exc(file=sys.stdout)

    return 0


@app.command()
def start_bg():
    """Start the Configuration Manager Control Server in the background."""
    proc = SubProcess("cm_cs", ["cm_cs", "start"])
    proc.execute()


@app.command()
def stop():
    """Send a 'quit_server' command to the Configuration Manager."""
    try:
        with ConfigurationManagerProxy() as cm:
            sp = cm.get_service_proxy()
            sp.quit_server()
    except ConnectionError:
        rich.print("[red]ERROR: Couldn't connect to the configuration manager.[/]")


@app.command()
def status():
    """Print the status of the control server."""

    import rich
    from egse.confman import get_status

    rich.print(get_status(), end='')


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def list_setups(ctx: Annotated[typer.Context, typer.Option()] = None):
    """List available Setups."""

    args = ctx.args if ctx else []

    # These extra arguments need to be converted into a dictionary as expected by
    # the function egse.system.filter_by_attr()
    for extra_arg in args:
        print(f"Got extra arg: {extra_arg}")

    with ConfigurationManagerProxy() as cm:
        setups = cm.list_setups(**{})
    if isinstance(setups, Failure):
        rich.print(f"[red]ERROR: {setups}[/]")
        rich.print("Check the log file for a more detailed error message.")
        return
    if setups:
        # We want to have the most recent (highest id number) last, but keep the site together
        setups = sorted(setups, key=lambda x: (x[1], x[0]))
        print("\n".join(f"{setup}" for setup in setups))


@app.command()
def load_setup(setup_id: int):
    """Load the given Setup on the configuration manager."""

    with ConfigurationManagerProxy() as cm:
        setup = cm.load_setup(setup_id)
    if isinstance(setup, Response):
        print(setup)
        return
    if setup.has_private_attribute("_setup_id"):
        setup_id = setup.get_private_attribute("_setup_id")
        print(f"{setup_id} loaded on configuration manager.")


@app.command()
def reload_setups():
    """ Clears the cache and re-loads the available setups.

    Note that this does not affect the currently loaded setup.
    """

    with ConfigurationManagerProxy() as pm:
        pm.reload_setups()


def check_prerequisites():
    """Checks if all prerequisites for running the Configuration Manager are met.

    Raises:
        RuntimeError when one or more of the prerequisites is not met.
    """

    fails = 0

    # We need a proper location for storing the configuration data.

    location = get_conf_data_location()

    if not location:
        raise RuntimeError(
            "The location for the configuration data is not defined. Please check your environment."
        )

    location = Path(location)

    if not location.exists():
        logger.error(
            f"The directory {location} does not exist, provide a writable location for "
            f"storing the configuration data."
        )
        fails += 1

    logger.debug(f"location = {location}")

    # now raise the final verdict

    if fails:
        raise RuntimeError(
            "Some of the prerequisites for the Configuration Manager haven't met. "
            "Please check the logs."
        )


if __name__ == "__main__":

    sys.exit(app())
