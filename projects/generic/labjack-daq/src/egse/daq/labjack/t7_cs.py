"""Control Server for the LabJack T7."""

import logging
import multiprocessing
from typing import Annotated

import rich
import sys
import typer
import zmq

from egse.daq.labjack import PROTOCOL, CS_SETTINGS
from egse.control import is_control_server_active, ControlServer
from egse.daq.labjack.t7 import T7Proxy
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.settings import Settings
from egse.storage import store_housekeeping_information
from egse.zmq_ser import connect_address, get_port_number

logger = logging.getLogger("egse.daq.labjack.t7")
DEVICE_SETTINGS = Settings.load("LabJack T7")


def is_t7_cs_active(device_id: str, timeout: float = 0.5) -> bool:
    """Checks whether the LabJack T7 Control Server is running.

    Args:
        device_id (str): Device identifier, as per (local) settings and setup.
        timeout (float): Timeout when waiting for a reply [s].

    Returns:
        True if the LabJack T7 Control Server is running and replied with the expected answer; False otherwise.
    """

    commanding_port = CS_SETTINGS[device_id].get(
        "COMMANDING_PORT", 0
    )  # Commanding port (as per settings or dynamically assigned)
    hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")  # Hostname

    if commanding_port != 0:
        protocol = PROTOCOL
        port = commanding_port

    else:
        with RegistryClient() as reg:
            service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "t7_cs")
            service = reg.discover_service(service_type)

            if service:
                protocol = service.get("protocol", "tcp")
                hostname = service["host"]
                port = service["port"]

            else:
                return False

    # noinspection PyUnboundLocalVariable
    endpoint = connect_address(protocol, hostname, port)

    return is_control_server_active(endpoint, timeout)


class T7ControlServer(ControlServer):
    def __init__(self, device_id: str, simulator: bool = False):
        """Initialisation of a new LabJack T7 Control Server.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
            simulator (bool): Indicates whether to operate in simulator mode.
        """
        self.cs_settings = CS_SETTINGS[device_id]
        super().__init__()

        self.device_id = device_id
        process_name = CS_SETTINGS[device_id].get("PROCESS_NAME", "t7_cs")
        service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "t7_cs")

        multiprocessing.current_process().name = (
            process_name  # Name under which it is registered in the service registry
        )

        self.logger = logger
        self.service_name = process_name
        self.service_type = service_type

        from egse.daq.labjack.t7_protocol import T7Protocol

        self.device_protocol = T7Protocol(self, device_id, simulator=simulator)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service(service_type)

    def get_communication_protocol(self) -> str:
        """Returns the communication protocol used LabJack T7 Control Server.

        Returns:
            Communication protocol used by the LabJack T7 Control Server, as specified in the settings.
        """

        return PROTOCOL

    def get_commanding_port(self) -> int:
        """Returns the commanding port used by the LabJack T7 Control Server.

        Returns:
            Commanding port used by the LabJack T7 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_cmd_sock) or self.cs_settings.get("COMMANDING_PORT", 0)

    def get_service_port(self) -> int:
        """Returns the service port used by the LabJack T7 Control Server.

        Returns:
            Service port used by the LabJack T7 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_service_sock) or self.cs_settings.get("SERVICE_PORT", 0)

    def get_monitoring_port(self) -> int:
        """Returns the monitoring port used by the LabJack T7 Control Server.

        Returns:
            Monitoring port used by the LabJack T7 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_mon_sock) or self.cs_settings.get("MONITORING_PORT", 0)

    def get_storage_mnemonic(self) -> str:
        """Returns the storage mnemonic used by the LabJack T7 Control Server.

        Returns:
            Storage mnemonic used by the LabJack T7 Control Server, as specified in the settings.
        """

        return self.cs_settings.get("STORAGE_MNEMONIC", "T7")

    def is_storage_manager_active(self):
        """Checks whether the Storage Manager is active."""

        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Sends housekeeping information of the LabJack T7 to the Storage Manager."""

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

    def after_serve(self):
        self.deregister_service()


app = typer.Typer()


@app.command()
def start(
    device_id: Annotated[
        str, typer.Argument(help="Identifies the hardware controller (as per local settings and setup)")
    ],
    simulator: Annotated[
        bool,
        typer.Option("--simulator", "--sim", help="start the LabJack T7 Control Server in simulator mode"),
    ] = False,
) -> int:
    """Starts the LabJack T7 Control Server with the given identifier."""

    # noinspection PyBroadException
    try:
        controller = T7ControlServer(device_id, simulator)
        controller.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exc:
        exit_code = exc.code if hasattr(exc, "code") else 0
        print(f"System Exit with code {exc.code}")
        sys.exit(exit_code)
    except Exception:
        logger.exception(f"Cannot start the LabJack T7 {device_id} Control Server")

    return 0


@app.command()
def stop(
    device_id: Annotated[
        str, typer.Argument(help="Identifies the hardware controller (as per local settings and setup)")
    ],
) -> None:
    """Sends a `quit_server` command to the LabJack T7 Control Server."""

    service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "t7_cs")

    with RegistryClient() as reg:
        service = reg.discover_service(service_type)

        if service:
            proxy = ServiceProxy(protocol="tcp", hostname=service["host"], port=service["metadata"]["service_port"])
            proxy.quit_server()
        else:
            try:
                with T7Proxy(device_id) as t7_proxy:
                    with t7_proxy.get_service_proxy() as sp:
                        sp.quit_server()
            except ConnectionError:
                rich.print(f"[red]Couldn't connect to 't7_cs' {device_id}, process probably not running. ")


@app.command()
def status(
    device_id: Annotated[
        str, typer.Argument(help="Identifies the hardware controller (as per local settings and setup)")
    ],
) -> None:
    """Requests the status information from the LabJack T7 Control Server."""

    hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")
    commanding_port = CS_SETTINGS[device_id].get("COMMANDING_PORT", 0)
    service_port = CS_SETTINGS[device_id].get("SERVICE_PORT", 0)
    monitoring_port = CS_SETTINGS[device_id].get("MONITORING_PORT", 0)
    service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "t7_cs")

    if commanding_port != 0:
        endpoint = connect_address(PROTOCOL, hostname, commanding_port)
        port = commanding_port
        service_port = service_port
        monitoring_port = monitoring_port

    else:
        with RegistryClient() as reg:
            service = reg.discover_service(service_type)

            if service:
                protocol = service.get("protocol", "tcp")
                hostname = service["host"]
                port = service["port"]
                service_port = service["metadata"]["service_port"]
                monitoring_port = service["metadata"]["monitoring_port"]
                endpoint = connect_address(protocol, hostname, port)
            else:
                rich.print(
                    f"[red]The LabJack T7 Control Server {device_id} isn't registered as a service. The Control "
                    f"Server cannot be contacted without the required information from the service registry.[/]"
                )
                rich.print(f"LabJack T7 {device_id}: [red]not active")
                return

    # noinspection PyUnboundLocalVariable
    if is_control_server_active(endpoint, timeout=2):
        rich.print(f"LabJack T7 {device_id}: [green]active -> {endpoint}")

        with T7Proxy(device_id) as t7:
            sim = t7.is_simulator()
            connected = t7.is_connected()
            ip = t7.get_ip_address()
            rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
            rich.print(f"hostname: {ip}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"commanding port: {port}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"service port: {service_port}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"monitoring port: {monitoring_port}")
    else:
        rich.print(f"LabJack T7 {device_id}: [red]not active")


if __name__ == "__main__":
    import logging

    from egse.logger import set_all_logger_levels

    set_all_logger_levels(logging.DEBUG)

    sys.exit(app())
