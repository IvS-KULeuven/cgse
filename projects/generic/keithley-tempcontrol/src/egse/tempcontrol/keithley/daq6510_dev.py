__all__ = [
    "DAQ6510",
    "DAQ6510Command",
]
import socket
import time

from egse.command import ClientServerCommand
from egse.device import DeviceConnectionError, DeviceError, DeviceTimeoutError
from egse.log import logger
from egse.env import bool_env
from egse.settings import Settings
from egse.socketdevice import SocketDevice

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")

IDENTIFICATION_QUERY = "*IDN?"

dev_settings = Settings.load("Keithley DAQ6510")

DEVICE_NAME = dev_settings.get("DEVICE_NAME", "DAQ6510")
DEV_HOST = dev_settings.get("HOSTNAME", "localhost")
DEV_PORT = dev_settings.get("PORT", 5025)
READ_TIMEOUT = dev_settings.get("TIMEOUT")  # [s], can be smaller than timeout (for DAQ6510Proxy) (e.g. 1s)

SEPARATOR = b"\n"
SEPARATOR_STR = SEPARATOR.decode()


class DAQ6510Command(ClientServerCommand):
    def get_cmd_string(self, *args, **kwargs) -> str:
        """Constructs the command string, based on the given positional and/or keyword arguments.

        Args:
            *args: Positional arguments that are needed to construct the command string
            **kwargs: Keyword arguments that are needed to construct the command string

        Returns: Command string with the given positional and/or keyword arguments filled out.
        """

        out = super().get_cmd_string(*args, **kwargs)
        return out + SEPARATOR_STR


class DAQ6510(SocketDevice):
    """Defines the low-level interface to the Keithley DAQ6510 Controller."""

    def __init__(self, hostname: str = DEV_HOST, port: int = DEV_PORT):
        """Initialization of an Ethernet interface for the DAQ6510.

        Args:
            hostname(str): Hostname to which to open a socket
            port (int): Port to which to open a socket
        """

        super().__init__(hostname, port, separator=SEPARATOR, read_timeout=READ_TIMEOUT)

    @property
    def device_name(self) -> str:
        return DEVICE_NAME

    def initialize(
        self, commands: list[tuple[str, bool]] | None = None, reset_device: bool = False
    ) -> list[str | None]:
        """Initialize the device with optional reset and command sequence.

        Performs device initialization by optionally resetting the device and then
        executing a sequence of commands. Each command can optionally expect a
        response that will be logged for debugging purposes.

        Args:
           commands: List of tuples containing (command_string, expects_response).
               Each tuple specifies a command to send and whether to wait for and
               log the response. Defaults to None (no commands executed).
           reset_device: Whether to send a reset command (*RST) before executing
               the command sequence. Defaults to False.

        Returns:
           Response for each of the commands, or None when no response was expected.

        Raises:
           Any exceptions raised by the underlying write() or trans() methods,
           typically communication errors or device timeouts.

        Example:
            responses = device.initialize(
                [
                    ("*IDN?", True),           # Query device ID, expect response
                    ("SYST:ERR?", True),       # Check for errors, expect response
                    ("OUTP ON", False)         # Enable output, no response expected
                ],
                reset_device=True
            )
        """

        commands = commands or []
        responses = []

        if reset_device:
            logger.info(f"Resetting the {self.device_name}...")
            self.write("*RST")  # this also resets the user-defined buffer

        for cmd, expects_response in commands:
            if expects_response:
                logger.debug(f"Sending {cmd}...")
                response = self.trans(cmd).decode().strip()
                logger.debug(f"{response = }")
            else:
                logger.debug(f"Sending {cmd}...")
                self.write(cmd)

        return responses

    # FIXME: this device interface might be connecting to a simulator instead of a real device!
    def is_simulator(self) -> bool:
        return False

    def is_connected(self) -> bool:
        """Checks if the device is connected.

        This will send a query for the device identification and validate the answer.

        Returns:
            True is the device is connected and answered with the proper ID; False otherwise.
        """

        if not self.is_connection_open:
            return False

        try:
            version = self.query(IDENTIFICATION_QUERY).decode().strip()
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

        if VERBOSE_DEBUG:
            logger.debug(f"{self.device_name} connection check successful, version: {version}")

        return True


def main():
    return 0


if __name__ == "__main__":
    main()
