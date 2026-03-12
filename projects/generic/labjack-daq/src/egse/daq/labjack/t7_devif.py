import logging

from labjack import ljm
from labjack.ljm.ljm import LJMError

LOGGER = logging.getLogger(__name__)


import logging

from egse.device import (
    DeviceError,
    DeviceConnectionInterface,
    DeviceTransport,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 3.0  # Timeout when connecting the socket [s]


class T7Error(Exception):
    """A T7-specific error."""

    pass


class T7ConnectionInterface(DeviceConnectionInterface, DeviceTransport):
    def __init__(self, device_id: str, connection_type: int, identifier: str = "ANY"):
        """Initialisation of an interface to interact with a LabJack T7 devices.

        The connection to the device is done either via USB or via Ethernet.

        Args:
            device_id (str): Identifier of the device to which to open a connection.
            connection_type (int): Type of connection to the device: `ljm.constants.ctUSB` for a USB connection,
                                   `ljm.constants.ctETHERNET` for an Ethernet connection.
            identifier (str): Identifier for the device to be connected or "LJM_idANY"/"ANY". This can be a serial
                              number, IP address, or device name. Device names may not contain periods.
        """

        super().__init__()

        self.device_id = device_id
        self.connection_type = connection_type
        self.identifier = identifier

        self._handle = None

    @property
    def handle(self):
        return self._handle

    def connect(self) -> None:
        """Connects to the LabJack T7 device.

        Raises:
            T7Error when the connection could not be closed.
        """

        if self.is_connected():
            raise T7Error("T7 already connected")

        try:
            self._handle = ljm.openS(
                deviceType=ljm.constants.dtT7, connectionType=ljm.constants.ctUSB, identifier=self.identifier
            )
        except LJMError as exc:
            raise T7Error(f"Failed to open connection to T7 device via identifier {self.identifier}") from exc

    def disconnect(self) -> None:
        """Disconnects from the LabJack T7 device.

        Raises:
            T7Error when the connection could not be closed.
        """

        try:
            ljm.close(self.handle)
        except Exception as exc:
            raise T7Error(f"Failed to close connection to T7 device via identifier {self.identifier}") from exc

    def reconnect(self):
        """Reconnects to the LabJack T7 device.

        Raises:
            T7Error when the device cannot be reconnected for some reason.
        """

        if self.is_connected():
            self.disconnect()
        self.connect()

    def is_connected(self) -> bool:
        """Checks if the LabJack T7 device is connected.
        Returns:
            True is the device is connected; False otherwise.
        """

        try:
            ljm.getHandleInfo(self.handle)
            # TODO Maybe you want to check the content of (some parts of) `info` to be sure that you are connected to
            # a LabJack T7 device)?
            device_type, *_ =  ljm.getHandleInfo(self.handle)

            if device_type != ljm.constants.dtT7:
                return False

            return True

        except DeviceError as exc:
            logger.exception(exc)
            logger.error("Most probably the client connection was closed. Disconnecting...")
            self.disconnect()
            return False

    def write(self, command: str) -> None:
        # TODO
        pass

    def trans(self, command: str) -> str | bytes:
        # TODO
        pass

    def read(self) -> bytes:
        # TODO
        pass


class T7UsbInterface(T7ConnectionInterface):
    """USB Interface for the LabJack T7 devices."""

    def __init__(self, device_id: str, identifier: str = "ANY"):
        """Initialisation of a USB interface for a LabJack T7 device.

        Args:
            device_id (str): Identifier of the device to which to open a connection.
            identifier (str): Identifier for the device to be connected or "LJM_idANY"/"ANY". This can be a serial
                              number, IP address, or device name. Device names may not contain periods.
        """

        super().__init__(device_id, ljm.constants.ctUSB, identifier)


class T7EthernetInterface(T7ConnectionInterface):
    """Ethernet interface for LabJack T7 devices."""

    def __init(self, device_id: str, identifier: str = "ANY"):
        """Initialisation of an Ethernet for a LabJack T7 device.

        Args:
            device_id (str): Identifier of the device to which to open a connection.
            identifier (str): Identifier for the device to be connected or "LJM_idANY"/"ANY". This can be a serial
                              number, IP address, or device name. Device names may not contain periods.
        """

        super().__init__(device_id, ljm.constants.ctETHERNET, identifier)


def main():
    return 0


if __name__ == "__main__":
    main()
