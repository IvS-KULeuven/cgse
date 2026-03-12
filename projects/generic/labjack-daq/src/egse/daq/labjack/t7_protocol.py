"""Command protocol for the LabJack T7."""

import logging
from pathlib import Path

from egse.arbitrary_wave_generator.aim_tti.tgf4000 import Tgf4000Interface, Tgf4000Simulator, Tgf4000Controller
from egse.arbitrary_wave_generator.aim_tti.tgf4000_cs import Tgf4000ControlServer
from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.daq.labjack.t7 import T7Interface, T7Simulator, T7Controller
from egse.device import DeviceConnectionState
from egse.hk import read_conversion_dict, convert_hk_names
from egse.protocol import DynamicCommandProtocol
from egse.settings import Settings
from egse.setup import SetupError
from egse.system import format_datetime
from egse.zmq_ser import bind_address

_HERE = Path(__file__).parent
DEVICE_SETTINGS = Settings.load(filename="t7.yaml", location=_HERE)
LOGGER = logging.getLogger("egse.daq.labjack.t7")


class T7Command(ClientServerCommand):
    """Command class for the LabJack T7 Control Server."""

    pass


class T7Protocol(DynamicCommandProtocol):
    """Command protocol for the LabJack T7 Control Server."""

    def __init__(self, control_server: T7ControlServer, device_id: str, simulator: bool = False):
        """Initialisation of a LabJack T7 protocol.

        Args:
            control_server (ControlServer): LabJack T7 Control Server.
            device_id (str): Device identifier, as per (local) settings and setup.
            simulator (bool): Whether to use a simulator as the backend.
        """

        super().__init__(control_server)

        try:
            self.hk_conversion_table = read_conversion_dict(
                self.get_control_server().get_storage_mnemonic(), use_site=False
            )
        except SetupError:
            self.hk_conversion_table = None

        self.simulator = simulator

        if self.simulator:
            self.t7: T7Interface = T7Simulator(device_id)
        else:
            self.t7: T7Interface = T7Controller(device_id)

        try:
            self.t7.connect()
        except ConnectionError:
            LOGGER.warning("Couldn't establish connection to the LabJack T7, check the log messages.")

    def get_bind_address(self) -> str:
        """Returns the bind address for the LabJack T7 Control Server.

        Returns:
            Bind address for the LabJack T7 Control Server.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_device(self) -> T7Interface:
        """Returns the LabJack T7 interface.

        Returns:
            LabJack T7 interface.
        """

        return self.t7

    def get_status(self) -> dict:
        """Returns the status information for the LabJack T7 Control Server.

        Returns:
            Status information for the LabJack T7 Control Server.
        """

        status = super().get_status()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return status

        # TODO Add device-specific status information

        return status

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping information for the LabJack T7 Control Server.

        Returns:
            Housekeeping information for the LabJack T7 Control Server.
        """

        result = dict()
        result["timestamp"] = format_datetime()

        # TODO

        if self.hk_conversion_table:
            return convert_hk_names(result, self.hk_conversion_table)
        return result

    def is_device_connected(self) -> bool:
        """Checks whether the LabJack T7 is connected.

        Returns:
            True if the LabJack T7 is connected; False otherwise.
        """

        return self.t7.is_connected()
