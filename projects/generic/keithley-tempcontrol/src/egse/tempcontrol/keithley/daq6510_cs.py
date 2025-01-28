import logging

from prometheus_client import start_http_server

import multiprocessing
multiprocessing.current_process().name = "daq6510_cs"

import sys

import click
import invoke
import rich
import zmq

from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.settings import Settings
from egse.tempcontrol.keithley.daq6510 import DAQ6510Proxy
from egse.tempcontrol.keithley.daq6510_protocol import DAQ6510Protocol
from egse.zmq_ser import connect_address

logger = logging.getLogger(__name__)

CTRL_SETTINGS = Settings.load("Keithley Control Server")


def is_daq6510_cs_active(timeout: float = 0.5) -> bool:
    """ Checks if the DAQ6510 Control Server is running.

    Args:
        timeout (float): Timeout when waiting for a reply [s, default=0.5]

    Returns:  True if the Control Server is running and replied with the expected answer; False otherwise.
    """

    endpoint = connect_address(
        CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.HOSTNAME, CTRL_SETTINGS.COMMANDING_PORT
    )

    return is_control_server_active(endpoint, timeout)


class DAQ6510ControlServer(ControlServer):
    """
    Keithley DAQ6510ControlServer - Command and monitor the Keithley Data Acquisition System.

    This class works as a command and monitoring server to control the DAQ6510 Controller.

    The sever binds to the following ZeroMQ sockets:

        - REQ-REP socket that can be used as a command server. Any client can connect and send a command to the
          DAQ6510 controller.

        - PUB-SUP socket that serves as a monitoring server. It will send out DAQ6510 status information to all the
          connected clients every DELAY seconds.

    """

    def __init__(self):
        """ Initialisation of a DAQ6510 Control Server."""

        super().__init__()

        self.device_protocol = DAQ6510Protocol(self)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

    def get_communication_protocol(self) -> str:
        """ Returns the communication protocol used by the Control Server.

        Returns: Communication protocol used by the Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.PROTOCOL

    def get_commanding_port(self) -> int:
        """ Returns the commanding port used by the Control Server.

        Returns: Commanding port used by the Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.COMMANDING_PORT

    def get_service_port(self):
        """ Returns the service port used by the Control Server.

        Returns: Service port used by the Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.SERVICE_PORT

    def get_monitoring_port(self):
        """ Returns the monitoring port used by the Control Server.

        Returns: Monitoring port used by the Control Server, as specified in the settings.
        """

        return CTRL_SETTINGS.MONITORING_PORT

    def get_storage_mnemonic(self):
        """ Returns the storage mnemonics used by the Control Server.

        This is a string that will appear in the filename with the housekeeping information of the device, as a way of
        identifying the device.  If this is not implemented in the sub-class, then the class name will be used.

        Returns: Storage mnemonics used by the Control Server, as specified in the settings.  If not specified in the
                 settings, "DAQ6510" will be used.
        """

        try:
            return CTRL_SETTINGS.STORAGE_MNEMONIC
        except AttributeError:
            return "DAQ6510"

    def before_serve(self):
        """ Steps to take before the Control Server is activated."""

        start_http_server(CTRL_SETTINGS.METRICS_PORT)


@click.group()
def cli():
    pass


@cli.command()
def start():
    """ Starts the Keithley DAQ6510 Control Server."""

    try:
        control_server = DAQ6510ControlServer()
        control_server.serve()
    except KeyboardInterrupt:
        logger.debug("Shutdown requested...exiting")
    except SystemExit as exit_code:
        logger.debug("System Exit with code {}.".format(exit_code))
        sys.exit(exit_code)
    except Exception:
        msg = "Cannot start the DAQ6510 Control Server"
        logger.exception(msg)
        rich.print(f"[red]{msg}.")

    return 0


@cli.command()
def start_bg():
    """ Starts the DAQ6510 Control Server in the background."""

    invoke.run("daq6510_cs start", disown=True)


@cli.command()
def stop():
    """ Sends a 'quit_server' command to the Keithley DAQ6510 Control Server."""

    try:
        with DAQ6510Proxy() as daq:
            sp = daq.get_service_proxy()
            sp.quit_server()
    except ConnectionError as exc:
        msg = "Cannot stop the DAQ6510 Control Server"
        logger.exception(msg)
        rich.print(f"[red]{msg}, could not send the Quit command. [black]Check log messages.")


@cli.command()
def status():
    """ Requests status information from the Control Server."""

    protocol = CTRL_SETTINGS.PROTOCOL
    hostname = CTRL_SETTINGS.HOSTNAME
    port = CTRL_SETTINGS.COMMANDING_PORT

    endpoint = connect_address(protocol, hostname, port)

    if is_control_server_active(endpoint):
        rich.print(f"DAQ6510 CS: [green]active")
        with DAQ6510Proxy() as daq6510:
            sim = daq6510.is_simulator()
            connected = daq6510.is_connected()
            ip = daq6510.get_ip_address()
            rich.print(f"mode: {'simulator' if sim else 'device'}{' not' if not connected else ''} connected")
            rich.print(f"hostname: {ip}")
    else:
        rich.print(f"DAQ6510 CS: [red]not active")


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

    sys.exit(cli())
