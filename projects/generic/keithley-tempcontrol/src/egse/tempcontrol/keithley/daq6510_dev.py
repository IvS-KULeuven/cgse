import logging
import socket
import time

from egse.command import ClientServerCommand
from egse.device import DeviceConnectionError
from egse.device import DeviceConnectionInterface
from egse.device import DeviceError
from egse.device import DeviceTimeoutError
from egse.device import DeviceTransport
from egse.settings import Settings
from egse.system import Timer

logger = logging.getLogger(__name__)

IDENTIFICATION_QUERY = "*IDN?"

DEVICE_SETTINGS = Settings.load("Keithley DAQ6510")
DEVICE_NAME = "DAQ6510"
READ_TIMEOUT = DEVICE_SETTINGS.TIMEOUT  # [s], can be smaller than timeout (for DAQ6510Proxy) (e.g. 1s)


class DAQ6510Command(ClientServerCommand):
    def get_cmd_string(self, *args, **kwargs) -> str:
        """Constructs the command string, based on the given positional and/or keyword arguments.

        Args:
            *args: Positional arguments that are needed to construct the command string
            **kwargs: Keyword arguments that are needed to construct the command string

        Returns: Command string with the given positional and/or keyword arguments filled out.
        """

        out = super().get_cmd_string(*args, **kwargs)
        return out + "\n"


