"""
The Storage Control Server, aka Storage Manager, is the service which saves all data coming
from any component in the Common-EGSE.

The Storage manager is implemented as a standard control server.

"""
import logging
import multiprocessing
import sys
from pathlib import Path

import click
import rich
import zmq
from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import start_http_server
from pytz import utc

from egse.control import ControlServer
from egse.env import get_data_storage_location
from egse.env import get_site_id
from egse.process import SubProcess
from egse.settings import Settings
from egse.storage import StorageProtocol
from egse.storage import StorageProxy
from egse.storage import cycle_daily_files

# Use explicit name here otherwise the logger will probably be called __main__

logger = logging.getLogger("egse.storage.storage_cs")

CTRL_SETTINGS = Settings.load("Storage Control Server")
SITE_ID = get_site_id()


class StorageControlServer(ControlServer):
    """
    The Storage Control Server (aka Storage Manager) saves information from registered components.
    """

    def __init__(self):
        super().__init__()

        self.device_protocol = StorageProtocol(self)

        self.logger = logger
        self.logger.debug(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

    def before_serve(self):

        self.scheduler = BackgroundScheduler(timezone=utc)
        self.scheduler.start()
        self.scheduler.add_job(cycle_daily_files, "cron", day="*")

        start_http_server(CTRL_SETTINGS.METRICS_PORT)

    def after_serve(self):
        self.scheduler.shutdown()

    def get_communication_protocol(self):
        return CTRL_SETTINGS.PROTOCOL

    def get_commanding_port(self):
        return CTRL_SETTINGS.COMMANDING_PORT

    def get_service_port(self):
        return CTRL_SETTINGS.SERVICE_PORT

    def get_monitoring_port(self):
        return CTRL_SETTINGS.MONITORING_PORT


@click.group()
def cli():
    pass


@cli.command()
def start():
    """Start the Storage Manager."""

    multiprocessing.current_process().name = "storage_cs"

    # We import this class such that the class name is
    # 'egse.storage.storage_cs.StorageControlServer' and we
    # can compare self with isinstance inside the Control.
    # If this import is not done, the class name for the
    # StorageControlServer would be '__main__.StorageControlServer'.

    from egse.storage.storage_cs import StorageControlServer

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
        print("System Exit with code {}.".format(exit_code))
        sys.exit(exit_code)
    except Exception:
        import traceback

        traceback.print_exc(file=sys.stdout)

    return 0


@cli.command()
def start_bg():
    """Start the Storage Manager Control Server in the background."""
    proc = SubProcess("sm_cs", ["sm_cs", "start"])
    proc.execute()


@cli.command()
def stop():
    """Send a 'quit_server' command to the Storage Manager."""
    try:
        with StorageProxy() as sm:
            sp = sm.get_service_proxy()
            sp.quit_server()
    except ConnectionError as exc:
        rich.print("[red]ERROR: Couldn't connect to the storage manager.[/]")


@cli.command()
@click.option("--full", is_flag=True, help="Give a full status report")
def status(full):
    """Print the status of the control server."""

    import rich
    from egse.storage import get_status

    rich.print(get_status(full=full), end='')


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
        raise RuntimeError(
            "The data storage location is not defined. Please check your environment."
        )

    location = Path(location)

    if not location.exists():
        logger.error(
            f"The directory {location} does not exist, provide a writable location for "
            f"storing the data."
        )
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
        raise RuntimeError(
            "Some of the prerequisites for the Storage Manager haven't met. "
            "Please check the logs."
        )


if __name__ == "__main__":
    sys.exit(cli())
