"""Command protocol for the Digilent MEASURpoint DT8874."""

import logging
from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.digilent.digilent import DigilentInterface
from egse.digilent.measurpoint.dt8874.dt8874 import Dt8874Simulator, Dt8874Controller
from egse.digilent.measurpoint.dt8874.dt8874_cs import ORIGIN
from egse.hk import read_conversion_dict, convert_hk_names
from egse.protocol import DynamicCommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

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

        self.hk_conversion_table = read_conversion_dict(
            self.get_control_server().get_storage_mnemonic(), use_site=False
        )

        self.simulator = simulator

        if self.simulator:
            self.dt8874: DigilentInterface = Dt8874Simulator()
        else:
            self.dt8874: DigilentInterface = Dt8874Controller()

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

    def get_device(self) -> DigilentInterface:
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

        if "RTD" in self.dt8874.channels:
            for rtd_type in self.dt8874.channels.RTD:
                rtd_temperatures = self.dt8874.get_rtd_temperature(
                    rtd_type=rtd_type, channels=self.dt8874.channels.RTD[rtd_type]
                )

                for channel_id, rtd_temperature in zip(self.dt8874.channel_lists.RTD[rtd_type], rtd_temperatures):
                    original_name = f"{ORIGIN}_T_RTD_{rtd_type}_CH{channel_id}"
                    result[original_name] = rtd_temperature

        if "THERMOCOUPLE" in self.dt8874.channels:
            for tc_type in self.dt8874.channels.THERMOCOUPLE:
                tc_temperatures = self.dt8874.get_thermocouple_temperature(
                    tc_type=tc_type, channels=self.dt8874.channels.THERMOCOUPLE[tc_type]
                )

                for channel_id, tc_temperature in zip(self.dt8874.channel_lists.THERMOCOUPLE[tc_type], tc_temperatures):
                    original_name = f"{ORIGIN}_T_TC_{tc_type}_CH{channel_id}"
                    result[original_name] = tc_temperature

        if "RESISTANCE" in self.dt8874.channels:
            resistances = self.dt8874.get_resistance(self.dt8874.channels.RESISTANCE)

            for channel_id, resistance in zip(self.dt8874.channel_lists.RESISTANCE, resistances):
                original_name = f"{ORIGIN}_R_CH{channel_id}"
                result[original_name] = resistance

        if "VOLTAGE" in self.dt8874.channels:
            voltages = self.dt8874.get_voltage(self.dt8874.channels.VOLTAGE)

            for channel_id, voltage in zip(self.dt8874.channel_lists.VOLTAGE, voltages):
                original_name = f"{ORIGIN}_V_CH{channel_id}"
                result[original_name] = voltage

        if self.hk_conversion_table:
            return convert_hk_names(result, self.hk_conversion_table)
        return result

    def is_device_connected(self) -> bool:
        """Checks whether the Digilent MEASURpoint DT8874 is connected.

        Returns:
            True if the Digilent MEASURpoint DT8874 is connected; False otherwise.
        """

        return self.dt8874.is_connected()
