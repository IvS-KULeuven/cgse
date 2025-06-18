import logging
import multiprocessing
from typing import Annotated, Optional

import rich
import sys
import typer
import zmq

from egse.control import is_control_server_active, ControlServer
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.settings import Settings
from egse.storage import store_housekeeping_information
from egse.tempcontrol.lakeshore.lakeshore336 import LakeShore336Proxy
from egse.tempcontrol.lakeshore.lakeshore336_protocol import LakeShore336Protocol
from egse.zmq_ser import connect_address, get_port_number

multiprocessing.current_process().name = "lakeshore336_cs"
CTRL_SETTINGS = Settings.load("LakeShore336 Control Server")

logger = logging.getLogger(__name__)


def is_lakeshore336_cs_active(device_id: str, timeout: float = 0.5) -> bool:
    """Checks if the LakeShore336 Control Server with the given device ID is active.

    Args
        device_id (str): Device identifier

    Returns: True if the LakeShore336 Control Server with the given device ID is active; False otherwise.
    """

    protocol = CTRL_SETTINGS.PROTOCOL
    hostname = CTRL_SETTINGS.HOSTNAME
    port = CTRL_SETTINGS[device_id]["COMMANDING_PORT"]

    endpoint = connect_address(protocol, hostname, port)

    return is_control_server_active(endpoint, timeout)


class LakeShore336ControlServer(ControlServer):
    def __init__(self, device_id: str, simulator: bool = False):
        """Initialisation of a LakeShore336 Control Server.

        Args:
            device_id (str): Device identifier
            simulator (bool): Indicates whether the LakeShore336 Control Server should be started in simulator mode
        """

        super().__init__(device_id=device_id)

        self.device_protocol = LakeShore336Protocol(self, device_id, simulator=simulator)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service(service_type=f"{device_id}")

    def get_communication_protocol(self) -> str:
        """Returns the communication protocol used by the Control Server.

        Returns Communication protocol used by the Control Server, as specified in the settings.
        """

        return "tcp"

    def get_commanding_port(self):
        """Returns the commanding port used by the Control Server.

        Returns: Commanding port used by the Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_cmd_sock) or 0

    def get_service_port(self):
        """Returns the service port used by the Control Server.

        Returns: Service port used by the Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_service_sock) or 0

    def get_monitoring_port(self) -> int:
        """Returns the monitoring port used by the Control Server.

        Returns: Monitoring port used by the Control Server, as specified in the settings.
        """

        return get_port_number(self.dev_ctrl_mon_sock) or 0

    def get_storage_mnemonic(self) -> str:
        """Returns the storage mnemonic used by the Control Server.

        This is a string that will appear in the filename with the housekeeping information of the device, as a way of
        identifying the device.  If this is not included in the settings, the device identifier is used.


        Returns: Storage mnemonic used by the Control Server, as specified in the settings.  If not specified in the
                 settings, the device identifier will be used.
        """

        try:
            return CTRL_SETTINGS[self.device_id]["STORAGE_MNEMONIC"]
        except AttributeError:
            return self.device_id

    def is_storage_manager_active(self):
        """Checks whether the Storage Manager is active.

        Returns: True if the Storage Manager is active; False otherwise.
        """

        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        """Stores the given housekeeping information in a dedicated file.

        Args:
            data (dict): Dictionary containing parameter name and value of all device housekeeping.
        """

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

    def after_serve(self) -> None:
        self.deregister_service()

    def unregister_from_storage_manager(self):
        """Unregisters the Control Server from the Storage Manager."""

        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=self.get_storage_mnemonic())


app = typer.Typer()


@app.command()
def start(
    device_id: Annotated[str, typer.Argument(help="Device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="Start the LakeShore336 Control Server in simulator mode")
    ] = False,
):
    """Start the LakeShore336 Control Server for the given device ID.

    Args:
        device_id (str): Device identifier
        simulator (bool): Indicates whether the LakeShore336 Control Server should be started in simulator mode
    """

    try:
        controller = LakeShore336ControlServer(device_id, simulator)
        controller.serve()

    except KeyboardInterrupt:
        print("Shutdown requested...exiting")

    except SystemExit as exit_code:
        print("System Exit with code {}.".format(exit_code))
        sys.exit(exit_code.code)

    except Exception:
        logger.exception(f"Cannot start the LakeShore336 Control Server {device_id}")

    return 0


@app.command()
def stop(device_id: str):
    """Stops the LakeShore336 Control Server for the given device ID.

    Args:
        device_id (str): Device identifier
    """

    with RegistryClient() as reg:
        service = reg.discover_service(device_id)
        rich.print("service = ", service)

        if service:
            proxy = ServiceProxy(protocol="tcp", hostname=service["host"], port=service["metadata"]["service_port"])
            proxy.quit_server()


@app.command()
def status(device_id: str):
    """Returns the status of the LakeShore336 Control Server for the given device ID.

    Args:
        device_id (str): Device identifier
    """

    with RegistryClient() as reg:
        service = reg.discover_service(device_id)

        if service:
            protocol = service.get("protocol", "tcp")
            hostname = service["host"]
            port = service["port"]
            service_port = service["metadata"]["service_port"]
            monitoring_port = service["metadata"]["monitoring_port"]
            endpoint = connect_address(protocol, hostname, port)

            if is_control_server_active(endpoint):
                rich.print(f"{device_id} CS: [green]active")
                with LakeShore336Proxy(device_id) as proxy:
                    sim = proxy.is_simulator()
                    connected = proxy.is_connected()
                    ip = proxy.get_ip_address()
                    rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
                    rich.print(f"hostname: {ip}")
                    rich.print(f"commanding port: {port}")
                    rich.print(f"service port: {service_port}")
                    rich.print(f"monitoring port: {monitoring_port}")
            else:
                rich.print(f"LakeShore336 {device_id} CS: [red]inactive")
        else:
            rich.print(
                f"[red]The LakeShore336 CS '{device_id}' isn't registered as a service. I cannot contact the control "
                f"server without the required info from the service registry.[/]"
            )
            rich.print(f"LakeShore336 {device_id}: [red]inactive")