class DAQ6510EthernetInterface(DeviceConnectionInterface, DeviceTransport):
    """Defines the low-level interface to the Keithley DAQ6510 Controller."""

    def __init__(self, hostname: str = None, port: int = None):
        """Initialisation of an Ethernet interface for the DAQ6510.

        Args:
            hostname(str): Hostname to which to open a socket
            port (int): Port to which to open a socket
        """

        super().__init__()

        self.hostname = DEVICE_SETTINGS.HOSTNAME if hostname is None else hostname
        self.port = DEVICE_SETTINGS.PORT if port is None else port
        self._sock = None

        self._is_connection_open = False

    def connect(self) -> None:
        """Connects the device.

        Raises:
            DeviceConnectionError: When the connection could not be established. Check the logging messages for more
                                   details.
            DeviceTimeoutError: When the connection timed out.
            ValueError: When hostname or port number are not provided.
        """

        # Sanity checks

        if self._is_connection_open:
            logger.warning(f"{DEVICE_NAME}: trying to connect to an already connected socket.")
            return

        if self.hostname in (None, ""):
            raise ValueError(f"{DEVICE_NAME}: hostname is not initialized.")

        if self.port in (None, 0):
            raise ValueError(f"{DEVICE_NAME}: port number is not initialized.")

        # Create a new socket instance

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # The following lines are to experiment with blocking and timeout, but there is no need.
            # self._sock.setblocking(1)
            # self._sock.settimeout(3)
        except socket.error as e_socket:
            raise DeviceConnectionError(DEVICE_NAME, "Failed to create socket.") from e_socket

        # Attempt to establish a connection to the remote host

        # FIXME: Socket shall be closed on exception?

        # We set a timeout of 3s before connecting and reset to None (=blocking) after the `connect` method has been
        # called. This is because when no device is available, e.g. during testing, the timeout will take about
        # two minutes, which is way too long. It needs to be evaluated if this approach is acceptable and not causing
        # problems during production.

        try:
            logger.debug(f'Connecting a socket to host "{self.hostname}" using port {self.port}')
            self._sock.settimeout(3)
            self._sock.connect((self.hostname, self.port))
            self._sock.settimeout(None)
        except ConnectionRefusedError as exc:
            raise DeviceConnectionError(DEVICE_NAME, f"Connection refused to {self.hostname}:{self.port}.") from exc
        except TimeoutError as exc:
            raise DeviceTimeoutError(DEVICE_NAME, f"Connection to {self.hostname}:{self.port} timed out.") from exc
        except socket.gaierror as exc:
            raise DeviceConnectionError(DEVICE_NAME, f"Socket address info error for {self.hostname}") from exc
        except socket.herror as exc:
            raise DeviceConnectionError(DEVICE_NAME, f"Socket host address error for {self.hostname}") from exc
        except socket.timeout as exc:
            raise DeviceTimeoutError(DEVICE_NAME, f"Socket timeout error for {self.hostname}:{self.port}") from exc
        except OSError as exc:
            raise DeviceConnectionError(DEVICE_NAME, f"OSError caught ({exc}).") from exc

        self._is_connection_open = True

        # Check that we are connected to the controller by issuing the "VERSION" or
        # "*ISDN?" query. If we don't get the right response, then disconnect automatically.

        if not self.is_connected():
            raise DeviceConnectionError(DEVICE_NAME, "Device is not connected, check logging messages for the cause.")

    def disconnect(self) -> None:
        """Disconnects from the Ethernet connection.

        Raises:
            DeviceConnectionError when the socket could not be closed.
        """

        try:
            if self._is_connection_open:
                logger.debug(f"Disconnecting from {self.hostname}")
                self._sock.close()
                self._is_connection_open = False
        except Exception as e_exc:
            raise DeviceConnectionError(DEVICE_NAME, f"Could not close socket to {self.hostname}") from e_exc

    def reconnect(self):
        """Reconnects to the device controller.

        Raises:
            ConnectionError when the device cannot be reconnected for some reason.
        """

        if self._is_connection_open:
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """Checks if the device is connected.

        This will send a query for the device identification and validate the answer.

        Returns: True is the device is connected and answered with the proper ID; False otherwise.
        """

        if not self._is_connection_open:
            return False

        try:
            version = self.query(IDENTIFICATION_QUERY)
        except DeviceError as exc:
            logger.exception(exc)
            logger.error("Most probably the client connection was closed. Disconnecting...")
            self.disconnect()
            return False

        if "DAQ6510" not in version:
            logger.error(
                f'Device did not respond correctly to a "VERSION" command, response={version}. Disconnecting...'
            )
            self.disconnect()
            return False

        return True

    def write(self, command: str) -> None:
        """Senda a single command to the device controller without waiting for a response.

        Args:
            command (str): Command to send to the controller

        Raises:
            DeviceConnectionError when the command could not be sent due to a communication problem.
            DeviceTimeoutError when the command could not be sent due to a timeout.
        """

        try:
            command += "\n" if not command.endswith("\n") else ""

            self._sock.sendall(command.encode())

        except socket.timeout as e_timeout:
            raise DeviceTimeoutError(DEVICE_NAME, "Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as a connection error
            raise DeviceConnectionError(DEVICE_NAME, "Socket communication error.") from e_socket
        except AttributeError:
            if not self._is_connection_open:
                msg = "The DAQ6510 is not connected, use the connect() method."
                raise DeviceConnectionError(DEVICE_NAME, msg)
            raise

    def trans(self, command: str) -> str:
        """Sends a single command to the device controller and block until a response from the controller.

        This is seen as a transaction.

        Args:
            command (str): Command to send to the controller

        Returns:
            Either a string returned by the controller (on success), or an error message (on failure).

        Raises:
            DeviceConnectionError when there was an I/O problem during communication with the controller.
            DeviceTimeoutError when there was a timeout in either sending the command or receiving the response.
        """

        try:
            # Attempt to send the complete command

            command += "\n" if not command.endswith("\n") else ""

            self._sock.sendall(command.encode())

            # wait for, read and return the response from HUBER (will be at most TBD chars)

            return_string = self.read()

            return return_string.decode().rstrip()

        except socket.timeout as e_timeout:
            raise DeviceTimeoutError(DEVICE_NAME, "Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as an I/O error
            raise DeviceConnectionError(DEVICE_NAME, "Socket communication error.") from e_socket
        except ConnectionError as exc:
            raise DeviceConnectionError(DEVICE_NAME, "Connection error.") from exc
        except AttributeError:
            if not self._is_connection_open:
                raise DeviceConnectionError(DEVICE_NAME, "Device not connected, use the connect() method.")
            raise

    def read(self) -> bytes:
        """Reads from the device buffer.

        Returns: Content of the device buffer.
        """

        n_total = 0
        buf_size = 2048

        # Set a timeout of READ_TIMEOUT to the socket.recv

        saved_timeout = self._sock.gettimeout()
        self._sock.settimeout(READ_TIMEOUT)

        try:
            for idx in range(100):
                time.sleep(0.001)  # Give the device time to fill the buffer
                data = self._sock.recv(buf_size)
                n = len(data)
                n_total += n
                if n < buf_size:
                    break
        except socket.timeout:
            logger.warning(f"Socket timeout error for {self.hostname}:{self.port}")
            return b"\r\n"
        except TimeoutError as exc:
            logger.warning(f"Socket timeout error: {exc}")
            return b"\r\n"
        finally:
            self._sock.settimeout(saved_timeout)

        # logger.debug(f"Total number of bytes received is {n_total}, idx={idx}")

        return data


def main():
    return 0


if __name__ == "__main__":
    main()
