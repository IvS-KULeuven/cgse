"""Control Server for the Digilent MEASURpoint DT8874."""

import logging
import multiprocessing
from typing import Annotated, Callable

import rich
import sys
import typer
import zmq

from egse.control import is_control_server_active, ControlServer
from egse.digilent.measurpoint.dt8874 import (
    PROCESS_NAME,
    SERVICE_TYPE,
    COMMANDING_PORT,
    SERVICE_PORT,
    MONITORING_PORT,
    ORIGIN,
    PROTOCOL,
    HOSTNAME,
)
from egse.digilent.measurpoint.dt8874.dt8874 import Dt8874Proxy
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.settings import Settings
from egse.setup import load_setup
from egse.storage import store_housekeeping_information
from egse.zmq_ser import connect_address, get_port_number

logger = logging.getLogger("egse.digilent.measurpoint.dt8874")
DEVICE_SETTINGS = Settings.load("Digilent MEASURpoint DT8874")


def is_dt8874_cs_active(timeout: float = 0.5) -> bool:
    """Checks whether the Digilent MEASURpoint DT8874 Control Server is running.

    Args:
        timeout (float): Timeout when waiting for a reply [s].

    Returns:
        True if the Digilent MEASURpoint DT8874 Control Server is running and replied with the expected answer; False
        otherwise.
    """

    if COMMANDING_PORT != 0:
        protocol = PROTOCOL
        hostname = HOSTNAME
        port = COMMANDING_PORT

    else:
        with RegistryClient() as reg:
            service = reg.discover_service(SERVICE_TYPE)

            if service:
                protocol = service.get("protocol", "tcp")
                hostname = service["host"]
                port = service["port"]

            else:
                return False

    # noinspection PyUnboundLocalVariable
    endpoint = connect_address(protocol, hostname, port)

    return is_control_server_active(endpoint, timeout)


class Dt8874ControlServer(ControlServer):
    def __init__(self, simulator: bool = False):
        super().__init__()

        multiprocessing.current_process().name = PROCESS_NAME

        self.logger = logger
        self.service_name = PROCESS_NAME
        self.service_type = SERVICE_TYPE

        from egse.digilent.measurpoint.dt8874.dt8874_protocol import Dt8874Protocol

        self.device_protocol = Dt8874Protocol(self, simulator=simulator)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service(SERVICE_TYPE)

    def get_communication_protocol(self) -> str:
        """Returns the communication protocol used by the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Communication protocol used by the Digilent MEASURpoint DT8874 Control Server, as specified in the settings.
        """

        return PROTOCOL

    def get_commanding_port(self) -> int:
        """Returns the commanding port used by the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Commanding port used by the Digilent MEASURpoint DT8874 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_cmd_sock) or COMMANDING_PORT

    def get_service_port(self) -> int:
        """Returns the service port used by the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Service port used by the Digilent MEASURpoint DT8874 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_service_sock) or SERVICE_PORT

    def get_monitoring_port(self) -> int:
        """Returns the monitoring port used by the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Monitoring port used by the Digilent MEASURpoint DT8874 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_mon_sock) or MONITORING_PORT

    def get_storage_mnemonic(self) -> str:
        """Returns the storage mnemonic used by the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Storage mnemonic used by the Digilent MEASURpoint DT8874 Control Server, as specified in the settings.
        """

        return ORIGIN

    def is_storage_manager_active(self):
        """Checks whether the Storage Manager is active."""

        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Sends housekeeping information of the Digilent MEASURpoint DT8874 to the Storage Manager."""

        origin = self.get_storage_mnemonic()
        store_housekeeping_information(origin, data)

    def register_to_storage_manager(self):
        """Registers the Control Server to the Storage Manager."""

        from egse.storage import register_to_storage_manager
        from egse.storage.persistence import TYPES

        register_to_storage_manager(
            origin=self.get_storage_mnemonic(),
            persistence_class=TYPES["CSV"],
            prep={
                "column_names": list(self.device_protocol.get_housekeeping().keys()),
                "mode": "a",
            },
        )

    def unregister_from_storage_manager(self):
        """Unregisters the Control Server from the Storage Manager."""

        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=self.get_storage_mnemonic())

    def before_serve(self):
        """Enables password-protected commands and applies the channel configuration.

        Quite a lot of commands (e.g. configuring the channels and requesting measurement results) are
        password-protected, so we need to enable those, before we can get going.

        In the setup, we specify (under `setup.gse.dt8874`), which channels should be configured and how.  It's also
        those channels for which we request measurement results to populate the housekeeping and metrics.
        """

        try:
            # Enable password-protected commands

            password = DEVICE_SETTINGS.PASSWORD
            self.device_protocol.dt8874.enable_pwd_protected_cmds(password=password)
        except AttributeError as ae:
            logger.warning(f"Couldn't enable password protected commands, check the log messages: {ae}.")

        if self.device_protocol.dt8874.is_pwd_protected_cmds_enabled():
            # Read the channel configuration from the setup + apply it to the device

            self.device_protocol.dt8874.config_channels()

        #     start_http_server(CTRL_SETTINGS.METRICS_PORT)

    def after_serve(self):
        self.deregister_service()

    def config_channels(self, event_data: dict):
        """Configures the channels of the Digilent MEASURpoint DT8874 after a new setup has been loaded.

        Args:
            event_data (dict): Event data, containing the setup ID.
        """

        if data := event_data.get("data"):
            if setup_id := data.get("setup_id"):
                setup = load_setup(int(setup_id))
                self.device_protocol.dt8874.config_channels(setup)

    def get_event_handlers(self) -> dict[str, Callable]:
        """Provides methods to handle the events the Control Server is subscribed to.

        Returns:
            Dictionary of event handlers.
        """

        return {"new_setup": self.config_channels}

    def get_event_subscriptions(self) -> list[str]:
        """Returns the list of events the Control Server is subscribed to.

        Returns:
            List of events the Control Server is subscribed to.
        """

        return ["new_setup"]


