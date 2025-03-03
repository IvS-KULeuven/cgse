"""
This module provides a dummy implementation for classes of the commanding chain.

Start the control server with:

    py -m egse.dummy start-cs

and stop the server with:

    py -m egse.dummy stop-cs

Commands that can be used with the proxy:

  * info – returns an info message from the dummy device, e.g. "Dummy Device <__version__>"
  * get_value – returns a random float between 0.0 and 1.0

The device simulator can be started with:

    py -m egse.dummy start-dev

"""
from __future__ import annotations

import logging
import multiprocessing
import random
import select
import socket
import sys
import threading
import time
from functools import partial

import typer
import zmq

from egse.command import ClientServerCommand
from egse.confman import is_configuration_manager_active
from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.decorators import dynamic_interface
from egse.device import DeviceConnectionError
from egse.device import DeviceConnectionInterface
from egse.device import DeviceTimeoutError
from egse.device import DeviceTransport
from egse.listener import Event
from egse.listener import EventInterface
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.settings import Settings
from egse.system import SignalCatcher
from egse.system import attrdict
from egse.system import format_datetime
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

_LOGGER = logging.getLogger("egse.dummy")

__version__ = "0.2.0"

DEV_HOST = "localhost"
"""The hostname or IP address of the Dummy Device."""
DEV_PORT = 4446
"""The port number for the Dummy Device."""
DEV_NAME = "Dummy Device"
"""The name used for theDummy Device, this is used in Exceptions and in the info command."""

READ_TIMEOUT = 10.0
"""The maximum time in seconds to wait for a socket receive command."""
WRITE_TIMEOUT = 1.0
"""The maximum time in seconds to wait for a socket send command."""
CONNECT_TIMEOUT = 3.0
"""The maximum time in seconds to wait for establishing a socket connect."""

# Especially DummyCommand and DummyController need to be defined in a known module
# because those objects are pickled and when de-pickled at the clients side the class
# definition must be known.

# We use AttributeDict here to define the settings, because that is how the Settings.load() returns
# settings loaded from a YAML file.

ctrl_settings = attrdict(
    {
        'HOSTNAME': 'localhost',
        'COMMANDING_PORT': 4443,
        'SERVICE_PORT': 4444,
        'MONITORING_PORT': 4445,
        'PROTOCOL': 'tcp',
        'TIMEOUT': 10_000,  # milliseconds
        'HK_DELAY': 1.0,
    }
)

commands = attrdict(
    {
        'info': {
            'description': 'Info on the Dummy Device.',
            'response': 'handle_device_method'
        },
        'get_value': {
            'description': 'Read a value from the device.',
        },
        'handle_event': {
            'description': "Notification of an event",
            'device_method': 'handle_event',
            'cmd': '{event}',
            'response': 'handle_device_method'
        },
    }
)


def is_dummy_cs_active():
    """Returns True if the dummy device control server is active."""
    return is_control_server_active(
        endpoint=connect_address(ctrl_settings.PROTOCOL, ctrl_settings.HOSTNAME, ctrl_settings.COMMANDING_PORT)
    )


class DummyCommand(ClientServerCommand):
    """The Command class for the dummy device."""
    pass


class DummyInterface:
    """The interface for the dummy device."""
    @dynamic_interface
    def info(self) -> str:
        """Return an info string from the device."""
        ...

    @dynamic_interface
    def get_value(self, *args, **kwargs) -> float:
        """
        Return a float value from the device.
        This dummy implementation will return a random number between 0.0 and 1.0.
        """
        ...


class DummyProxy(Proxy, DummyInterface, EventInterface):
    """
    The Proxy class for the dummy device.

    Args:
        protocol: the transport protocol [default is taken from settings file]
        hostname: location of the control server (IP address) [default is taken from settings file]
        port: TCP port on which the control server is listening for commands [default is taken from settings file]
        timeout: a socket timeout in milliseconds
    """

    def __init__(
            self,
            protocol: str = ctrl_settings.PROTOCOL,
            hostname: str = ctrl_settings.HOSTNAME,
            port: int = ctrl_settings.COMMANDING_PORT,
            timeout: int = ctrl_settings.TIMEOUT
    ):
        super().__init__(connect_address(protocol, hostname, port), timeout=timeout)


