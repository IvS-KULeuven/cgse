"""
The Control Server that connects to the Hexapod JORAN Hardware Controller.

Start the control server from the terminal as follows:

    $ joran_cs start-bg

or when you don't have the device available, start the control server in simulator mode. That
will make the control server connect to a device software simulator:

    $ joran_cs start --sim

Please note that software simulators are intended for simple test purposes and will not simulate
all device behavior correctly, e.g. timing, error conditions, etc.

"""
import logging

from egse.process import SubProcess

if __name__ != "__main__":
    import multiprocessing
    multiprocessing.current_process().name = "joran_cs"

import sys

import click
import rich
import zmq

from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.hexapod.symetrie.joran import JoranProxy
from egse.hexapod.symetrie.joran_protocol import JoranProtocol
from egse.settings import Settings
from egse.zmq_ser import connect_address
from prometheus_client import start_http_server

logger = logging.getLogger(__name__)

CTRL_SETTINGS = Settings.load("Hexapod JORAN Control Server")


class JoranControlServer(ControlServer):
    """JoranControlServer - Command and monitor the Hexapod JORAN hardware.

    This class works as a command and monitoring server to control the Symétrie Hexapod JORAN.
    This control server shall be used as the single point access for controlling the hardware
    device. Monitoring access should be done preferably through this control server also,
    but can be done with a direct connection through the PunaController if needed.

    The sever binds to the following ZeroMQ sockets:

    * a REQ-REP socket that can be used as a command server. Any client can connect and
      send a command to the Hexapod.

    * a PUB-SUP socket that serves as a monitoring server. It will send out Hexapod status
      information to all the connected clients every five seconds.

    """

    def __init__(self):
        super().__init__()

        self.device_protocol = JoranProtocol(self)

        self.logger.debug(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

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
            return "JORAN"

    def before_serve(self):
        start_http_server(CTRL_SETTINGS.METRICS_PORT)


@click.group()
def cli():
    pass


@cli.command()
@click.option("--simulator", "--sim", is_flag=True, help="Start the Hexapod Joran Simulator as the backend.")
def start(simulator):
    """Start the Hexapod Joran Control Server."""

    if simulator:

        Settings.set_simulation_mode(True)

    try:

        controller = JoranControlServer()
        controller.serve()

    except KeyboardInterrupt:

        print("Shutdown requested...exiting")

    except SystemExit as exit_code:

        print("System Exit with code {}.".format(exit_code))
        sys.exit(exit_code)

    except Exception:

        logger.exception("Cannot start the Hexapod Joran Control Server")

        # The above line does exactly the same as the traceback, but on the logger
        # import traceback
        # traceback.print_exc(file=sys.stdout)

    return 0


@cli.command()
@click.option("--simulator", "--sim", is_flag=True,
              help="Start the Hexapod Joran Simulator as the backend.")
def start_bg(simulator):
    """Start the JORAN Control Server in the background."""
    sim = "--simulator" if simulator else ""
    proc = SubProcess("joran_cs", ["joran_cs", "start", sim])
    proc.execute()


@cli.command()
def stop():
    """Send a 'quit_server' command to the Hexapod Joran Control Server."""

    try:
        with JoranProxy() as proxy:
            sp = proxy.get_service_proxy()
            sp.quit_server()
    except ConnectionError:
        rich.print("[red]Couldn't connect to 'joran_cs', process probably not running. ")


@cli.command()
def status():
    """Request status information from the Control Server."""

    protocol = CTRL_SETTINGS.PROTOCOL
    hostname = CTRL_SETTINGS.HOSTNAME
    port = CTRL_SETTINGS.COMMANDING_PORT

    endpoint = connect_address(protocol, hostname, port)

    if is_control_server_active(endpoint):
        rich.print("JORAN Hexapod: [green]active")
        with JoranProxy() as joran:
            sim = joran.is_simulator()
            connected = joran.is_connected()
            ip = joran.get_ip_address()
            rich.print(f"type: ALPHA+")
            rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
            rich.print(f"hostname: {ip}")
            rich.print(f"commanding port: {port}")
    else:
        rich.print("JORAN Hexapod: [red]not active")


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

    sys.exit(cli())
