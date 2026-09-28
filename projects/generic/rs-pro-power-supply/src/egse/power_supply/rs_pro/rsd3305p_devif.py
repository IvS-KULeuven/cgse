import logging
import time
from serial import SerialException

from serial.tools import list_ports

from egse.power_supply.rs_pro import (
    DEVICE_SETTINGS,
    IDENTIFICATION_QUERY,
    ENCODING,
    LINE_ENDING,
    split_result_on_blanks,
)
import serial


from egse.device import (
    DeviceConnectionInterface,
    DeviceTransport,
)

LOGGER = logging.getLogger(__name__)


class RsdError(Exception):
    """An RS-D3305P-specific error."""

    pass


def print_serial_ports() -> str | None:
    """Prints a list of all available serial ports."""

    ports = list_ports.comports()

    for port in ports:
        print(port.name, port.serial_number)


class Rsd3305pUsbInterface(DeviceConnectionInterface, DeviceTransport):
    def __init__(self, device_id: str):
        """Initialisation of a serial interface to the TCU Arduino.

        Args:
            device_id (str): Identifier of the device to which to open a serial port.
        """

        super().__init__()

        self.device_id = device_id
        self.serial_number = DEVICE_SETTINGS[device_id]["SERIAL_NUMBER"]

        ports = list_ports.comports()

        self.port = None

        for port in ports:
            if port.serial_number == self.serial_number:
                self.port = f"/dev/{port.name}"
                break

        if not self.port:
            raise RsdError(f"{self.device_id}: Serial port not found.")

        self.psu = serial.Serial(
            port=self.port,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        time.sleep(0.05)
        self.psu.reset_input_buffer()

    def connect(self) -> None:
        """Connects to the RS-PRO RS-D3305P hardware.

        Raises:
            RsdError when a connection could not be established.
        """

        try:
            self.psu.open()
        except SerialException:
            pass
        except Exception as e_exc:
            raise RsdError(f"{self.device_id}: Failed to open serial port.") from e_exc

    def disconnect(self) -> None:
        """Disconnects from the RS-PRO RS-D3305P hardware.

        Raises:
            RsdError when the connection could not be closed.
        """

        try:
            self.psu.close()
        except Exception as e_exc:
            raise RsdError(f"{self.device_id}: Failed to close serial port.") from e_exc

    def reconnect(self) -> None:
        """Reconnects to the RS-PRO RS-D3305P hardware.

        Raises:
            RsdError when the device cannot be reconnected for some reason.
        """

        if self.is_connected():
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """Checks if the RS-PRO RS-D3305P hardware is connected.

        This will send a query for the device identification and validate the answer.

        Returns: True is the device is connected and answered with the proper ID; False otherwise.
        """

        if not self.psu.is_open:
            return False

        try:
            # noinspection PyTypeChecker
            model, *_ = split_result_on_blanks(self.query(IDENTIFICATION_QUERY))

        except RsdError as exc:
            LOGGER.exception(exc)
            LOGGER.error("Most probably the client connection was closed. Disconnecting...")
            self.disconnect()
            return False

        if "RS-D3305P" not in model:
            LOGGER.error(
                f"Device did not respond correctly to a {IDENTIFICATION_QUERY} command, model={model}. Disconnecting..."
            )
            self.disconnect()
            return False

        return True

    def write(self, command: str) -> None:
        """Sends a single command to the device controller without waiting for a response.

        Args:
            command (str): Command to send to the controller.
        """

        self.psu.write(_cmd_bytes(command))
        self.psu.flush()

    def trans(self, command: str, max_bytes: int = 256) -> bytes:
        """Sends a single command to the device controller and block until a response from the controller.

        This is seen as a transaction.

        Args:
            command (str): Command to send to the controller.
            max_bytes (int, optional): Maximum number of bytes to send. Defaults to 256.

        Returns:
            Bytestring returned by the controller.

        Raises:
            TimeoutError when no data were received from the controller.
        """

        self.psu.reset_input_buffer()
        self.psu.write(_cmd_bytes(command))
        self.psu.flush()

        data = self.psu.read_until(expected=b"\n", size=max_bytes)

        if not data:
            data = self.psu.read(max_bytes)

        if not data:
            raise TimeoutError(f"No response from {self.device_id} for command {command}")

        return data

        # text = data.decode(ENCODING, errors="ignore").strip("\r\n\x00 ")

    def read(self):

        raise NotImplementedError


def _cmd_bytes(command: str) -> bytes:
    """Converts the given command to bytes.

    Args:
        command (str): String representing the command to send to the controller.

    Returns:
        Command to send to the controller.
    """
    return command.strip().encode(ENCODING, errors="ignore") + LINE_ENDING.encode(ENCODING)


def main():
    return 0


if __name__ == "__main__":
    main()
