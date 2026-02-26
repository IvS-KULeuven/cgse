"""Control Server for the Aim-TTi TGF4000."""

import logging
import multiprocessing
from typing import Annotated

import rich
import sys
import typer
import zmq

from egse.control import is_control_server_active, ControlServer
from egse.arbitrary_wave_generator.aim_tti import PROTOCOL, CS_SETTINGS
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.settings import Settings
from egse.storage import store_housekeeping_information
from egse.zmq_ser import connect_address, get_port_number

logger = logging.getLogger("egse.arbitrary_wave_generator.aim_tti.tgf4000")
DEVICE_SETTINGS = Settings.load("Aim-TTi TGF4000")


def is_tgf4000_cs_active(device_id: str, timeout: float = 0.5) -> bool:
    """Checks whether the Aim-TTi TGF4000 Control Server is running.

    Args:
        device_id (str): Device identifier, as per (local) settings and setup.
        timeout (float): Timeout when waiting for a reply [s].

    Returns:
        True if the Aim-TTi TGF4000 Control Server is running and replied with the expected answer; False otherwise.
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
            service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "tgf4000_cs")
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


class Tgf4000ControlServer(ControlServer):
    def __init__(self, device_id: str, simulator: bool = False):
        """Initialisation of a new Aim-TTi TGF4000 Control Server.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
            simulator (bool): Indicates whether to operate in simulator mode.
        """
        self.cs_settings = CS_SETTINGS[device_id]
        super().__init__()

        self.device_id = device_id
        process_name = CS_SETTINGS[device_id].get("PROCESS_NAME", "tgf4000_cs")
        service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "tgf4000_cs")

        multiprocessing.current_process().name = (
            process_name  # Name under which it is registered in the service registry
        )

        self.logger = logger
        self.service_name = process_name
        self.service_type = service_type

        from egse.arbitrary_wave_generator.aim_tti.tgf4000_protocol import Tgf4000Protocol

        self.device_protocol = Tgf4000Protocol(self, device_id, simulator=simulator)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service(service_type)

    def get_communication_protocol(self) -> str:
        """Returns the communication protocol used Aim-TTi TGF4000 Control Server.

        Returns:
            Communication protocol used by the Aim-TTi TGF4000 Control Server, as specified in the settings.
        """

        return PROTOCOL

    def get_commanding_port(self) -> int:
        """Returns the commanding port used by the Aim-TTi TGF4000 Control Server.

        Returns:
            Commanding port used by the Aim-TTi TGF4000 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_cmd_sock) or self.cs_settings.get("COMMANDING_PORT", 0)

    def get_service_port(self) -> int:
        """Returns the service port used by the Aim-TTi TGF4000 Control Server.

        Returns:
            Service port used by the Aim-TTi TGF4000 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_service_sock) or self.cs_settings.get("SERVICE_PORT", 0)

    def get_monitoring_port(self) -> int:
        """Returns the monitoring port used by the Aim-TTi TGF4000 Control Server.

        Returns:
            Monitoring port used by the Aim-TTi TGF4000 Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_mon_sock) or self.cs_settings.get("MONITORING_PORT", 0)

    def get_storage_mnemonic(self) -> str:
        """Returns the storage mnemonic used by the Aim-TTi TGF4000 Control Server.

        Returns:
            Storage mnemonic used by the Aim-TTi TGF4000 Control Server, as specified in the settings.
        """

        return self.cs_settings.get("STORAGE_MNEMONIC", "TGF4000")

    def is_storage_manager_active(self):
        """Checks whether the Storage Manager is active."""

        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Sends housekeeping information of the Aim-TTi TGF4000 to the Storage Manager."""

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
        typer.Option("--simulator", "--sim", help="start the Aim-TTi TGF4000 Control Server in simulator mode"),
    ] = False,
) -> int:
    """Starts the Aim-TTi TGF4000 Control Server with the given identifier."""

    # noinspection PyBroadException
    try:
        controller = Tgf4000ControlServer(device_id, simulator)
        controller.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exc:
        exit_code = exc.code if hasattr(exc, "code") else 0
        print(f"System Exit with code {exc.code}")
        sys.exit(exit_code)
    except Exception:
        logger.exception(f"Cannot start the Aim-TTi TGF4000 {device_id} Control Server")

    return 0


@app.command()
def stop(
    device_id: Annotated[
        str, typer.Argument(help="Identifies the hardware controller (as per local settings and setup)")
    ],
) -> None:
    """Sends a `quit_server` command to the Aim-TTi TGF4000 Control Server."""

    service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "tgf4000_cs")

    with RegistryClient() as reg:
        service = reg.discover_service(service_type)

        if service:
            proxy = ServiceProxy(protocol="tcp", hostname=service["host"], port=service["metadata"]["service_port"])
            proxy.quit_server()
        else:
            try:
                with Tgf4000Proxy(device_id) as tgf4000_proxy:
                    with tgf4000_proxy.get_service_proxy() as sp:
                        sp.quit_server()
            except ConnectionError:
                rich.print(f"[red]Couldn't connect to 'tgf4000_cs' {device_id}, process probably not running. ")


@app.command()
def status(
    device_id: Annotated[
        str, typer.Argument(help="Identifies the hardware controller (as per local settings and setup)")
    ],
) -> None:
    """Requests the status information from the Aim-TTi TGF4000 Control Server."""

    hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")
    commanding_port = CS_SETTINGS[device_id].get("COMMANDING_PORT", 0)
    service_port = CS_SETTINGS[device_id].get("SERVICE_PORT", 0)
    monitoring_port = CS_SETTINGS[device_id].get("MONITORING_PORT", 0)
    service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "tgf4000_cs")

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
                    f"[red]The Aim-TTi TGF4000 Control Server {device_id} isn't registered as a service. The Control "
                    f"Server cannot be contacted without the required information from the service registry.[/]"
                )
                rich.print(f"Aim-TTi TGF4000 {device_id}: [red]not active")
                return

    # noinspection PyUnboundLocalVariable
    if is_control_server_active(endpoint, timeout=2):
        rich.print(f"Aim-TTi TGF4000 {device_id}: [green]active -> {endpoint}")

        with Tgf4000Proxy(device_id) as tgf4000:
            sim = tgf4000.is_simulator()
            connected = tgf4000.is_connected()
            ip = tgf4000.get_ip_address()
            rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
            rich.print(f"hostname: {ip}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"commanding port: {port}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"service port: {service_port}")
            # noinspection PyUnboundLocalVariable
            rich.print(f"monitoring port: {monitoring_port}")
    else:
        rich.print(f"Aim-TTi TGF4000 {device_id}: [red]not active")


if __name__ == "__main__":
    import logging

    from egse.logger import set_all_logger_levels

    set_all_logger_levels(logging.DEBUG)

    sys.exit(app())