class DummyController(DummyInterface, EventInterface):
    """
    The controller class for the dummy device.

    This class is used to directly communicate with the device.
    """
    def __init__(self, control_server):
        self._cs = control_server
        self._dev = DummyDeviceEthernetInterface(DEV_HOST, DEV_PORT)
        self._dev.connect()

    def info(self) -> str:
        return self._dev.trans("info").decode().strip()

    def get_value(self) -> float:
        return float(self._dev.trans("get_value").decode().strip())

    def handle_event(self, event: Event) -> str:

        _exec_in_thread = False

        def _handle_event(_event):
            _LOGGER.info(f"An event is received, {_event=}")
            _LOGGER.info(f"CM CS active? {is_configuration_manager_active()}")
            time.sleep(5.0)
            _LOGGER.info(f"CM CS active? {is_configuration_manager_active()}")
            _LOGGER.info(f"An event is processed, {_event=}")

        if _exec_in_thread:
            # We execute this function in a daemon thread so the acknowledgment is
            # sent back immediately (the ACK means 'command received and will be
            # executed').

            retry_thread = threading.Thread(target=_handle_event, args=(event,))
            retry_thread.daemon = True
            retry_thread.start()
        else:
            # An alternative to the daemon thread is to create a scheduled task that will be executed
            # after the event is acknowledged.

            self._cs.schedule_task(partial(_handle_event, event))

        return "ACK"


class DummyProtocol(CommandProtocol):
    """
    The protocol class for the dummy device.

    This class defines the communication between the client (usually a Proxy) and
    the server (the control server) for this device.

    Args:
        control_server: the control server for the dummy device.
    """
    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

        self.device_controller = DummyController(control_server)

        self.load_commands(commands, DummyCommand, DummyController)

        self.build_device_method_lookup_table(self.device_controller)

        self._count = 0

    def get_bind_address(self):
        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_status(self):
        return super().get_status()

    def get_housekeeping(self) -> dict:

        # _LOGGER.debug(f"Executing get_housekeeping function for {self.__class__.__name__}.")

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

    def quit(self):
        _LOGGER.info("Executing 'quit()' on DummyProtocol.")


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
        multiprocessing.current_process().name = "dummy_cs"

        super().__init__()

        self.device_protocol = DummyProtocol(self)

        _LOGGER.info(
            f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()} for {self.__class__.__name__}"
        )

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.set_hk_delay(ctrl_settings.HK_DELAY)

        from egse.confman import ConfigurationManagerProxy
        from egse.listener import EVENT_ID

        # The following import is needed because without this import, DummyProxy would be <class '__main__.DummyProxy'>
        # instead of `egse.dummy.DummyProxy` and the ConfigurationManager control server will not be able to de-pickle
        # the register message.
        from egse.dummy import DummyProxy  # noqa

        self.register_as_listener(
            proxy=ConfigurationManagerProxy,
            listener={'name': 'Dummy CS', 'proxy': DummyProxy, 'event_id': EVENT_ID.SETUP}
        )

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

    def after_serve(self):
        _LOGGER.debug("After Serve: unregistering Dummy CS")

        from egse.confman import ConfigurationManagerProxy

        self.unregister_as_listener(proxy=ConfigurationManagerProxy, listener={'name': 'Dummy CS'})


