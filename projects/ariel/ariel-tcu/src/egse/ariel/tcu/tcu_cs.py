import logging
import sys
from typing import Annotated

import zmq
import typer
import rich

from egse.control import is_control_server_active, ControlServer
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.settings import Settings
from egse.storage import store_housekeeping_information
from egse.zmq_ser import connect_address
from egse.ariel.tcu.tcu_protocol import TcuProtocol
from egse.ariel.tcu.tcu import TcuProxy

logger = logging.getLogger(__name__)

CTRL_SETTINGS = Settings.load("Ariel TCU Control Server")


def is_tcu_cs_active(timeout: float = 0.5) -> bool:
    """Checks whether the Ariel TCU Control Server is running.

    Args:
        timeout (float): Timeout when waiting for a reply [s].

    Returns:
        True if the Ariel TCU Control Server is running and replied with the expected answer; False otherwise.
    """

    endpoint = connect_address(CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.HOSTNAME, CTRL_SETTINGS.COMMANDING_PORT)

    return is_control_server_active(endpoint, timeout)


class TcuControlServer(ControlServer):
    def __init__(self, simulator: bool = False):
        super().__init__()

        self.device_protocol = TcuProtocol(self, simulator=simulator)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service("tcu_control_server")

    def get_communication_protocol(self) -> str:
        """Returns the communication protocol used by the Ariel TCU Control Server.

        Returns:
            Communication protocol used by the Ariel TCU Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.PROTOCOL

    def get_commanding_port(self) -> int:
        """Returns the commanding port used by the Ariel TCU Control Server.

        Returns:
            Commanding port used by the Ariel TCU Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.COMMANDING_PORT

    def get_service_port(self) -> int:
        """Returns the service port used by the Ariel TCU Control Server.

        Returns:
            Service port used by the Ariel TCU Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.SERVICE_PORT

    def get_monitoring_port(self) -> int:
        """Returns the monitoring port used by the Ariel TCU Control Server.

        Returns:
            Monitoring port used by the Ariel TCU Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.MONITORING_PORT

    def get_storage_mnemonic(self) -> str:
        """Returns the storage mnemonic used by the Ariel TCU Control Server.

        Returns:
            Storage mnemonic used by the Ariel TCU Control Server, as specified in the settings.
        """

        try:
            return CTRL_SETTINGS.STORAGE_MNEMONIC
        except AttributeError:
            return "TCU"

    def is_storage_manager_active(self):
        """ Checks whether the Storage Manager is active."""
        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Sends housekeeping information of the Ariel TCU to the Storage Manager."""

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
            },
        )

    def unregister_from_storage_manager(self):
        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=self.get_storage_mnemonic())

    # def before_serve(self):
    #     start_http_server(CTRL_SETTINGS.METRICS_PORT)

    def after_serve(self):
        self.deregister_service()


app = typer.Typer()


@app.command()
def start(
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="start the Ariel TCU Control Server in simulator mode")
    ] = False,
):
    """Starts the Ariel TCU Control Server."""

    try:
        controller = TcuControlServer(simulator)
        controller.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exc:
        exit_code = exc.code if hasattr(exc, "code") else 0
        print(f"System Exit with code {exc.code}")
        sys.exit(exit_code)
    except Exception:
        logger.exception("Cannot start the Ariel TCU Control Server")
        # The above line does exactly the same as the traceback, but on the logger
        # import traceback
        # traceback.print_exc(file=sys.stdout)

    return 0


@app.command()
def stop():
    """Sends a `quit_server` command to the Ariel TCU Control Server."""

    with RegistryClient() as reg:
        service = reg.discover_service("tcu_control_server")
        rich.print("service = ", service)

        if service:
            proxy = ServiceProxy(protocol="tcp", hostname=service["host"], port=service["metadata"]["service_port"])
            proxy.quit_server()
        else:
            # *_, device_type, controller_type = get_hexapod_controller_pars(device_id)

            try:
                with TcuProxy() as tcu_proxy:
                    with tcu_proxy.get_service_proxy() as sp:
                        sp.quit_server()
            except ConnectionError:
                rich.print("[red]Couldn't connect to 'tcu_cs', process probably not running. ")


@app.command()
def status():
    """Requests the status information from the Ariel TCU Control Server."""

    with RegistryClient() as reg:
        service = reg.discover_service("tcu_control_server")

        if service:
            protocol = service.get("protocol", "tcp")
            hostname = service["host"]
            port = service["port"]
            service_port = service["metadata"]["service_port"]
            monitoring_port = service["metadata"]["monitoring_port"]
            endpoint = connect_address(protocol, hostname, port)
        else:
            rich.print(
                f"[red]The Ariel TCU Control Server isn't registered as a service. The Control Server cannot be "
                f"contacted without the required information from the service registry.[/]"
            )
            rich.print("Ariel TCU: [red]not active")
            return

    if is_control_server_active(endpoint):
        rich.print("Ariel TCU: [green]active")

        with TcuProxy() as tcu:
            sim = tcu.is_simulator()
            connected = tcu.is_connected()
            ip = tcu.get_ip_address()
            rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
            rich.print(f"hostname: {ip}")
            rich.print(f"commanding port: {port}")
            rich.print(f"service port: {service_port}")
            rich.print(f"monitoring port: {monitoring_port}")
    else:
        rich.print("Ariel TCU: [red]not active")

if __name__ == "__main__":
    import logging

    from egse.logger import set_all_logger_levels

    set_all_logger_levels(logging.DEBUG)

    sys.exit(app())
