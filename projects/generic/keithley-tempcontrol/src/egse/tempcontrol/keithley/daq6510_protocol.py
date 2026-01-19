import logging
from pathlib import Path

from egse.control import ControlServer
from egse.device import DeviceTimeoutError
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.setup import load_setup
from egse.system import format_datetime
from egse.tempcontrol.keithley.daq6510 import DAQ6510Controller
from egse.tempcontrol.keithley.daq6510 import DAQ6510Interface
from egse.tempcontrol.keithley.daq6510_dev import DAQ6510Command
from egse.zmq_ser import bind_address

HERE = Path(__file__).parent

COMMAND_SETTINGS = Settings.load(location=HERE, filename="daq6510.yaml")

MODULE_LOGGER = logging.getLogger(__name__)


class DAQ6510Protocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        """Initialisation of a new Protocol for DAQ6510 Management.

        Args:
            control_server: Control Server for which to send out status and monitoring information
        """

        super().__init__(control_server)

        self.daq = DAQ6510Controller()

        try:
            self.daq.connect()
        except (ConnectionError, DeviceTimeoutError):
            MODULE_LOGGER.warning("Couldn't establish a connection to the DAQ6510, check the log messages.")

        self.load_commands(COMMAND_SETTINGS.Commands, DAQ6510Command, DAQ6510Interface)
        self.build_device_method_lookup_table(self.daq)

        setup = load_setup()
        self.channels = setup.gse.DAQ6510.channels

    def get_bind_address(self) -> str:
        """
        Returns a string with the bind address, the endpoint, for accepting connections and bind a socket to.

        Returns:
            String with the protocol and port to bind a socket to.
        """

        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_status(self) -> dict:
        """
        Returns a dictionary with status information for the Control Server and the DAQ6510.

        Returns:
            Dictionary with status information for the Control Server and the DAQ6510.
        """

        return super().get_status()

    def get_housekeeping(self) -> dict:
        """
        Returns a dictionary with housekeeping information about the DAQ6510.

        Returns:
            Dictionary with housekeeping information about the DAQ6510.
        """

        hk_dict = dict()
        hk_dict["timestamp"] = format_datetime()

        return hk_dict

    def quit(self) -> None:
        """Clean up and stop threads that were started by the process."""

        # TODO
        # self.synoptics.disconnect_cs()

        pass
