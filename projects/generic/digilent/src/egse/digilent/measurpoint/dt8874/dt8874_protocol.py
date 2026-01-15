"""Command protocol for the Digilent MEASURpoint DT8874."""

import logging
from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.protocol import DynamicCommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address
from egse.digilent.measurpoint.dt8874.dt8874 import Dt8874Simulator, Dt8874Interface

_HERE = Path(__file__).parent
DEVICE_SETTINGS = Settings.load(filename="dt8874.yaml", location=_HERE)
LOGGER = logging.getLogger("egse.digilent.measurpoint.dt8874")


class Dt8874Command(ClientServerCommand):
    """Command class for the Digilent MEASURpoint DT8874 Control Server."""

    pass


class Dt8874Protocol(DynamicCommandProtocol):
    """Command protocol for the Digilent MEASURpoint DT8874 Control Server."""

    def __init__(self, control_server: ControlServer, simulator: bool = False):
        """Initialisation of a Digilent MEASURpoint DT8874 protocol.

        Args:
            control_server (ControlServer): Digilent MEASURpoint DT8874 Control Server.
            simulator (bool): Whether to use a simulator as the backend.
        """

        super().__init__(control_server)

        self.simulator = simulator

        if self.simulator:
            self.dt8874 = Dt8874Simulator()
        else:
            self.dt8874 = Dt8874Simulator()

        try:
            self.dt8874.connect()
        except ConnectionError:
            LOGGER.warning("Couldn't establish connection to the Digilent MEASURpoint DT8874, check the log messages.")

        # self.metrics = define_metrics("DT8874")

    def get_bind_address(self) -> str:
        """Returns the bind address for the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Bind address for the Digilent MEASURpoint DT8874 Control Server.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_device(self) -> Dt8874Interface:
        """Returns the Digilent MEASURpoint DT8874 interface.

        Returns:
            Digilent MEASURpoint DT8874 interface.
        """
        return self.dt8874

    def get_status(self) -> dict:
        """Returns the status information for the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Status information for the Digilent MEASURpoint DT8874 Control Server.
        """

        status = super().get_status()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return status

        # TODO Add device-specific status information

        return status

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping information for the Digilent MEASURpoint DT8874 Control Server.

        Returns:
            Housekeeping information for the Digilent MEASURpoint DT8874 Control Server.
        """

        result = dict()
        result["timestamp"] = format_datetime()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return result

        # TODO

        return result

    def is_device_connected(self) -> bool:
        """Checks whether the Digilent MEASURpoint DT8874 is connected.

        Returns:
            True if the Digilent MEASURpoint DT8874 is connected; False otherwise.
        """

        return self.dt8874.is_connected()
