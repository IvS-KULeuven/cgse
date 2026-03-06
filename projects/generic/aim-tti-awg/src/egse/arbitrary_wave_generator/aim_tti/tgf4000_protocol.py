"""Command protocol for the Aim-TTi TGF4000."""

import logging
from pathlib import Path

from egse.arbitrary_wave_generator.aim_tti.tgf4000 import Tgf4000Interface, Tgf4000Simulator, Tgf4000Controller
from egse.arbitrary_wave_generator.aim_tti.tgf4000_cs import Tgf4000ControlServer
from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.hk import read_conversion_dict, convert_hk_names
from egse.protocol import DynamicCommandProtocol
from egse.settings import Settings
from egse.setup import SetupError
from egse.system import format_datetime
from egse.zmq_ser import bind_address

_HERE = Path(__file__).parent
DEVICE_SETTINGS = Settings.load(filename="tgf4000.yaml", location=_HERE)
LOGGER = logging.getLogger("egse.arbitrary_wave_generator.aim_tti.tgf4000")


class Tgf4000Command(ClientServerCommand):
    """Command class for the Aim-TTi TGF4000 Control Server."""

    pass


class Tgf4000Protocol(DynamicCommandProtocol):
    """Command protocol for the Aim-TTi TGF4000 Control Server."""

    def __init__(self, control_server: Tgf4000ControlServer, device_id: str, simulator: bool = False):
        """Initialisation of a Aim-TTi TGF4000 protocol.

        Args:
            control_server (ControlServer): Aim-TTi TGF4000 Control Server.
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
            self.tgf4000: Tgf4000Interface = Tgf4000Simulator(device_id)
        else:
            self.tgf4000: Tgf4000Interface = Tgf4000Controller(device_id)

        try:
            self.tgf4000.connect()
        except ConnectionError:
            LOGGER.warning("Couldn't establish connection to the Aim-TTi TGF4000, check the log messages.")

    def get_bind_address(self) -> str:
        """Returns the bind address for the Aim-TTi TGF400 Control Server.

        Returns:
            Bind address for the Aim-TTi TGF400 Control Server.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_device(self) -> Tgf4000Interface:
        """Returns the Aim-TTi TGF400 interface.

        Returns:
            Aim-TTi TGF400 interface.
        """

        return self.tgf4000

    def get_status(self) -> dict:
        """Returns the status information for the Aim-TTi TGF400 Control Server.

        Returns:
            Status information for the Aim-TTi TGF400 Control Server.
        """

        status = super().get_status()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return status

        # TODO Add device-specific status information

        return status

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping information for the Aim-TTi TGF400 Control Server.

        Returns:
            Housekeeping information for the Aim-TTi TGF400 Control Server.
        """

        result = dict()
        result["timestamp"] = format_datetime()

        # TODO

        if self.hk_conversion_table:
            return convert_hk_names(result, self.hk_conversion_table)
        return result

    def is_device_connected(self) -> bool:
        """Checks whether the Aim-TTi TGF400 is connected.

        Returns:
            True if the Aim-TTi TGF400 is connected; False otherwise.
        """

        return self.tgf4000.is_connected()
