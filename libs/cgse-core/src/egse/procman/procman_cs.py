"""
The Process Manager Control Server is the service that handles all Common-EGSE
processes.  The list of processes to handle, is taken from the Configuration
Manager (from the setup).

The Process Manager Control Server is implemented as a standard control server.
"""
import logging
import multiprocessing
import sys

import click
import zmq
from prometheus_client import start_http_server

from egse.control import ControlServer
from egse.procman import ProcessManagerProtocol
from egse.procman import ProcessManagerProxy
from egse.procman import is_process_manager_cs_active
from egse.settings import Settings

CTRL_SETTINGS = Settings.load("Process Manager Control Server")

logger = logging.getLogger(__name__)


class ProcessManagerControlServer(ControlServer):
    """
    The Process Manager Control Server handles all Common-EGSE processes.
    """

    def __init__(self):
        """Initialisation of a new Control Server for Process Management.

        The initialisation of this Control Server consists of the following
        steps:

            - Define the device protocol;
            - Bind the command socket to the device protocol (to listen for
              commands);
            - Add the device protocol to the poller, to be able to listen for
              commands on different sockets in one thread.
        """

        super().__init__()

        # Protocol used for commanding

        self.device_protocol = ProcessManagerProtocol(self)

        # Bind to a socket to listen for commands

        bind_address = self.device_protocol.get_bind_address()

        self.logger = logger
        self.logger.debug(f"Binding ZeroMQ socket to {bind_address}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        # Listen on different sockets in the same threads -> poller

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

    def get_communication_protocol(self):
        """Returns the communication protocol, as defined in the settings.

        Returns:
            - Communication protocol, as defined in the settings.
        """
        return CTRL_SETTINGS.PROTOCOL

    def get_commanding_port(self):
        """Returns the commanding port number.

        The commanding port is the port on which the Controller listens for
        commands, using the REQ-REP (ZeroMQ) socket pattern.  Its number is
        read from the settings file.

        Returns:
            - Number of the port on which the Controller listens for commands.
        """

        return CTRL_SETTINGS.COMMANDING_PORT

    def get_service_port(self):
        """Returns the service port number.

        The service port is the port on which the Controller listens for
        configuration and administration, using the PUB-SUB (ZeroMQ) socket
        pattern.  Its number is read from the settings file.

        Returns:
            - Number of the port on which the Controller listens for
              configuration and administration.
        """

        return CTRL_SETTINGS.SERVICE_PORT

    def get_monitoring_port(self):
        """Returns the monitoring port number.

        The monitoring port is the port on which the Controller sends periodic
        information on the device, using the PUB-SUB (ZeroMQ) socket
        pattern.  Its number is read from the settings file.

        Returns:
            - Number of the port on which the Controller sends periodic status
              information on the device.
        """

        return CTRL_SETTINGS.MONITORING_PORT

    def get_storage_mnemonic(self):
        """Returns the storage mnemonic for the Controller.

        The storage mnemonic is used in the filename of the housekeeping of
        the Controller (as using by the Storage).  If this is not defined in
        the settings file, "PM" will be used instead.

        Returns:
            - Storage mnemonic for the Controller.
        """

        try:

            # As defined in the settings file

            return CTRL_SETTINGS.STORAGE_MNEMONIC

        except AttributeError:

            # Default

            return "PM"

    def before_serve(self):
        start_http_server(CTRL_SETTINGS.METRICS_PORT)


@click.group()
def cli():
    pass


@cli.command()
def start():
    """Start the Process Manager."""

    multiprocessing.current_process().name = "procman_cs"

    # We import this class such that the class name is
    # 'egse.procman.procman_cs.ProcessManagerControlServer' and we
    # can compare self with isinstance inside the Control.
    # If this import would not be done, the class name for the
    # ProcessManagerControlServer would be '__main__.ProcessManagerControlServer'.

    from egse.procman.procman_cs import ProcessManagerControlServer

    try:
        control_server = ProcessManagerControlServer()
        control_server.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exit_code:
        print("System Exit with code {}.".format(exit_code))
        sys.exit(exit_code)
    except Exception:
        import traceback

        traceback.print_exc(file=sys.stdout)

    return 0


@cli.command()
def stop():
    """Send a 'quit_server' command to the Process Manager."""
    with ProcessManagerProxy() as pm:
        sp = pm.get_service_proxy()
        sp.quit_server()


@cli.command()
def status():
    """Send a 'quit_server' command to the Process Manager."""

    import rich
    rich.print("Process Manager:")
    if is_process_manager_cs_active():
        rich.print(f"  Status: [green]active")
        with ProcessManagerProxy() as pm:
            rich.print(f"  Hostname: {pm.get_ip_address()}")
            rich.print(f"  Monitoring port: {pm.get_monitoring_port()}")
            rich.print(f"  Commanding port: {pm.get_commanding_port()}")
            rich.print(f"  Service port: {pm.get_service_port()}")
    else:
        rich.print(f"  Status: [red]not active")


if __name__ == "__main__":
    sys.exit(cli())
