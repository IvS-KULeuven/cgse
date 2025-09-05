import logging
from pathlib import Path

from egse.ariel.tcu.tcu import TcuController, TcuSimulator, TcuInterface
from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.metrics import define_metrics
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

_HERE = Path(__file__).parent
DEVICE_SETTINGS = Settings.load(filename="tcu.yaml", location=_HERE)
logger = logging.getLogger("egse.ariel.tcu")


class TcuCommand(ClientServerCommand):
    """Command class for the Ariel TCU Control Server."""

    pass


class TcuProtocol(CommandProtocol):
    """Command protocol for the Ariel TCU Control Server."""

    def __init__(self, control_server: ControlServer, simulator: bool = False):
        """Initialisation of an Ariel TCU protocol.

        Args:
            control_server (ControlServer): Ariel TCU Control Server.
            simulator (bool): Whether to use a simulator as the backend.
        """

        super().__init__(control_server)

        self.simulator = simulator

        if self.simulator:
            self.tcu = TcuSimulator()
        else:
            self.tcu = TcuController()

        try:
            self.tcu.connect()
        except ConnectionError:
            logger.warning("Couldn't establish connection to the Ariel TCU, check the log messages.")

        self.load_commands(DEVICE_SETTINGS.Commands, TcuCommand, TcuInterface)
        self.build_device_method_lookup_table(self.tcu)

        self.metrics = define_metrics("TCU")

    def get_bind_address(self) -> str:
        """Returns the bind address for the Ariel TCU Control Server.

        Returns:
            Bind address for the Ariel TCU Control Server.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_device_interface(self) -> TcuInterface:
        """Returns the Ariel TCU interface.

        Returns:
            Ariel TCU interface.
        """
        return self.tcu

    def get_status(self) -> dict:
        """Returns the status information for the Ariel TCU Control Server.

        Returns:
            Status information for the Ariel TCU Control Server.
        """

        status = super().get_status()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return status

        # TODO Add device-specific status information

        return status

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping information for the Ariel TCU Control Server.

        Returns:
            Housekeeping information for the Ariel TCU Control Server.
        """

        result = dict()
        result["timestamp"] = format_datetime()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return result

        # TODO Add HK

        return result

    def is_device_connected(self) -> bool:
        """Checks whether the Ariel TCU is connected.

        Returns:
            True if the Ariel TCU is connected; False otherwise.
        """

        return self.tcu.is_connected()
