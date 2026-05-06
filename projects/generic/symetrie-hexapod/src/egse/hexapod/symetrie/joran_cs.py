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
import multiprocessing
import sys
from typing import Annotated

import click
import rich
import typer
import zmq
from egse.connect import get_endpoint
from egse.connect import get_metadata_port
from egse.control import ControlServer, is_control_server_active
from egse.process import SubProcess
from egse.services import ServiceProxy
from egse.settings import Settings
from prometheus_client import start_http_server

from egse.hexapod.symetrie.joran import JoranProxy
from egse.hexapod.symetrie.joran_protocol import JoranProtocol

logger = logging.getLogger(__name__)

CTRL_SETTINGS = Settings.load("Hexapod Control Server")["JORAN"]

PROTOCOL = CTRL_SETTINGS.get("PROTOCOL", "tcp")
HOSTNAME = CTRL_SETTINGS.get("HOSTNAME", "localhost")
COMMANDING_PORT = CTRL_SETTINGS.get("COMMANDING_PORT", 0)
SERVICE_PORT = CTRL_SETTINGS.get("SERVICE_PORT", 0)
MONITORING_PORT = CTRL_SETTINGS.get("MONITORING_PORT", 0)


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

    def __init__(self, device_id: str, simulator: bool = False):
        super().__init__()

        multiprocessing.current_process().name = "joran_cs"

        self.device_protocol = JoranProtocol(self, device_id=device_id, simulator=simulator)

        self.logger.debug(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.service_name = "joran_cs"
        self.service_type = device_id
        self.register_service(service_type=self.service_type)

    def get_communication_protocol(self):
        return PROTOCOL

    def get_commanding_port(self):
        return COMMANDING_PORT

    def get_service_port(self):
        return SERVICE_PORT

    def get_monitoring_port(self):
        return MONITORING_PORT

    def can_operate_without_registry(self) -> bool:
        return bool(COMMANDING_PORT and SERVICE_PORT and MONITORING_PORT)

    def get_storage_mnemonic(self):
        return CTRL_SETTINGS.get("STORAGE_MNEMONIC", "JORAN")

    def before_serve(self):
        start_http_server(CTRL_SETTINGS["METRICS_PORT"])


app = typer.Typer()


@app.command()
def start(
    device_id: Annotated[str, typer.Argument(help="the device identifier, identifies the hardware controller")],
    simulator: Annotated[
        bool, typer.Option("--simulator", "--sim", help="start the hexapod JORAN Control Server in simulator mode")
    ] = False,
):
    """Start the Hexapod JORAN Control Server."""

    try:
        controller = JoranControlServer(device_id=device_id, simulator=simulator)
        controller.serve()

    except KeyboardInterrupt:
        print("Shutdown requested...exiting")

    except SystemExit as exc:
        exit_code = exc.code if hasattr(exc, "code") else 0
        print("System Exit with code {}.".format(exit_code))
        sys.exit(exit_code)

    except Exception:
        logger.exception("Cannot start the Hexapod JORAN Control Server")

        # The above line does exactly the same as the traceback, but on the logger
        # import traceback
        # traceback.print_exc(file=sys.stdout)

    return 0


@app.command()
def stop(device_id: str):
    """Send a 'quit_server' command to the Hexapod Joran Control Server."""

    try:
        _, hostname, service_port = get_metadata_port(
            service_type=device_id,
            metadata_key="service_port",
            static_port=SERVICE_PORT,
            protocol=PROTOCOL,
            hostname=HOSTNAME,
        )
    except RuntimeError as exc:
        rich.print(f"[red]{exc}")
        return

    proxy = ServiceProxy(protocol=PROTOCOL, hostname=hostname, port=service_port)
    try:
        proxy.quit_server()
    except ConnectionError:
        rich.print("[red]Couldn't connect to 'joran_cs', process probably not running.")


@app.command()
def status(device_id: str):
    """Request status information from the Control Server."""

    try:
        endpoint = get_endpoint(service_type=device_id, protocol=PROTOCOL, hostname=HOSTNAME, port=COMMANDING_PORT)
        commanding_port = int(endpoint.rsplit(":", maxsplit=1)[-1])

        _, hostname, service_port = get_metadata_port(
            service_type=device_id,
            metadata_key="service_port",
            static_port=SERVICE_PORT,
            protocol=PROTOCOL,
            hostname=HOSTNAME,
        )
        _, _, monitoring_port = get_metadata_port(
            service_type=device_id,
            metadata_key="monitoring_port",
            static_port=MONITORING_PORT,
            protocol=PROTOCOL,
            hostname=HOSTNAME,
        )
    except RuntimeError:
        rich.print(
            f"[red]The JORAN CS '{device_id}' isn't registered as a service. I cannot contact the control "
            f"server without the required info from the service registry.[/]"
        )
        rich.print("JORAN Hexapod: [red]not active")
        return

    if is_control_server_active(endpoint):
        rich.print("JORAN Hexapod: [green]active")
        with JoranProxy(device_id) as joran:
            sim = joran.is_simulator()
            connected = joran.is_connected()
            ip = joran.get_ip_address()
            rich.print(f"type: ALPHA+")
            rich.print(f"mode: {'simulator' if sim else 'device'}{'' if connected else ' not'} connected")
            rich.print(f"hostname: {ip}")
            rich.print(f"commanding port: {commanding_port}")
            rich.print(f"service port: {service_port}")
            rich.print(f"monitoring port: {monitoring_port}")
    else:
        rich.print("JORAN Hexapod: [red]not active")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

    sys.exit(app())
