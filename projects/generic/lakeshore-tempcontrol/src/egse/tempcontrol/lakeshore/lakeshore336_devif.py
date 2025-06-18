import logging
import socket
from typing import Optional

import time

from egse.command import ClientServerCommand
from egse.device import DeviceConnectionInterface, DeviceTransport
from egse.settings import Settings

DEVICE_SETTINGS = Settings.load("LakeShore336 Controller")

logger = logging.getLogger(__name__)


class LakeShore336Command(ClientServerCommand):
    """Commands for the Lakeshore336 temperature controller.

    A Command is basically a string that is sent to a device and for which the device returns a response.  The command
    string can contain placeholders that will be filled when the command is called.  The arguments that are given, will
    be filled into the formatted string.  Arguments can be positional or keyword arguments, not both.
    """

    def get_cmd_string(self, *args, **kwargs) -> str:
        """Returns the formatted command string with the given positional and/or keyword arguments filled out.

        Args:
            *args: Positional arguments that are needed to construct the command string
            **kwargs: Keyword arguments that are needed to construct the command string
        """

        out = super().get_cmd_string(*args, **kwargs)
        return out + "\n"


class LakeShore336Error(Exception):
    """Base exception for all LakeShore336 errors."""

    pass


class LakeShore336EthernetInterface(DeviceConnectionInterface, DeviceTransport):
    """Defines the low-level interface to the LakeShore336 temperature controller."""

    def __init__(self, device_id: str, hostname: str = None, port: int = None):
        """Initialisation of an Ethernet interface for the Lakeshore336.

        Args:
            device_id (str): Device identifier
            hostname (str): Hostname to which to open a socket
            port (int): Port to which to open a socket
        """

        super().__init__()

        self.device_id = device_id

        self.hostname = DEVICE_SETTINGS[device_id]["HOSTNAME"] if hostname is None else hostname
        self.port = DEVICE_SETTINGS[device_id]["PORT"] if port is None else port

        self._socket = None
        self._is_connection_open = False

    def connect(self):
        """Connects to the Ethernet connection.

        Raises:
            LakeShore336Error when no connection could be established
        """

        # Sanity checks

        if self._is_connection_open:
            logger.warning(f"{self.device_id}: trying to connect to an already connected socket.")
            return

        if self.hostname in (None, ""):
            raise LakeShore336Error(f"{self.device_id}: hostname is not initialised.")

        if self.port in (None, 0):
            raise LakeShore336Error(f"{self.device_id}: port number is not initialised.")

        # Create a new socket instance

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # self._socket.setblocking(1)
            # self._socket.settimeout(3)
        except socket.error as e_socket:
            raise LakeShore336Error(self.device_id, "Failed to create socket.") from e_socket

        # Attempt to establish a connection to the remote host

        # FIXME: Socket shall be closed on exception?

        # We set a timeout of 3s before connecting and reset to None (=blocking) after the `connect` method has been
        # called. This is because when no device is available, e.g. during testing, the timeout will take about
        # two minutes, which is way too long. It needs to be evaluated if this approach is acceptable and not causing
        # problems during production.

        try:
            logger.debug(f'Connecting a socket to host "{self.hostname}" using port {self.port}')
            self._socket.settimeout(3)
            self._socket.connect((self.hostname, self.port))
            self._socket.settimeout(None)
        except ConnectionRefusedError as exc:
            raise LakeShore336Error(self.device_id, f"Connection refused to {self.hostname}:{self.port}.") from exc
        except TimeoutError as exc:
            raise LakeShore336Error(self.device_id, f"Connection to {self.hostname}:{self.port} timed out.") from exc
        except socket.gaierror as exc:
            raise LakeShore336Error(self.device_id, f"Socket address info error for {self.hostname}") from exc
        except socket.herror as exc:
            raise LakeShore336Error(self.device_id, f"Socket host address error for {self.hostname}") from exc
        except socket.timeout as exc:
            raise LakeShore336Error(self.device_id, f"Socket timeout error for {self.hostname}:{self.port}") from exc
        except OSError as exc:
            raise LakeShore336Error(self.device_id, f"OSError caught ({exc}).") from exc

        self._is_connection_open = True

        # Check that we are connected to the controller by issuing the "*IDN?" or  query. If we don't get the right
        # response, then disconnect automatically.

        if not self.is_connected():
            raise LakeShore336Error(self.device_id, "Device is not connected, check logging messages for the cause.")

    def disconnect(self):
        """Disconnects from the Ethernet connection.

        Raises:
            LakeShore336Error when the socket could not be closed
        """

        try:
            if self._is_connection_open:
                logger.debug(f"Disconnecting from {self.hostname}")
                self._socket.close()
                self._is_connection_open = False
        except Exception as e_exc:
            raise LakeShore336Error(self.device_id, f"Could not close socket to {self.hostname}") from e_exc

    def reconnect(self):
        """Reconnects to the Ethernet connection."""

        if self._is_connection_open:
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """Checks if the client is connected to the device.

        Returns: True if the client is connected to the device; False otherwise.
        """

        if not self._is_connection_open:
            return False

        try:
            version = self.query("*IDN?\n")
        except LakeShore336Error as exc:
            logger.exception(exc)
            logger.error("Most probably the client connection was closed. Disconnecting...")
            self.disconnect()
            return False

        if "LSCI" not in version:
            logger.error(f'Device did not respond correctly to a "*IDN?" command, response={version}. Disconnecting...')
            return False

        return True

    def write(self, command: str):
        """Sends a single command to the device controller without waiting for a response.

        Args
            command (str): Command to send to the controller
        """

        try:
            self._socket.sendall(command.encode())
        except socket.timeout as e_timeout:
            raise LakeShore336Error("Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as a connection error
            raise LakeShore336Error("Socket communication error.") from e_socket
        except AttributeError:
            if not self.is_connected:
                msg = "The LakeShore336 is not connected, use the connect() method."
                raise LakeShore336Error(msg)

    def trans(self, command: str) -> Optional[str]:
        """Sends a single command to the device and blocks until a response is received.

        This operation is seen as a transaction or query.

        Args:
            command (str): Command to send to the controller

        Returns: Either a string returned by the controller (on success) or an error message (on failure).

        Raises:
            LakeShore336Error when there was an I/O problem during communication with the controller, or when there
            was a timeout in either sending the command or receiving the response.
        """

        try:
            self._socket.sendall(command.encode())

            # wait for, read and return the response from HUBER (will be at most TBD chars)

            return_string = self.read()

            return return_string.decode().replace("\r\n", "").replace("+", "")

        except socket.timeout as e_timeout:
            raise LakeShore336Error(self.device_id, "Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as an I/O error
            raise LakeShore336Error(self.device_id, "Socket communication error.") from e_socket
        except ConnectionError as exc:
            raise LakeShore336Error(self.device_id, "Connection error.") from exc
        except AttributeError:
            if not self._is_connection_open:
                raise LakeShore336Error(self.device_id, "Device not connected, use the connect() method.")

    def read(self) -> bytes:
        """Reads the device buffer.

        Returns: Content of the device buffer.
        """

        n_total = 0
        buf_size = 2048

        try:
            for idx in range(100):
                time.sleep(0.05)  # Give the device time to fill the buffer
                data = self._socket.recv(buf_size)
                n = len(data)
                n_total += n
                if n < buf_size:
                    break
            return data
        except socket.timeout as e_timeout:
            logger.warning(f"Socket timeout error from {e_timeout}")
            return b"\r\n"
