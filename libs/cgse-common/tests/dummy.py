"""
This module provides dummy implementation for classes of the Commanding chain.
"""
import logging
import pickle
import random
import sys

import click
import zmq

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.decorators import dynamic_interface
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.settings import Settings
from egse.system import AttributeDict
from egse.system import format_datetime
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)
LOGGER = logging.getLogger("egse.dummy")

# Especially DummyCommand and DummyController need to be defined in a known module
# because those objects are pickled and when de-pickled at the clients side the class
# definition must be known.

# We use AttributeDict here to define the settings, because that is how the Settings.load() returns
# settings loaded from a YAML file.

ctrl_settings = AttributeDict(
    {
        'HOSTNAME': 'localhost',
        'COMMANDING_PORT': 4443,
        'SERVICE_PORT': 4444,
        'MONITORING_PORT': 4445,
        'PROTOCOL': 'tcp',
        'TIMEOUT': 10,
        'HK_DELAY': 1.0,
    }
)

commands = AttributeDict(
    {
        'info': {
            'description': 'Info on the Dummy Controller',
            'response': 'handle_device_method'
        },
        'response': {
            'description': 'send a command to the device and return it\'s response',
            'device_method': 'response',
            'cmd': '{one} {two} {fake}',
            'response': 'handle_device_method'
        }
    }
)


def is_dummy_cs_active():
    return is_control_server_active(
        endpoint=connect_address(ctrl_settings.PROTOCOL, ctrl_settings.HOSTNAME, ctrl_settings.COMMANDING_PORT)
    )


class DummyCommand(ClientServerCommand):
    pass


class DummyInterface:
    @dynamic_interface
    def info(self):
        ...
    @dynamic_interface
    def response(self, *args, **kwargs):
        ...


class DummyProxy(Proxy, DummyInterface):
    def __init__(self,
                 protocol=ctrl_settings.PROTOCOL, hostname=ctrl_settings.HOSTNAME, port=ctrl_settings.COMMANDING_PORT):
        """
        Args:
            protocol: the transport protocol [default is taken from settings file]
            hostname: location of the control server (IP address) [default is taken from settings file]
            port: TCP port on which the control server is listening for commands [default is taken from settings file]
        """
        super().__init__(connect_address(protocol, hostname, port), timeout=ctrl_settings.TIMEOUT)


class DummyController(DummyInterface):
    def info(self):
        return "method info() called on DummyController"

    def response(self, *args, **kwargs):
        return f"response({args}, {kwargs})"


class DummyProtocol(CommandProtocol):

    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

        self.device_controller = DummyController()

        self.load_commands(commands, DummyCommand, DummyController)

        self.build_device_method_lookup_table(self.device_controller)

        self._count = 0

    def get_bind_address(self):
        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_status(self):
        return super().get_status()

    def get_housekeeping(self) -> dict:

        LOGGER.debug(f"Executing get_housekeeping function for {self.__class__.__name__}.")

        self._count += 1

        # use the sleep to test the responsiveness of the control server when even this get_housekeeping function takes
        # a lot of time, i.e. up to several minutes in the case of data acquisition devices
        # import time
        # time.sleep(2.0)


        return {
            'timestamp': format_datetime(),
            'COUNT': self._count,
            'PI': 3.14159,  # just to have a constant parameter
            'Random': random.randint(0, 100),  # just to have a variable parameter
        }


class DummyControlServer(ControlServer):
    """
    DummyControlServer - Command and monitor dummy device controllers.

    The sever binds to the following ZeroMQ sockets:

    * a REQ-REP socket that can be used as a command server. Any client can connect and
      send a command to the dummy device controller.

    * a PUB-SUP socket that serves as a monitoring server. It will send out status
      information to all the connected clients every DELAY seconds.

    """

    def __init__(self):
        super().__init__()

        self.device_protocol = DummyProtocol(self)

        self.logger.info(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.set_hk_delay(ctrl_settings.HK_DELAY)

    def get_communication_protocol(self):
        return 'tcp'

    def get_commanding_port(self):
        return ctrl_settings.COMMANDING_PORT

    def get_service_port(self):
        return ctrl_settings.SERVICE_PORT

    def get_monitoring_port(self):
        return ctrl_settings.MONITORING_PORT

    def get_storage_mnemonic(self):
        return "DUMMY-HK"


@click.group()
def cli():
    pass


@cli.group()
def control_server():
    pass


@control_server.command()
def start():
    """Start the dummy control server on localhost."""

    try:
        control_server = DummyControlServer()
        control_server.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exit_code:
        print(f"System Exit with code {exit_code}.")
        sys.exit(1)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stdout)


@control_server.command()
def stop():
    """Send a quit service command to the dummy control server."""
    with DummyProxy() as dummy:
        sp = dummy.get_service_proxy()
        sp.quit_server()


if __name__ == "__main__":
    cli()