app = typer.Typer()


@app.command()
def start(
    simulator: Annotated[
        bool,
        typer.Option(
            "--simulator", "--sim", help="start the Digilent MEASURpoint DT8874 Control Server in simulator mode"
        ),
    ] = False,
):
    """Starts the Digilent MEASURpoint DT8874 Control Server."""

    # noinspection PyBroadException
    try:
        controller = Dt8874ControlServer(simulator)
        controller.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exc:
        exit_code = exc.code if hasattr(exc, "code") else 0
        print(f"System Exit with code {exc.code}")
        sys.exit(exit_code)
    except Exception:
        logger.exception("Cannot start the Digilent MEASURpoint DT8874 Control Server")

    return 0


@app.command()
def stop():
    """Sends a `quit_server` command to the Digilent MEASURpoint DT8874 Control Server."""

    with RegistryClient() as reg:
        service = reg.discover_service(SERVICE_TYPE)

        if service:
            proxy = ServiceProxy(protocol="tcp", hostname=service["host"], port=service["metadata"]["service_port"])
            proxy.quit_server()
        else:
            try:
                with Dt8874Proxy() as dt8874_proxy:
                    with dt8874_proxy.get_service_proxy() as sp:
                        sp.quit_server()
            except ConnectionError:
                rich.print("[red]Couldn't connect to 'dt8874_cs', process probably not running. ")


@app.command()
def status():
    """Requests the status information from the Digilent MEASURpoint DT8874 Control Server."""

    if COMMANDING_PORT != 0:
        endpoint = connect_address(PROTOCOL, HOSTNAME, COMMANDING_PORT)
        port = COMMANDING_PORT
        service_port = SERVICE_PORT
        monitoring_port = MONITORING_PORT

    else:
        with RegistryClient() as reg:
            service = reg.discover_service(SERVICE_TYPE)

            if service:
                protocol = service.get("protocol", "tcp")
                hostname = service["host"]
                port = service["port"]
                service_port = service["metadata"]["service_port"]
                monitoring_port = service["metadata"]["monitoring_port"]
                endpoint = connect_address(protocol, hostname, port)
            else:
                rich.print(
                    f"[red]The Digilent MEASURpoint DT8874 Control Server isn't registered as a service. The Control "
                    f"Server cannot be contacted without the required information from the service registry.[/]"
                )
                rich.print("Digilent MEASURpoint DT8874: [red]not active")
                return

    # noinspection PyUnboundLocalVariable
    if is_control_server_active(endpoint, timeout=2):
        rich.print(f"Digilent MEASURpoint DT8874: [green]active -> {endpoint}")

        with Dt8874Proxy() as dt8874:
            sim = dt8874.is_simulator()
            connected = dt8874.is_connected()
            ip = dt8874.get_ip_address()
            rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
            rich.print(f"hostname: {ip}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"commanding port: {port}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"service port: {service_port}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"monitoring port: {monitoring_port}")
    else:
        rich.print("Digilent MEASURpoint DT8874: [red]not active")


if __name__ == "__main__":
    import logging

    from egse.logger import set_all_logger_levels

    set_all_logger_levels(logging.DEBUG)

    sys.exit(app())