class DummyDeviceEthernetInterface(DeviceConnectionInterface, DeviceTransport):
    """
    Defines the low-level interface to the Dummy Device.

    Args:
        hostname (str): the IP address or fully qualified hostname of the Dummy Device
            controller.

        port (int): the IP port number to connect to.
    """
    def __init__(self, hostname: str = None, port: int = None):

        super().__init__()

        # Basic connection settings, loaded from the configuration YAML file

        self.hostname = hostname
        self.port = port
        self.sock = None

        self.is_connection_open = False

    def connect(self):
        """
        Connects the TCP socket to the device controller.

        Raises:
            ValueError: when hostname or port number are not initialized properly.
            DeviceConnectionError: on any socket error except timeouts.
            DeviceTimeoutError: on a socket timeout.
        """
        # Sanity checks

        if self.is_connection_open:
            _LOGGER.warning("Trying to connect to an already connected socket.")
            return

        if self.hostname in (None, ""):
            raise ValueError("hostname is not initialized.")

        if self.port in (None, 0):
            raise ValueError("port number is not initialized.")

        # Create a new socket instance

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as exc:
            self.sock.close()
            raise DeviceConnectionError("Dummy Device", "Failed to create socket.") from exc

        # Attempt to establish a connection to the remote host

        # Socket shall be closed on exception?
        # Closing a socket doesn't harm and almost never throws an exception,
        # except for fatal exceptions like MemoryError, ...

        # We set a timeout of 3 sec before connecting and reset to None
        # (=blocking) after the connect() method. The reason for this that when no
        # device is available, e.g. during testing, the timeout will take about
        # two minutes which is way too long. It needs to be evaluated if this
        # approach is acceptable and not causing problems during production.

        try:
            _LOGGER.debug(f'Connecting a socket to host "{self.hostname}" using port {self.port}')
            self.sock.settimeout(CONNECT_TIMEOUT)
            self.sock.connect((self.hostname, self.port))
            self.sock.settimeout(None)
        except ConnectionRefusedError as exc:
            self.sock.close()
            raise DeviceConnectionError(
                DEV_NAME, f"Connection refused to {self.hostname}:{self.port}."
            ) from exc
        except TimeoutError as exc:
            self.sock.close()
            raise DeviceTimeoutError(
                DEV_NAME, f"Connection to {self.hostname}:{self.port} timed out."
            ) from exc
        except socket.gaierror as exc:
            self.sock.close()
            raise DeviceConnectionError(
                DEV_NAME, f"socket address info error for {self.hostname}"
            ) from exc
        except socket.herror as exc:
            self.sock.close()
            raise DeviceConnectionError(
                DEV_NAME, f"socket host address error for {self.hostname}"
            ) from exc
        except OSError as exc:
            self.sock.close()
            raise DeviceConnectionError(DEV_NAME, f"OSError caught ({exc}).") from exc

        self.is_connection_open = True

        # The first thing to receive should be the device info string.
        # This might not be the case for your device.

        response = self.read()
        _LOGGER.debug(f"After connection, we got '{response.decode().rstrip()}' as a response.")

    def disconnect(self):
        """
        Disconnect the Ethernet connection from the device controller.

        Raises:
             DeviceConnectionError: on failure.
        """
        try:
            _LOGGER.debug(f'Disconnecting from {self.hostname}')
            self.sock.close()
            self.is_connection_open = False
        except Exception as exc:
            raise DeviceConnectionError(
                DEV_NAME, f"Could not close socket to {self.hostname}") from exc

    def reconnect(self):
        """Disconnect from the device, then connect again."""
        if self.is_connection_open:
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """
        Check if the device is connected.

        Returns:
             True is the device is connected, False otherwise.
        """

        return bool(self.is_connection_open)

    def read(self) -> bytes:
        """
        Read a response from the device.

        Returns:
            A bytes object containing the response from the device. No processing is done
            on the response.

        Raises:
            DeviceTimeoutError: when the read operation timed out.
        """
        n_total = 0
        buf_size = 1024 * 10
        response = bytes()

        # Set a timeout of READ_TIMEOUT to the socket.recv

        saved_timeout = self.sock.gettimeout()
        self.sock.settimeout(READ_TIMEOUT)

        try:
            for _ in range(100):
                # time.sleep(0.1)  # Give the device time to fill the buffer
                data = self.sock.recv(buf_size)
                n = len(data)
                n_total += n
                response += data
                if n < buf_size:
                    break
        except socket.timeout as exc:
            _LOGGER.warning(f"Socket timeout error: {exc}")
            raise DeviceTimeoutError(DEV_NAME, "Socket timeout error") from exc
        finally:
            self.sock.settimeout(saved_timeout)

        # _LOGGER.debug(f"Total number of bytes received is {n_total}, idx={idx}")
        # _LOGGER.debug(f"> {response[:80]=}")

        return response

    def write(self, command: str) -> None:
        """
        Send a command to the device.

        No processing is done on the command string, except for the encoding into a bytes object.

        Args:
            command: the command string including terminators.

        Raises:
            DeviceTimeoutError: when the sendall() timed out, and a DeviceConnectionError if
                there was a socket related error.
        """

        # _LOGGER.debug(f"{command.encode() = }")

        try:
            self.sock.sendall(command.encode())
        except socket.timeout as exc:
            raise DeviceTimeoutError(DEV_NAME, "Socket timeout error") from exc
        except socket.error as exc:
            # Interpret any socket-related error as an I/O error
            raise DeviceConnectionError(DEV_NAME, "Socket communication error.") from exc

    def trans(self, command: str) -> bytes:
        """
        Send a command to the device and wait for the response.

        No processing is done on the command string, except for the encoding into a bytes object.

        Args:
            command: the command string including terminators.

        Returns:
            A bytes object containing the response from the device. No processing is done
            on the response.

        Raises:
            DeviceTimeoutError: when the sendall() timed out, and a DeviceConnectionError if
                there was a socket related error.
        """
        # MODULE_LOGGER.debug(f"{command.encode() = }")

        try:
            # Attempt to send the complete command

            self.sock.sendall(command.encode())

            # wait for, read and return the response (will be at most TBD chars)

            return self.read()

        except socket.timeout as exc:
            raise DeviceTimeoutError(DEV_NAME, "Socket timeout error") from exc
        except socket.error as exc:
            # Interpret any socket-related error as an I/O error
            raise DeviceConnectionError(DEV_NAME, "Socket communication error.") from exc


