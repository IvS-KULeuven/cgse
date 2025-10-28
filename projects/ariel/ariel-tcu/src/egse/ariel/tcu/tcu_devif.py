import logging
import time

import serial

from egse.device import DeviceConnectionInterface, DeviceTransport
from egse.settings import Settings

logger = logging.getLogger(__name__)
DEVICE_SETTINGS = Settings.load("Ariel TCU Controller")


class TcuError(Exception):
    """Generic TCU error for low-level classes."""

    pass


class TcuDeviceInterface(DeviceConnectionInterface, DeviceTransport):
    """Defines the low-level interface to the Ariel TCU (Arduino)."""

    def __init__(self, port: int = None):
        """Initialisation of a serial interface to the TCU Arduino.

        Args:
            port (int): Serial port to which to connect to the TCU Arduino.
        """

        super().__init__()

        # self.hostname = hostname or DEVICE_SETTINGS["HOSTNAME"]
        self.port = port or DEVICE_SETTINGS["COM_PORT"]

        self.arduino = serial.Serial()
        self.arduino.port = self.port
        self.arduino.baudrate = DEVICE_SETTINGS["BAUD_RATE"]
        self.arduino.bytesize = DEVICE_SETTINGS["NUM_DATA_BITS"]
        self.arduino.parity = DEVICE_SETTINGS["PARITY"]
        self.arduino.stopbits = DEVICE_SETTINGS["NUM_STOP_BITS"]

    def connect(self) -> None:
        """Opens the serial port to the TCU Arduino.

        Raises:
            TcuError: When the serial port could not be opened.
        """

        if self.is_connected():
            raise TcuError("TCU already connected.")
        # if self.hostname in (None, ""):
        #     raise TcuError("TCU hostname is not initialised.")
        if self.port in (None, 0):
            raise TcuError("TCU serial port is not initialised.")

        try:
            self.arduino.open()
        except Exception as exc:
            raise TcuError(f"Failed to open TCU serial port {self.port}") from exc

    def disconnect(self) -> None:
        """Closes the serial port to the TCU Arduino.

        Raises:
            TcuError: When the serial port could not be closed.
        """

        try:
            self.arduino.close()
        except Exception as exc:
            raise TcuError(f"Failed to close TCU serial port {self.port}") from exc

    def reconnect(self) -> None:
        """Re-connect to the Ariel TCU Arduino."""

        if self.is_connected():
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """Checks whether the serial port to the TCU Arduino is open.

        Returns:
            True if the serial port to the TCU Arduino is open; False otherwise.
        """

        return self.arduino.is_open

    def trans(self, command: str) -> bytes:
        """Sends the given command to the TCU Arduino and returns the response.

        This is seen as a transaction.

        Args:
            command: Command string to send to the TCU Arduino.

        Returns:
            Response string from the TCU Arduino.
        """

        self.arduino.write(command.encode("utf-8"))
        time.sleep(0.05)
        return self.arduino.readline()
