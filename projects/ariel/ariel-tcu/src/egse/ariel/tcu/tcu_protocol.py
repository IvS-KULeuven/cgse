"""Command protocol for the Ariel Telescope Control Unit (TCU)."""

import logging
from pathlib import Path

from egse.ariel.tcu import NUM_TSM_PROBES_PER_FRAME
from egse.ariel.tcu.tcu import TcuController, TcuSimulator, TcuInterface
from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.protocol import DynamicCommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

_HERE = Path(__file__).parent
DEVICE_SETTINGS = Settings.load(filename="tcu.yaml", location=_HERE)
LOGGER = logging.getLogger("egse.ariel.tcu")


class TcuCommand(ClientServerCommand):
    """Command class for the Ariel TCU Control Server."""

    pass


class TcuProtocol(DynamicCommandProtocol):
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
            LOGGER.warning("Couldn't establish connection to the Ariel TCU, check the log messages.")

        # self.metrics = define_metrics("TCU")

    def get_bind_address(self) -> str:
        """Returns the bind address for the Ariel TCU Control Server.

        Returns:
            Bind address for the Ariel TCU Control Server.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_device(self) -> TcuInterface:
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

        result["TCU_MODE"] = self.tcu.get_tcu_mode()
        result["TCU_VHK_PSU_VMOTOR"] = self.tcu.vhk_psu_vmotor()
        result["TCU_VHK_PSU_VHI"] = self.tcu.vhk_psu_vhi()
        result["TCU_VHK_PSU_VLOW"] = self.tcu.vhk_psu_vlow()
        result["TCU_VHK_PSU_VMEDP"] = self.tcu.vhk_psu_vmedp()
        result["TCU_VHK_PSU_VMEDN"] = self.tcu.vhk_psu_vmedn()
        result["TCU_IHK_PSU_VMEDN"] = self.tcu.ihk_psu_vmedn()
        result["TCU_IHK_PSU_VMEDP"] = self.tcu.ihk_psu_vmedp()
        result["TCU_IHK_PSU_VLOW"] = self.tcu.ihk_psu_vlow()
        result["TCU_IHK_PSU_VHI"] = self.tcu.ihk_psu_vhi()
        result["TCU_IHK_PSU_VMOTOR"] = self.tcu.ihk_psu_vmotor()
        result["TCU_THK_PSU_FIRST"] = self.tcu.thk_psu_first()
        result["TCU_THK_M2MD_FIRST"] = self.tcu.thk_m2md_first()
        result["TCU_THK_PSU_SECOND"] = self.tcu.thk_psu_second()
        result["TCU_THK_M2MD_SECOND"] = self.tcu.thk_m2md_second()
        result["TCU_THK_CTS_Q1"] = self.tcu.thk_cts_q1()
        result["TCU_THK_CTS_Q2"] = self.tcu.thk_cts_q2()
        result["TCU_THK_CTS_Q3"] = self.tcu.thk_cts_q3()
        result["TCU_THK_CTS_Q4"] = self.tcu.thk_cts_q4()
        result["TCU_THK_CTS_FPGA"] = self.tcu.thk_cts_fpga()
        result["TCU_THK_CTS_ADS1282"] = self.tcu.thk_cts_ads1282()
        result["TCU_VHK_THS_RET"] = self.tcu.vhk_ths_ret()
        result["TCU_HK_ACQ_COUNTER"] = self.tcu.hk_acq_counter()

        for probe in range(1, NUM_TSM_PROBES_PER_FRAME + 1):
            bias_pos = self.tcu.tsm_adc_value_xx_biasp(probe=probe)
            result[f"TCU_BIAS_POS_PROBE_{probe}"] = bias_pos
            bias_neg = self.tcu.tsm_adc_value_xx_biasn(probe=probe)
            result[f"TCU_BIAS_NEG_PROBE_{probe}"] = bias_neg
            current_pos = self.tcu.tsm_adc_value_xx_currentp(probe=probe)
            result[f"TCU_CURRENT_POS_PROBE_{probe}"] = current_pos
            current_neg = self.tcu.tsm_adc_value_xx_currentn(probe=probe)
            result[f"TCU_CURRENT_NEG_PROBE_{probe}"] = current_neg

            # alpha = (bias_pos - bias_neg) / (current_pos - current_neg)
            # (c0, c1) ??
            # resistance = alpha / (alpha * c1 + c0)

        return result

    def is_device_connected(self) -> bool:
        """Checks whether the Ariel TCU is connected.

        Returns:
            True if the Ariel TCU is connected; False otherwise.
        """

        return self.tcu.is_connected()
