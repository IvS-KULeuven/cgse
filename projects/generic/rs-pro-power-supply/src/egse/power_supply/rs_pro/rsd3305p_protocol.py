"""Command protocol for the RS-PRO D3000 power supply."""

import logging
from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.hk import read_conversion_dict, convert_hk_names
from egse.power_supply.rs_pro.rsd3305p import Rsd3305pInterface, Rsd3305pSimulator, Rsd3305pController
from egse.power_supply.rs_pro.rsd3305p_cs import Rsd3305pControlServer
from egse.protocol import DynamicCommandProtocol
from egse.settings import Settings
from egse.setup import SetupError
from egse.system import format_datetime
from egse.zmq_ser import bind_address

_HERE = Path(__file__).parent
DEVICE_SETTINGS = Settings.load(filename="rsd3305p.yaml", location=_HERE)
LOGGER = logging.getLogger("egse.power_supply.rs_pro.rsd3305p")


class Rd3305Command(ClientServerCommand):
    """Command class for the RS-PRO D3305P Control Server."""

    pass


class Rsd3305pProtocol(DynamicCommandProtocol):
    """Command protocol for the RS-PRO D3305P Control Server."""

    def __init__(self, control_server: Rsd3305pControlServer, device_id: str, simulator: bool = False):
        """Initialisation of an RS-PRO D3305P protocol.

        Args:
            control_server (ControlServer): RS-PRO D3305P Control Server.
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
            self.rsd3305p: Rsd3305pInterface = Rsd3305pSimulator(device_id)
        else:
            self.rsd3305p: Rsd3305pInterface = Rsd3305pController(device_id)

        try:
            self.rsd3305p.connect()
        except ConnectionError:
            LOGGER.warning("Couldn't establish connection to the RS-PRO D3305P, check the log messages.")

    def get_bind_address(self) -> str:
        """Returns the bind address for the RS-PRO D3305P Control Server.

        Returns:
            Bind address for the RS-PRO D3305P Control Server.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_device(self) -> Rsd3305pInterface:
        """Returns the RS-PRO D3305P interface.

        Returns:
            RS-PRO D3305P interface.
        """

        return self.rsd3305p

    def get_status(self) -> dict:
        """Returns the status information for the RS-PRO D3305P Control Server.

        Returns:
            Status information for the RS-PRO D3305P Control Server.
        """

        status = super().get_status()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return status

        # TODO Add device-specific status information

        return status

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping information for the RS-PRO D3305P Control Server.

        Returns:
            Housekeeping information for the RS-PRO D3305P Control Server.
        """

        result = dict()
        result["timestamp"] = format_datetime()

        for channel in [1, 2]:
            result[f"CURRENT{channel}"] = self.rsd3305p.get_current(channel=channel)  # Current [A]
            result[f"CURRENT_SETPOINT{channel}"] = self.rsd3305p.get_current_config(
                channel=channel
            )  # Current setpoint [A]
            result[f"VOLTAGE{channel}"] = self.rsd3305p.get_voltage(channel=channel)  # Voltage [V]
            result[f"VOLTAGE_SETPOINT{channel}"] = self.rsd3305p.get_voltage_config(
                channel=channel
            )  # Voltage setpoint [V]

        result |= self.rsd3305p.get_status()

        if self.hk_conversion_table:
            return convert_hk_names(result, self.hk_conversion_table)
        return result

    def is_device_connected(self) -> bool:
        """Checks whether the RS-PRO D3305P is connected.

        Returns:
            True if the RS-PRO D3305P is connected; False otherwise.
        """

        return self.rsd3305p.is_connected()
