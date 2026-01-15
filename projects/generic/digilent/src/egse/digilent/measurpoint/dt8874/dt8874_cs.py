"""Control Server for the Digilent MEASURpoint DT8874."""

import logging
import multiprocessing
from typing import Annotated

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
    STORAGE_MNEMONIC,
    PROTOCOL,
    HOSTNAME,
)
from egse.digilent.measurpoint.dt8874.dt8874 import Dt8874Proxy
from egse.digilent.measurpoint.dt8874.dt8874_protocol import Dt8874Protocol
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.storage import store_housekeeping_information
from egse.zmq_ser import connect_address, get_port_number

logger = logging.getLogger("egse.digilent.measurpoint.dt8874")


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

        return STORAGE_MNEMONIC

    def is_storage_manager_active(self):
        """Checks whether the Storage Manager is active."""
        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Sends housekeeping information of the Digilent MEASURpoint DT8874 to the Storage Manager."""

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
