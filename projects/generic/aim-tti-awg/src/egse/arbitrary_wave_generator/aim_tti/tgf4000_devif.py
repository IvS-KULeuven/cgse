import logging

from egse.arbitrary_wave_generator.aim_tti import DEVICE_SETTINGS

LOGGER = logging.getLogger(__name__)

IDENTIFICATION_QUERY = "*IDN?"


import logging
import socket
import time
from string import digits


from egse.device import (
    DeviceConnectionError,
    DeviceTimeoutError,
    DeviceError,
    DeviceConnectionInterface,
    DeviceTransport,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 3.0  # Timeout when connecting the socket [s]

remove_digits = str.maketrans("", "", digits)
time_in_s = time.time()


class TgfError(Exception):
    """A TGF-specific error."""

    pass


class Tgf4000EthernetInterface(DeviceConnectionInterface, DeviceTransport):
    """Ethernet Interface for the TGF devices."""

    def __init__(self, hostname: str = None, port: int = None, device_id: str = None, read_timeout: float = 60):
        """Initialisation of an Ethernet interface for a TGF device.

        Args:
            hostname( str): Hostname to which to open a socket.
            port (int): Port to which to open a socket.
            device_id (str): Identifier of the device to which to open a socket.
            read_timeout (float): Timeout for reading commands [s].
        """

        super().__init__()

        print(f"Device ID: {device_id}")

        self.hostname = DEVICE_SETTINGS[device_id]["HOSTNAME"] if hostname is None else hostname
        self.port = DEVICE_SETTINGS[device_id]["PORT"] if port is None else port
        self.device_id = device_id
        self._sock = None

        print(f"Hostname: {self.hostname}")
        print(f"Port: {self.port}")
        print(f"Device ID: {self.device_id}")

        self._is_connection_open = False
        self.read_timeout = read_timeout

    def connect(self) -> None:
        """Connects to the Aim-TTi TGF4000 hardware.

        Raises:
            DeviceConnectionError: When the connection could not be established. Check the logging messages for more
                                   details.
            DeviceTimeoutError: When the connection timed out.
            ValueError: When hostname or port number are not provided.
        """

        # Sanity checks

        if self._is_connection_open:
            logger.warning(f"{self.device_id}: trying to connect to an already connected socket.")
            return

        if self.hostname in (None, ""):
            raise ValueError(f"{self.device_id}: hostname is not initialised.")

        if self.port in (None, 0):
            raise ValueError(f"{self.device_id}: port number is not initialised.")

        # Create a new socket instance

        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # The following lines are to experiment with blocking and timeout, but there is no need.
            # self._sock.setblocking(1)
            # self._sock.settimeout(3)
        except socket.error as e_socket:
            raise DeviceConnectionError(self.device_id, "Failed to create socket.") from e_socket

        print(f"Socket created: {self._sock}")

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
            raise DeviceConnectionError(self.device_id, f"Connection refused to {self.hostname}:{self.port}.") from exc
        except TimeoutError as exc:
            raise DeviceTimeoutError(self.device_id, f"Connection to {self.hostname}:{self.port} timed out.") from exc
        except socket.gaierror as exc:
            raise DeviceConnectionError(self.device_id, f"Socket address info error for {self.hostname}") from exc
        except socket.herror as exc:
            raise DeviceConnectionError(self.device_id, f"Socket host address error for {self.hostname}") from exc
        except OSError as exc:
            raise DeviceConnectionError(self.device_id, f"OSError caught ({exc}).") from exc

        self._is_connection_open = True

        # Check that we are connected to the controller by issuing the "VERSION" or
        # "*IDN?" query. If we don't get the right response, then disconnect automatically.

        if not self.is_connected():
            raise DeviceConnectionError(
                self.device_id, "Device is not connected, check logging messages for the cause."
            )

    def disconnect(self) -> None:
        """Disconnects from the Aim-TTi TGF4000 hardware.

        Raises:
            DeviceConnectionError when the socket could not be closed.
        """

        try:
            if self._is_connection_open:
                logger.debug(f"Disconnecting from {self.hostname}")
                self._sock.close()
                self._is_connection_open = False
        except Exception as e_exc:
            raise DeviceConnectionError(self.device_id, f"Could not close socket to {self.hostname}") from e_exc

    def reconnect(self):
        """Reconnects to the Aim-TTi TGF4000 hardware.

        Raises:
            ConnectionError when the device cannot be reconnected for some reason.
        """

        if self._is_connection_open:
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """Checks if the Aim-TTi TGF4000 hardware is connected.

        This will send a query for the device identification and validate the answer.

        Returns: True is the device is connected and answered with the proper ID; False otherwise.
        """

        if not self._is_connection_open:
            return False

        try:
            print(f"Result from identification query: {self.query(IDENTIFICATION_QUERY)}")
            # noinspection PyTypeChecker
            manufacturer, model, *_ = self.query(IDENTIFICATION_QUERY).split(",")

        except DeviceError as exc:
            logger.exception(exc)
            logger.error("Most probably the client connection was closed. Disconnecting...")
            self.disconnect()
            return False

        print(f"Manufacturer: {manufacturer}")

        if "THURLBY THANDAR" not in manufacturer or "TGF4" not in model:
            logger.error(
                f"Device did not respond correctly to a {IDENTIFICATION_QUERY} command, manufacturer={manufacturer}, "
                f"model={model}. Disconnecting..."
            )
            self.disconnect()
            return False

        return True

    def write(self, command: str) -> None:
        """Sends a single command to the device controller without waiting for a response.

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
            raise DeviceTimeoutError(self.device_id, "Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as a connection error
            raise DeviceConnectionError(self.device_id, "Socket communication error.") from e_socket
        except AttributeError:
            if not self._is_connection_open:
                msg = "The TGF4000 is not connected, use the connect() method."
                raise DeviceConnectionError(self.device_id, msg)
            raise

    def trans(self, command: str) -> str | bytes:
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

            # wait for, read and return the response from Aim-TTi TGF4000 (will be at most TBD chars)

            return_string = self.read()

            return return_string.decode().rstrip()

        except UnicodeError:
            # noinspection PyUnboundLocalVariable
            return return_string
        except socket.timeout as e_timeout:
            raise DeviceTimeoutError(self.device_id, "Socket timeout error") from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as an I/O error
            raise DeviceConnectionError(self.device_id, "Socket communication error.") from e_socket
        except ConnectionError as exc:
            raise DeviceConnectionError(self.device_id, "Connection error.") from exc
        except AttributeError:
            if not self._is_connection_open:
                raise DeviceConnectionError(self.device_id, "Device not connected, use the connect() method.")
            raise

    def read(self) -> bytes:
        """Reads from the device buffer.

        Returns: Content of the device buffer.
        """

        n_total = 0
        buf_size = 2048

        # Set a timeout of READ_TIMEOUT to the socket.recv

        saved_timeout = self._sock.gettimeout()
        self._sock.settimeout(self.read_timeout)

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

        # noinspection PyUnboundLocalVariable
        return data


def main():
    return 0


if __name__ == "__main__":
    main()
