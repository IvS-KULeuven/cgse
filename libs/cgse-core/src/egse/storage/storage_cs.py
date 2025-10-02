"""
The Storage Manager Control Server, aka Storage Manager, is the service which saves all data coming
from any component in the Common-EGSE.

The Storage manager is implemented as a standard control server.

"""

__all__ = [
    "StorageControlServer",
    "StorageProxy",
]

import logging
import multiprocessing
import sys
from pathlib import Path
from typing import Annotated
from typing import Callable

import rich
import typer
import zmq
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import utc
from rich.console import Console

from egse.control import ControlServer
from egse.env import get_data_storage_location
from egse.env import get_site_id
from egse.logger import remote_logging
from egse.process import SubProcess
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.storage import (
    StorageProtocol,
    PROCESS_NAME,
    SERVICE_TYPE,
    PROTOCOL,
    COMMANDING_PORT,
    SERVICE_PORT,
    MONITORING_PORT,
    HOSTNAME,
)
from egse.storage import StorageProxy
from egse.storage import cycle_daily_files
from egse.zmq_ser import get_port_number

# Use explicit name here otherwise the logger will probably be called __main__

logger = logging.getLogger("egse.storage")
SITE_ID = get_site_id()


class StorageControlServer(ControlServer):
    """
    The Storage Manager Control Server (aka Storage Manager) saves information from registered components.
    """

    def __init__(self):
        super().__init__()

        multiprocessing.current_process().name = PROCESS_NAME

        self.scheduler: BackgroundScheduler | None = None

        self.logger = logger
        self.service_name = PROCESS_NAME
        self.service_type = SERVICE_TYPE

        self.device_protocol = StorageProtocol(self)

        self.logger.debug(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service(service_type=SERVICE_TYPE)

    def before_serve(self):
        self.scheduler = BackgroundScheduler(timezone=utc)
        self.scheduler.start()
        self.scheduler.add_job(cycle_daily_files, "cron", day="*")

    def after_serve(self):
        self.scheduler.shutdown()
        self.deregister_service()

    def get_communication_protocol(self):
        return PROTOCOL

    def get_commanding_port(self):
        return get_port_number(self.dev_ctrl_cmd_sock) or COMMANDING_PORT

    def get_service_port(self):
        return get_port_number(self.dev_ctrl_service_sock) or SERVICE_PORT

    def get_monitoring_port(self):
        return get_port_number(self.dev_ctrl_mon_sock) or MONITORING_PORT

    def get_event_subscriptions(self) -> list[str]:
        return ["new_setup"]

    def get_event_handlers(self) -> dict[str, Callable]:
        return {"new_setup": self.handle_event_new_setup}

    def handle_event_new_setup(self, event_data: dict):
        if data := event_data.get("data"):
            if setup_id := data.get("setup_id"):
                self.device_protocol.controller.load_setup(int(setup_id))
            else:
                self.logger.error("Event data doesn't have a setup_id, couldn't load new Setup.")
                self.logger.debug(f"{event_data=}")
        else:
            self.logger.error("Event data has no 'data' key, corrupt notification event.")
            self.logger.debug(f"{event_data=}")


app = typer.Typer(name=PROCESS_NAME)

console = Console(width=120)


@app.command()
def start():
    """Start the Storage Manager."""

    multiprocessing.current_process().name = PROCESS_NAME

    # We import this class such that the class name is
    # 'egse.storage.storage_cs.StorageControlServer' and we
    # can compare self with isinstance inside the Control.
    # If this import is not done, the class name for the
    # StorageControlServer would be '__main__.StorageControlServer'.

    from egse.storage.storage_cs import StorageControlServer  # noqa

    with remote_logging():
        try:
            check_prerequisites()
        except RuntimeError as exc:
            logger.info(exc)
            return 0

        try:
            control_server = StorageControlServer()
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
    """Start the Storage Manager Control Server in the background."""
    proc = SubProcess("sm_cs", ["sm_cs", "start"])
    proc.execute()


@app.command()
def stop():
    """Send a 'quit_server' command to the Storage Manager."""

    if COMMANDING_PORT == 0:
        with RegistryClient() as reg:
            service = reg.discover_service(SERVICE_TYPE)
            rich.print("service = ", service)
            if service:
                hostname = service["host"]
                port = service["metadata"]["service_port"]
            else:
                rich.print(
                    "[red]ERROR: Couldn't determine how to connect to the storage manager. No service defined.[/]"
                )
                return

    else:
        hostname = HOSTNAME
        port = SERVICE_PORT

    rich.print("[green]Sending 'quit' command to storage manager..[/]")
    try:
        with ServiceProxy(hostname=hostname, port=port) as proxy:
            proxy.quit_server()
    except ConnectionError as exc:
        console.print(f"[red]ERROR: Couldn't connect to storage manager: {exc}[/]")


@app.command()
def status(full: Annotated[bool, typer.Option(help="Give a full status report")] = False):
    """Print the status of the control server."""

    import rich
    from egse.storage import get_status

    rich.print(get_status(full=full), end="")


def check_prerequisites():
    """Checks if all prerequisites for running the Storage Manager are met.

    Raises:
        RuntimeError when one or more of the prerequisites is not met.
    """

    fails = 0

    # We need a proper location for storing the data, this directory shall contain
    # two subfolders: 'daily' and 'obs'.

    location = get_data_storage_location(site_id=SITE_ID)

    if not location:
        raise RuntimeError("The data storage location is not defined. Please check your environment.")

    location = Path(location)

    if not location.exists():
        logger.error(f"The directory {location} does not exist, provide a writable location for storing the data.")
        fails += 1

    logger.debug(f"location = {location}")

    daily_dir = location / "daily"
    obs_dir = location / "obs"

    if not daily_dir.exists():
        logger.error("The data storage location shall have a 'daily' sub-folder.")
        fails += 1
    if not obs_dir.exists():
        logger.error("The data storage location shall have a 'obs' sub-folder.")
        fails += 1

    # now raise the final verdict

    if fails:
        raise RuntimeError("Some of the prerequisites for the Storage Manager haven't met. Please check the logs.")


if __name__ == "__main__":
    sys.exit(app())
