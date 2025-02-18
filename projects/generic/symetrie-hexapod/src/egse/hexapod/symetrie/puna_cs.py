"""
The Control Server that connects to the Hexapod PUNA Hardware Controller.

Start the control server from the terminal as follows:

    $ puna_cs start-bg

or when you don't have the device available, start the control server in simulator mode. That
will make the control server connect to a device software simulator:

    $ puna_cs start --sim

Please note that software simulators are intended for simple test purposes and will not simulate
all device behavior correctly, e.g. timing, error conditions, etc.

"""
import logging
from typing import Annotated

import typer

from egse.hexapod.symetrie import ProxyFactory
from egse.hexapod.symetrie import get_hexapod_controller_pars

if __name__ != "__main__":
    import multiprocessing

    multiprocessing.current_process().name = "puna_cs"

import sys

import rich
import zmq

from egse.control import is_control_server_active
from egse.zmq_ser import connect_address

from prometheus_client import start_http_server

from egse.control import ControlServer
from egse.hexapod.symetrie.puna_protocol import PunaProtocol
from egse.settings import Settings

_LOGGER = logging.getLogger(__name__)

CTRL_SETTINGS = Settings.load("Hexapod PUNA Control Server")


class PunaControlServer(ControlServer):
    """
    PunaControlServer - Command and monitor the Hexapod PUNA hardware.

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

    def __init__(self, simulator: bool = False):
        super().__init__()

        self.device_protocol = PunaProtocol(self, simulator=simulator)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

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
            return "PUNA"

    def before_serve(self):
        start_http_server(CTRL_SETTINGS.METRICS_PORT)


app = typer.Typer()


@app.command()
def start(
        simulator: Annotated[
            bool,
            typer.Option("--simulator", "--sim", help="start the hexapod PUNA simulator in the background")
        ] = False
):
    """
    Start the Hexapod PUNA Control Server.

    Args:
        simulator: start the hexapod PUNA simulator in the background.
    """

    try:

        controller = PunaControlServer(simulator)
        controller.serve()

    except KeyboardInterrupt:

        print("Shutdown requested...exiting")

    except SystemExit as exit_code:

        print("System Exit with code {}.".format(exit_code))
        sys.exit(exit_code)

    except Exception:

        _LOGGER.exception("Cannot start the Hexapod Puna Control Server")

        # The above line does exactly the same as the traceback, but on the _LOGGER
        # import traceback
        # traceback.print_exc(file=sys.stdout)

    return 0


@app.command()
def stop():
    """Send a 'quit_server' command to the Hexapod Puna Control Server."""

    *_, device_id, device_name, controller_type = get_hexapod_controller_pars()

    factory = ProxyFactory()

    try:
        with factory.create(device_name, device_id=device_id) as proxy:
            sp = proxy.get_service_proxy()
            sp.quit_server()
    except ConnectionError:
        rich.print("[red]Couldn't connect to 'puna_cs', process probably not running. ")


@app.command()
def status():
    """Request status information from the Control Server."""

    protocol = CTRL_SETTINGS.PROTOCOL
    hostname_cs = CTRL_SETTINGS.HOSTNAME
    port_cs = CTRL_SETTINGS.COMMANDING_PORT

    endpoint = connect_address(protocol, hostname_cs, port_cs)

    *_, device_id, device_name, controller_type = get_hexapod_controller_pars()

    factory = ProxyFactory()

    if is_control_server_active(endpoint):
        rich.print("PUNA Hexapod: [green]active")
        with factory.create(device_name, device_id=device_id) as puna:
            sim = puna.is_simulator()
            connected = puna.is_connected()
            ip = puna.get_ip_address()
            rich.print(f"type: {controller_type}")
            rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
            rich.print(f"hostname: {ip}")
            rich.print(f"commanding port: {port_cs}")
    else:
        rich.print("PUNA Hexapod: [red]not active")


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

    sys.exit(app())
