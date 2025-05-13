"""
The Control Server that connects to the Hexapod ZONDA Hardware Controller.

Start the control server from the terminal as follows:

    $ zonda_cs start-bg

or when you don't have the device available, start the control server in simulator mode. That
will make the control server connect to a device software simulator:

    $ zonda_cs start --sim

Please note that software simulators are intended for simple test purposes and will not simulate
all device behavior correctly, e.g. timing, error conditions, etc.

"""
import multiprocessing
import sys
from typing import Annotated

import rich
import typer
import zmq
from prometheus_client import start_http_server

from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.hexapod.symetrie import ProxyFactory
from egse.hexapod.symetrie import get_hexapod_controller_pars
from egse.hexapod.symetrie import logger
from egse.hexapod.symetrie.zonda_protocol import ZondaProtocol
from egse.settings import Settings
from egse.storage import store_housekeeping_information
from egse.zmq_ser import connect_address

CTRL_SETTINGS = Settings.load("Hexapod ZONDA Control Server")


class ZondaControlServer(ControlServer):
    """ZondaControlServer - Command and monitor the Hexapod ZONDA hardware.

    This class works as a command and monitoring server to control the Symétrie Hexapod PUNA.
    This control server shall be used as the single point access for controlling the hardware
    device. Monitoring access should be done preferably through this control server also,
    but can be done with a direct connection through the PunaController if needed.

    The sever binds to the following ZeroMQ sockets:

    * a REQ-REP socket that can be used as a command server. Any client can connect and
      send a command to the Hexapod.

    * a PUB-SUP socket that serves as a monitoring server. It will send out Hexapod status
      information to all the connected clients every five seconds.

    """

    def __init__(self, device_id: str, simulator: bool = False):
        super().__init__()

        self.logger = logger

        self.device_id = device_id
        self.device_protocol = ZondaProtocol(self, device_id=device_id, simulator=simulator)

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

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
            return "ZONDA"

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
        multiprocessing.current_process().name = "zonda_cs"

        start_http_server(CTRL_SETTINGS.METRICS_PORT)


app = typer.Typer()


@app.command()
def start(
        device_id: Annotated[
            str,
            typer.Argument(help="the device identifier, identifies the hardware controller")
        ],
        simulator: Annotated[
            bool,
            typer.Option("--simulator", "--sim", help="start the hexapod PUNA Control Server in simulator mode")
        ] = False
):
    """Start the Hexapod Zonda Control Server."""

    try:

        controller = ZondaControlServer(device_id, simulator)
        controller.serve()

    except KeyboardInterrupt:

        print("Shutdown requested...exiting")

    except SystemExit as exc:

        exit_code = exc.code if hasattr(exc, 'code') else 0
        print(f"System Exit with code {exc.code}")
        sys.exit(exit_code)

    except Exception:

        logger.exception("Cannot start the Hexapod Zonda Control Server")

        # The above line does exactly the same as the traceback, but on the logger
        # import traceback
        # traceback.print_exc(file=sys.stdout)

    return 0


@app.command()
def stop(device_id: str):
    """Send a 'quit_server' command to the Hexapod Zonda Control Server."""

    *_, device_type, controller_type = get_hexapod_controller_pars(device_id)

    factory = ProxyFactory()

    try:
        with factory.create(device_type, device_id=device_id) as proxy:
            sp = proxy.get_service_proxy()
            sp.quit_server()
    except ConnectionError:
        rich.print("[red]Couldn't connect to 'zonda_cs', process probably not running. ")


@app.command()
def status(device_id: str):
    """Request status information from the Control Server."""

    protocol = CTRL_SETTINGS.PROTOCOL
    hostname = CTRL_SETTINGS.HOSTNAME
    port = CTRL_SETTINGS.COMMANDING_PORT

    endpoint = connect_address(protocol, hostname, port)

    if is_control_server_active(endpoint):
        status = "[green]active"
    else:
        status = "[red]not active"

    rich.print(f"ZONDA Hexapod: {status}")


if __name__ == "__main__":

    import logging

    from egse.logger import set_all_logger_levels
    set_all_logger_levels(logging.DEBUG)

    sys.exit(app())
