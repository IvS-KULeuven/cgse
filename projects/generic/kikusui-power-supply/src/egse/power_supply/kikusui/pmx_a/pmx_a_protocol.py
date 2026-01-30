"""Command protocol for the KIKUSUI PMX-A."""

import logging
from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.hk import read_conversion_dict, convert_hk_names
from egse.power_supply.kikusui.pmx_a.pmx_a import PmxAInterface
from egse.power_supply.kikusui.pmx_a.pmx_a import PmxASimulator, PmxAController
from egse.power_supply.kikusui.pmx_a.pmx_a_cs import PmxAControlServer
from egse.protocol import DynamicCommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

_HERE = Path(__file__).parent
DEVICE_SETTINGS = Settings.load(filename="pmx_a.yaml", location=_HERE)
LOGGER = logging.getLogger("egse.power_supply.kikusui.pmx_a.pmx_a")


class PmxACommand(ClientServerCommand):
    """Command class for the KIKUSUI PMX-A Control Server."""

    pass


class PmxAProtocol(DynamicCommandProtocol):
    """Command protocol for the KIKUSUI PMX-A Control Server."""

    def __init__(self, control_server: PmxAControlServer, device_id: str, simulator: bool = False):
        """Initialisation of a KIKUSUI PMX-A protocol.

        Args:
            control_server (ControlServer): KIKUSUI PMX-A Control Server.
            device_id (str): Device identifier, as per (local) settings and setup.
            simulator (bool): Whether to use a simulator as the backend.
        """

        super().__init__(control_server)

        self.hk_conversion_table = read_conversion_dict(
            self.get_control_server().get_storage_mnemonic(), use_site=False
        )

        self.simulator = simulator

        if self.simulator:
            self.pmx_a: PmxAInterface = PmxASimulator(device_id)
        else:
            self.pmx_a: PmxAInterface = PmxAController(device_id)

        try:
            self.pmx_a.connect()
        except ConnectionError:
            LOGGER.warning("Couldn't establish connection to the KIKUSUI PMX-A, check the log messages.")

    def get_bind_address(self) -> str:
        """Returns the bind address for the PmxA Control Server.

        Returns:
            Bind address for the PmxA Control Server.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_device(self) -> PmxAInterface:
        """Returns the KIKUSUI PMX-A interface.

        Returns:
            KIKUSUI PMX-A interface.
        """

        return self.pmx_a

    def get_status(self) -> dict:
        """Returns the status information for the PmxA Control Server.

        Returns:
            Status information for the PmxA Control Server.
        """

        status = super().get_status()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return status

        # TODO Add device-specific status information

        return status

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping information for the KIKUSUI PMX-A Control Server.

        Returns:
            Housekeeping information for the KIKUSUI PMX-A Control Server.
        """

        result = dict()
        result["timestamp"] = format_datetime()

        # result["CURRENT"] = self.pmx_a.get_current()  # Current [A]
        # result["VOLTAGE"] = self.pmx_a.get_voltage()  # Voltage [V]
        #
        # if self.hk_conversion_table:
        #     return convert_hk_names(result, self.hk_conversion_table)
        return result

    def is_device_connected(self) -> bool:
        """Checks whether the KIKUSUI PMX-A is connected.

        Returns:
            True if the KIKUSUI PMX-A is connected; False otherwise.
        """

        return self.pmx_a.is_connected()
