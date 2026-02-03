"""
Keithley DAQ6510 Synchronous Control Server.

This module implements a Control Server to command and monitor a Keithley DAQ6510 Data Acquisition System.

The control server can be started from the command line interface as follows:

    $ daq6510_cs start

It can also be stopped, queried for status information, etc.  Use the --help option to see all available commands:

    $ daq6510_cs --help

Functions:

    is_daq6510_cs_active(timeout: float = 0.5) -> bool
        Checks if the DAQ6510 Control Server is running.
Classes:
    DAQ6510ControlServer(ControlServer)
        Keithley DAQ6510ControlServer - Command and monitor the Keithley Data Acquisition System.

"""

import multiprocessing
import sys

import rich
import typer
import zmq

from egse.connect import get_endpoint
from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.log import logger
from egse.logger import remote_logging
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.storage import store_housekeeping_information
from egse.tempcontrol.keithley.daq6510 import DAQ6510Proxy
from egse.tempcontrol.keithley.daq6510_protocol import DAQ6510Protocol
from egse.zmq_ser import connect_address

cs_settings = Settings.load("Keithley Control Server")

PROTOCOL = cs_settings.get("PROTOCOL", "tcp")
HOSTNAME = cs_settings.get("HOSTNAME", "localhost")
COMMANDING_PORT = cs_settings.get("COMMANDING_PORT", 0)
STORAGE_MNEMONIC = cs_settings.get("STORAGE_MNEMONIC", "DAQ6510")
SERVICE_TYPE = cs_settings.get("SERVICE_TYPE", "daq6510")


def is_daq6510_cs_active(timeout: float = 0.5) -> bool:
    """Checks if the DAQ6510 Control Server is running.

    Args:
        timeout (float): Timeout when waiting for a reply [s, default=0.5]

    Returns:  True if the Control Server is running and replied with the expected answer; False otherwise.
    """

    if COMMANDING_PORT == 0:
        with RegistryClient() as client:
            endpoint = client.get_endpoint(SERVICE_TYPE)
            if endpoint is None:
                logger.debug(f"No endpoint for {SERVICE_TYPE}")
                return False
    else:
        endpoint = connect_address(PROTOCOL, HOSTNAME, COMMANDING_PORT)

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
        """Initialization of a DAQ6510 Control Server."""

        super().__init__()

        self.device_protocol = DAQ6510Protocol(self)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service(service_type=cs_settings.SERVICE_TYPE)

    def get_communication_protocol(self) -> str:
        """Returns the communication protocol used by the Control Server.

        Returns: Communication protocol used by the Control Server, as specified in the settings.
        """

        return cs_settings.PROTOCOL

    def get_commanding_port(self) -> int:
        """Returns the commanding port used by the Control Server.

        Returns: Commanding port used by the Control Server, as specified in the settings.
        """

        return cs_settings.COMMANDING_PORT

    def get_service_port(self):
        """Returns the service port used by the Control Server.

        Returns: Service port used by the Control Server, as specified in the settings.
        """

        return cs_settings.SERVICE_PORT

    def get_monitoring_port(self):
        """Returns the monitoring port used by the Control Server.

        Returns: Monitoring port used by the Control Server, as specified in the settings.
        """

        return cs_settings.MONITORING_PORT

    def get_storage_mnemonic(self):
        """Returns the storage mnemonics used by the Control Server.

        This is a string that will appear in the filename with the housekeeping information of the device, as a way of
        identifying the device.  If this is not implemented in the sub-class, then the class name will be used.

        Returns: Storage mnemonics used by the Control Server, as specified in the settings.  If not specified in the
                 settings, "DAQ6510" will be used.
        """

        return STORAGE_MNEMONIC

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
            },
        )

    def unregister_from_storage_manager(self):
        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=self.get_storage_mnemonic())

    def before_serve(self):
        """Steps to take before the Control Server is activated."""


app = typer.Typer(name="daq6510_cs")


@app.command()
def start():
    """Starts the Keithley DAQ6510 Control Server."""

    multiprocessing.current_process().name = "daq6510_cs (start)"

    with remote_logging():
        from egse.env import setup_env

        setup_env()

        try:
            control_server = DAQ6510ControlServer()
            control_server.serve()
        except KeyboardInterrupt:
            logger.debug("Shutdown requested...exiting")
        except SystemExit as exit_code:
            logger.debug("System Exit with code {}.".format(exit_code))
            sys.exit(exit_code.code)
        except Exception:
            msg = "Cannot start the DAQ6510 Control Server"
            logger.exception(msg)
            rich.print(f"[red]{msg}.")

    return 0


@app.command()
def start_bg():
    """Starts the DAQ6510 Control Server in the background."""

    print("Starting the DAQ6510 in the background is not implemented.")


@app.command()
def stop():
    """Sends a 'quit_server' command to the Keithley DAQ6510 Control Server."""

    multiprocessing.current_process().name = "daq6510_cs (stop)"

    from egse.env import setup_env

    setup_env()

    try:
        with DAQ6510Proxy() as daq:
            sp = daq.get_service_proxy()
            sp.quit_server()
    except ConnectionError:
        msg = "Cannot stop the DAQ6510 Control Server"
        logger.error(msg, exc_info=True)
        rich.print(f"[red]{msg}, could not send the Quit command. [black]Check log messages.")


@app.command()
def status():
    """Requests status information from the Control Server."""

    multiprocessing.current_process().name = "daq6510_cs (status)"

    from egse.env import setup_env

    setup_env()

    endpoint = get_endpoint(SERVICE_TYPE, PROTOCOL, HOSTNAME, COMMANDING_PORT)

    if is_control_server_active(endpoint):
        rich.print("DAQ6510 CS: [green]active")
        with DAQ6510Proxy() as daq6510:
            sim = daq6510.is_simulator()
            connected = daq6510.is_connected()
            ip = daq6510.get_ip_address()
            rich.print(f"mode: {'simulator' if sim else 'device'}{' not' if not connected else ''} connected")
            rich.print(f"hostname: {ip}")
    else:
        rich.print("DAQ6510 CS: [red]not active")


if __name__ == "__main__":
    sys.exit(app())
