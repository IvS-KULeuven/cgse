import logging

from egse.control import ControlServer
from egse.device import DeviceTimeoutError
from egse.hk import read_conversion_dict
from egse.metrics import define_metrics
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.setup import load_setup
from egse.synoptics import SynopticsManagerProxy
from egse.system import format_datetime
from egse.tempcontrol.keithley.daq6510 import DAQ6510Controller
from egse.tempcontrol.keithley.daq6510 import DAQ6510Interface
from egse.tempcontrol.keithley.daq6510 import DAQ6510Simulator
from egse.tempcontrol.keithley.daq6510_devif import DAQ6510Command
from egse.zmq_ser import bind_address

COMMAND_SETTINGS = Settings.load(filename="daq6510.yaml")

MODULE_LOGGER = logging.getLogger(__name__)


class DAQ6510Protocol(CommandProtocol):

    def __init__(self, control_server: ControlServer):
        """ Initialisation of a new Protocol for DAQ6510 Management.

        Args:
            control_server: Control Server for which to send out status and monitoring information
        """

        super().__init__()
        self.control_server = control_server

        if Settings.simulation_mode():
            self.daq = DAQ6510Simulator()
        else:
            self.daq = DAQ6510Controller()

        try:
            self.daq.connect()
        except (ConnectionError, DeviceTimeoutError):
            MODULE_LOGGER.warning(
                f"Couldn't establish a connection to the DAQ6510, check the log messages.")

        self.load_commands(COMMAND_SETTINGS.Commands, DAQ6510Command, DAQ6510Interface)
        self.build_device_method_lookup_table(self.daq)

        setup = load_setup()
        self.channels = setup.gse.DAQ6510.channels

        self.hk_conversion_table = read_conversion_dict(self.control_server.get_storage_mnemonic(), setup=setup)

        self.synoptics = SynopticsManagerProxy()
        self.metrics = define_metrics(origin="DAS-DAQ6510", use_site=True, setup=setup)

    def get_bind_address(self) -> str:
        """ Returns a string with the bind address, the endpoint, for accepting connections and bind a socket to.


        Returns: String with the protocol and port to bind a socket to.
        """

        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_status(self) -> dict:
        """ Returns a dictionary with status information for the Control Server and the DAQ6510.

        Returns: Dictionary with status information for the Control Server and the DAQ6510.
        """

        return super().get_status()

    def get_housekeeping(self) -> dict:
        """ Returns a dictionary with housekeeping information about the DAQ6510.

        Returns: Dictionary with housekeeping information about the DAQ6510.
        """

        hk_dict = dict()
        hk_dict["timestamp"] = format_datetime()

        # # TODO I guess we have to do something along those lines
        # # (We'll have to increase the HK delay, cfr. Agilents)
        # measurement = self.daq.perform_measurement(channel_list=self.channels)
        # temperatures = convert_hk_names(measurement, self.hk_conversion_table)
        # hk_dict.update(temperatures)
        #
        # self.synoptics.store_th_synoptics(hk_dict)
        #
        # for key, value in hk_dict.items():
        #     if key != "timestamp":
        #         self.metrics[key].set(value)

        return hk_dict

    def quit(self) -> None:
        """ Clean up and stop threads that were started by the process. """

        # TODO
        # self.synoptics.disconnect_cs()
        pass