app = typer.Typer()


@app.command()
def start_cs():
    """Start the dummy control server on localhost."""

    # The following import is needed because without this import, the control server and Proxy will not be able to
    # instantiate classes that are passed in ZeroMQ messages and de-pickled.
    from egse.dummy import DummyControlServer  # noqa

    try:
        control_server = DummyControlServer()
        control_server.serve()
    except KeyboardInterrupt:
        print("Shutdown requested...exiting")
    except SystemExit as exit_code:
        print(f"System Exit with code {exit_code}.")
        sys.exit(-1)
    except Exception:  # noqa
        import traceback
        traceback.print_exc(file=sys.stdout)


@app.command()
def stop_cs():
    """Send a quit service command to the dummy control server."""
    with DummyProxy() as dummy:
        _LOGGER.info("Sending quit_server() to Dummy CS.")
        sp = dummy.get_service_proxy()
        sp.quit_server()


# ----- Dummy Device functions -----------------------------------------------------------------------------------------

error_msg = ""


@app.command()
def start_dev():
    """Start the dummy device simulator."""
    global error_msg

    multiprocessing.current_process().name = "dummy_dev"

    _LOGGER.info("Starting the Dummy Device simulator")

    quit_request = False
    timeout = 1.0

    killer = SignalCatcher()

    while not quit_request:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((DEV_HOST, DEV_PORT))
            s.listen()
            conn, addr = s.accept()
            with conn:
                _LOGGER.info(f"Accepted connection from {addr}")
                conn.sendall(f"Dummy Device {__version__}".encode())
                try:
                    while True:
                        error_msg = ""
                        read_sockets, _, _ = select.select([conn], [], [], timeout)
                        if conn in read_sockets:
                            data = conn.recv(4096)
                            if not data:
                                _LOGGER.info("Connection closed by peer, waiting for connection..")
                                break  # connection closed by peer
                            if (response := process_command(data.decode().rstrip())) is not None:
                                response = f"{response}\r\n".encode()
                                conn.sendall(response)
                            _LOGGER.debug(f"{data = } -> {response = }")
                        if killer.term_signal_received:
                            _LOGGER.info("TERM signal received, terminating...")
                            quit_request = True
                            break
                        # _LOGGER.debug(f"Timeout received after {timeout}s..")
                except KeyboardInterrupt:
                    _LOGGER.info("Keyboard interrupt, closing.")
                except ConnectionResetError as exc:
                    _LOGGER.info(f"ConnectionResetError: {exc}")
                except Exception as exc:
                    _LOGGER.info(f"{exc.__class__.__name__} caught: {exc.args}")

    _LOGGER.info("Dummy Device terminated.")


COMMAND_ACTIONS_RESPONSES = {
    "info": (None, f"Dummy Device {__version__}"),
    "get_value": (None, random.random)
}


def process_command(command_string: str) -> str | None:

    _LOGGER.debug(f"{command_string = }")

    try:
        action, response = COMMAND_ACTIONS_RESPONSES[command_string]
        action and action()
        if error_msg:
            return error_msg
        else:
            return response if isinstance(response, str) else response()
    except KeyError:
        from egse.system import get_caller_breadcrumbs
        _LOGGER.info(get_caller_breadcrumbs())
        raise NotImplementedError(f"{command_string} not yet implemented..")


if __name__ == "__main__":
    app()
