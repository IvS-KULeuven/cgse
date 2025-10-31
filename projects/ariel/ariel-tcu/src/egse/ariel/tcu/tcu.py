"""Ariel Telescope Control Unit (TCU) commanding.

Commanding is done by communicating with the TCU Arduino via a serial port (with the PySerial package).

We discern between the following types of commands:
    - General commands;
    - M2MD commands (on a per-axis basis);
    - Thermal Monitoring System (TSM) commands;
    - HK commands.

Reference documents:
    - RD01: TCU User Manual (ARIEL-IEEC-PL-TN-002), v1.2
    - RD02: ARIEL TCU Data Handling (ARIEL-IEEC-PL-TN-007), v1.0
    - RD02: TCU code provided by Vladimiro Noce (priv. comm.)
"""

import logging
from serial.tools import list_ports

from egse.ariel.tcu import PROXY_TIMEOUT, SERVICE_TYPE, TcuMode
from egse.ariel.tcu.tcu_cmd_utils import (
    set_tcu_mode,
    tcu_simulated,
    restart_links_period_latch,
    set_restart_links_period,
    CommandAddress,
    ope_mng_command,
    ope_mng_event_clear_protect_flag,
    ope_mng_event_clear,
    ope_mng_status,
    ope_mng_event_reg,
    get_acq_curr_off_corr,
    set_acq_curr_off_corr,
    get_acq_curr_gain_corr,
    set_acq_curr_gain_corr,
    acq_axis_a_curr_read,
    acq_axis_b_curr_read,
    acq_ave_lpf_en,
    acq_ovc_cfg_filter,
    acq_avc_filt_time,
    acq_average_type,
    acq_spk_filt_counter_lim,
    acq_spk_filt_incr_thr,
    get_prof_gen_axis_step,
    set_prof_gen_axis_step,
    get_prof_gen_axis_speed,
    set_prof_gen_axis_speed,
    get_prof_gen_axis_state_start,
    set_prof_gen_axis_state_start,
    sw_rs_xx_sw_rise,
    sw_rs_xx_sw_fall,
    set_tsm_current_value,
    set_tsm_current_offset,
    set_tsm_adc_hpf_register,
    set_tsm_adc_ofc_register,
    set_tsm_adc_fsc_register,
    tsm_adc_command,
    tsm_adc_calibration,
    tsm_adc_value_xx_currentn,
    tsm_adc_value_xx_biasn,
    tsm_adc_value_xx_currentp,
    tsm_adc_value_xx_biasp,
    tcu_firmware_id,
    get_tcu_mode,
    tcu_status,
    get_restart_links_period,
    tsm_latch,
    get_tsm_current_value,
    get_tsm_current_offset,
    tsm_adc_id_register,
    tsm_adc_configuration_register,
    get_tsm_adc_ofc_register,
    get_tsm_adc_fsc_register,
    tsm_adc_command_latch,
    tsm_acq_counter,
    get_tsm_adc_hpf_register,
    tsm_adc_register_latch,
    vhk_psu_vmotor,
    vhk_psu_vhi,
    vhk_psu_vlow,
    vhk_psu_vmedp,
    vhk_psu_vmedn,
    ihk_psu_vmedn,
    ihk_psu_vlow,
    ihk_psu_vmedp,
    ihk_psu_vhi,
    ihk_psu_vmotor,
    thk_psu_first,
    thk_m2md_first,
    thk_psu_second,
    thk_m2md_second,
    thk_cts_q1,
    thk_cts_q2,
    thk_cts_q3,
    thk_cts_q4,
    thk_cts_fpga,
    thk_cts_ads1282,
    vhk_ths_ret,
    hk_acq_counter,
)

from egse.device import DeviceInterface
from egse.mixin import dynamic_command, CommandType, DynamicCommandMixin
from egse.proxy import DynamicProxy
from egse.ariel.tcu.tcu_devif import TcuDeviceInterface
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address

logger = logging.getLogger("egse.ariel.tcu")


def get_all_serial_ports() -> list:
    """Returns a list of all available serial ports.

    Returns:
        List of all available serial ports.
    """

    return list_ports.comports()


class TcuInterface(DeviceInterface):
    # General commands

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tcu_firmware_id)
    def tcu_firmware_id(self):
        """Selects the Instrument Control Unit (ICU) channel and returns the firmware version.

        Returns:
            Firmware version of the Ariel TCU.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tcu_mode)
    def get_tcu_mode(self):
        """Returns the current mode of the Ariel TCU.

        Possible modes are:
            - IDLE (0x0000): Waiting for commands, minimum power consumption
            - BASE (0x0001): HK + TSM Circuitry on
            - CALIBRATION (0x0003): HK + TSM + M2MD circuitry on

        Returns:
            Current mode of the Ariel TCU.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tcu_mode)
    def set_tcu_mode(self, tcu_mode: TcuMode | int = TcuMode.IDLE):
        """Selects the Ariel TCU working mode.

        Args:
            tcu_mode (TcuMode | int): Ariel TCU working mode:
                - IDLE (0x0000): Waiting for commands, minimum power consumption
                - BASE (0x0001): HK + TSM Circuitry on
                - CALIBRATION (0x0003): HK + TSM + M2MD circuitry on
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tcu_status)
    def tcu_status(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tcu_simulated)
    def tcu_simulated(self, cargo2: int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=restart_links_period_latch)
    def restart_links_period_latch(self, cargo2: int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_restart_links_period)
    def get_restart_links_period(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_restart_links_period)
    def set_restart_links_period(self, link_period: int = 0xFFFF):
        pass

    # M2MD commands

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_command)
    def ope_mng_command(self, axis: CommandAddress | str | int, cargo2: int = 0x0002):
        """Commands the action to the SENER motor driver IP core.

        Args:
            axis (CommandAddress): Axis to which the command is sent.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_event_clear_protect_flag)
    def ope_mng_event_clear_protect_flag(self, axis: CommandAddress | str | int, cargo2: int = 0xAAAA):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_event_clear)
    def ope_mng_event_clear(self, axis: CommandAddress | str | int, cargo2: int = 0x0001):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_status)
    def ope_mng_status(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_event_reg)
    def ope_mng_event_reg(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_acq_curr_off_corr)
    def get_acq_curr_off_corr(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_acq_curr_off_corr)
    def set_acq_curr_off_corr(self, axis: CommandAddress | str | int, cargo2: int = 0x03FB):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_acq_curr_gain_corr)
    def get_acq_curr_gain_corr(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_acq_curr_gain_corr)
    def set_acq_curr_gain_corr(self, axis: CommandAddress | str | int, cargo2: int = 0x074C):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_axis_a_curr_read)
    def acq_axis_a_curr_read(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_axis_b_curr_read)
    def acq_axis_b_curr_read(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_ave_lpf_en)
    def acq_ave_lpf_en(self, axis: CommandAddress | str | int, cargo2: int = 0x0001):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_ovc_cfg_filter)
    def acq_ovc_cfg_filter(self, axis: CommandAddress | str | int, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_avc_filt_time)
    def acq_avc_filt_time(self, axis: CommandAddress | str | int, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_average_type)
    def acq_average_type(self, axis: CommandAddress | str | int, cargo2: int = 0x0000):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_spk_filt_counter_lim)
    def acq_spk_filt_counter_lim(self, axis: CommandAddress | str | int, cargo2: int = 0x0001):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=acq_spk_filt_incr_thr)
    def acq_spk_filt_incr_thr(self, axis: CommandAddress | str | int, cargo2: int = 0x04C0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_prof_gen_axis_step)
    def get_prof_gen_axis_step(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_prof_gen_axis_step)
    def set_prof_gen_axis_step(self, axis: CommandAddress | str | int, cargo2: int = 0x0480):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_prof_gen_axis_speed)
    def get_prof_gen_axis_speed(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_prof_gen_axis_speed)
    def set_prof_gen_axis_speed(self, axis: CommandAddress | str | int, cargo2: int = 0x1777):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_prof_gen_axis_state_start)
    def get_prof_gen_axis_state_start(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_prof_gen_axis_state_start)
    def set_prof_gen_axis_state_start(self, axis: CommandAddress | str | int, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=sw_rs_xx_sw_rise)
    def sw_rs_xx_sw_rise(self, axis: CommandAddress | str | int, position: int = 1):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=sw_rs_xx_sw_fall)
    def sw_rs_xx_sw_fall(self, axis: CommandAddress | str | int, position: int = 1):
        pass

    # TSM commands

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_latch)
    def tsm_latch(self, cargo1: str | int, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_current_value)
    def get_tsm_current_value(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_current_value)
    def set_tsm_current_value(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_current_offset)
    def get_tsm_current_offset(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_current_offset)
    def set_tsm_current_offset(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_register_latch)
    def tsm_adc_register_latch(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_id_register)
    def tsm_adc_id_register(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_configuration_register)
    def tsm_adc_configuration_register(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_adc_hpf_register)
    def get_tsm_adc_hpf_register(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_adc_hpf_register)
    def set_tsm_adc_hpf_register(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_adc_ofc_register)
    def get_tsm_adc_ofc_register(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_adc_ofc_register)
    def set_tsm_adc_ofc_register(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_adc_fsc_register)
    def get_tsm_adc_fsc_register(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_adc_fsc_register)
    def set_tsm_adc_fsc_register(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_command_latch)
    def tsm_adc_command_latch(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_command)
    def tsm_adc_command(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_calibration)
    def tsm_adc_calibration(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_value_xx_currentn)
    def tsm_adc_value_xx_currentn(self, probe: int = 1):
        """Returns the negative current to polarise the given thermistor.

        Args:
            probe (int): Thermistor identifier.

        Returns:
            Negative current to polarise the given thermistor.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_value_xx_biasn)
    def tsm_adc_value_xx_biasn(self, probe: int = 1):
        """Returns the voltage measured on the given thermistor biased with negative current.

        Args:
            probe (int): Thermistor identifier.

        Returns:
            Voltage on the thermistor biased with the negative current.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_value_xx_currentp)
    def tsm_adc_value_xx_currentp(self, probe: int = 1):
        """Returns the positive current to polarise the given thermistor.

        Args:
            probe (int): Thermistor identifier.

        Returns:
            Positive current to polarise the given thermistor.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_value_xx_biasp)
    def tsm_adc_value_xx_biasp(self, probe: int = 1):
        """Returns the voltage measured on the given thermistor biased with positive current.

        Args:
            probe (int): Thermistor identifier.

        Returns:
            Voltage on the thermistor biased with the positive current.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_acq_counter)
    def tsm_acq_counter(self):
        """Reads the number of ADC measurement sequences that have been made.

        Returns:
            Number of ADC measurement sequences that have been made.
        """

        pass

    # HK commands

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=vhk_psu_vmotor)
    def vhk_psu_vmotor(self):
        """Returns the HK PSU motor voltage value.

        Returns:
            HK PSU motor voltage value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=vhk_psu_vhi)
    def vhk_psu_vhi(self):
        """Returns the HK PSU high voltage value.

        Returns:
            HK PSU motor high voltage value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=vhk_psu_vlow)
    def vhk_psu_vlow(self):
        """Returns the HK PSU low voltage value.

        Returns:
            HK PSU motor low voltage value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=vhk_psu_vmedp)
    def vhk_psu_vmedp(self):
        """Returns the HK PSU medium positive voltage value.

        Returns:
            HK PSU medium positive voltage value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=vhk_psu_vmedn)
    def vhk_psu_vmedn(self):
        """Returns the HK PSU medium negative voltage value.

        Returns:
            HK PSU medium negative voltage value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ihk_psu_vmedn)
    def ihk_psu_vmedn(self):
        """Returns the HK medium negative current value.

        Returns:
            HK medium negative current value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ihk_psu_vmedp)
    def ihk_psu_vmedp(self):
        """Returns the HK medium positive current value.

        Returns:
            HK medium positive current value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ihk_psu_vlow)
    def ihk_psu_vlow(self):
        """Returns the HK PSU low current value.

        Returns:
            HK PSU low current value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ihk_psu_vhi)
    def ihk_psu_vhi(self):
        """Returns the HK PSU high current value.

        Returns:
            HK PSU high current value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ihk_psu_vmotor)
    def ihk_psu_vmotor(self):
        """Returns the HK PSU motor current value.

        Returns:
            HK PSU motor current value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_psu_first)
    def thk_psu_first(self):
        """Returns the HK PSU temperature zone 1.

        Returns:
            HK PSU temperature zone 1.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_m2md_first)
    def thk_m2md_first(self):
        """Returns the HK M2MD temperature zone 1.

        Returns:
            HK M2MD temperature zone 1.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_psu_second)
    def thk_psu_second(self):
        """Returns the HK M2MD temperature zone 2.

        Returns:
            HK M2MD temperature zone 2.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_m2md_second)
    def thk_m2md_second(self):
        """Returns the HK M2MD temperature zone 2.

        Returns:
            HK M2MD temperature zone 2.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_cts_q1)
    def thk_cts_q1(self):
        """Returns the HK CTS temperature first quarter.

        Returns:
            HK CTS temperature first quarter.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_cts_q2)
    def thk_cts_q2(self):
        """Returns the HK CTS temperature second quarter.

        Returns:
            HK CTS temperature second quarter.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_cts_q3)
    def thk_cts_q3(self):
        """Returns the HK CTS temperature third quarter.

        Returns:
            HK CTS temperature third quarter.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_cts_q4)
    def thk_cts_q4(self):
        """Returns the HK CTS temperature fourth quarter.

        Returns:
            HK CTS temperature fourth quarter.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_cts_fpga)
    def thk_cts_fpga(self):
        """Returns the HK CTS temperature FPGA.

        Returns:
            HK CTS temperature FPGA.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=thk_cts_ads1282)
    def thk_cts_ads1282(self):
        """Returns the HK CTS temperature ADS1282.

        Returns:
            HK CTS temperature ADS1282.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=vhk_ths_ret)
    def vhk_ths_ret(self):
        """Returns the HK CTS thermistors return voltage.

        Returns:
            HK CTS thermistors return voltage.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=hk_acq_counter)
    def hk_acq_counter(self):
        """Returns the running counter that indicates the number of HK measurement sequences that have been made.

        Returns:
            Free running counter that indicates the number of HK measurement sequences that have been made.
        """

        pass


class TcuController(TcuInterface, DynamicCommandMixin):
    def __init__(self):
        """Initialisation of an Ariel TCU controller."""

        super().__init__()
        self.transport = self.tcu = TcuDeviceInterface()

    # noinspection PyMethodMayBeStatic
    def is_simulator(self):
        return False

    def is_connected(self):
        return self.tcu.is_connected()

    def connect(self):
        # TODO
        pass

    def disconnect(self):
        # TODO
        pass

    def reconnect(self):
        if self.is_connected():
            self.disconnect()
        self.connect()


class TcuSimulator(TcuInterface, DynamicCommandMixin):
    def __init__(self):
        super().__init__()

        self._is_connected = True

        self.tcu_mode = TcuMode.IDLE
        self.restart_links_period = 0
        self.acq_curr_off_corr_list = [None, 0, 0, 0]
        self.acq_curr_gain_corr_list = [None, 0, 0, 0]

        self.acq_axis_a_curr_read_list = [0, 1, 2, 3]
        self.acq_axis_b_curr_read_list = [0, 4, 5, 6]

        self.prof_gen_axis_step_list = [None, 7, 8, 9]
        self.prof_gen_axis_speed_list = [None, 10, 11, 12]
        self.prof_gen_axis_state_start_list = [None, 13, 14, 14]

    # noinspection PyMethodMayBeStatic
    def is_simulator(self):
        return True

    # noinspection PyMethodMayBeStatic
    def is_connected(self):
        return self._is_connected

    def connect(self):
        self._is_connected = True

    def disconnect(self):
        self._is_connected = False

    def reconnect(self):
        self._is_connected = True

    def tcu_firmware_id(self):
        return "TCU Simulator"

    def get_tcu_mode(self):
        return self.tcu_mode

    def set_tcu_mode(self, tcu_mode: TcuMode | int = TcuMode.IDLE):
        if isinstance(tcu_mode, TcuMode):
            self.tcu_mode = tcu_mode.value

        elif isinstance(tcu_mode, int):
            self.tcu_mode = tcu_mode

    def tcu_status(self):
        # TODO
        pass

    def tcu_simulated(self, cargo2: int):
        # TODO
        pass

    def set_restart_links_period(self, link_period: int = 0xFFFF):
        self.restart_links_period = link_period

    def get_restart_links_period(self):
        return self.restart_links_period

    def get_acq_curr_off_corr(self, axis: CommandAddress | str | int):
        return self.acq_curr_off_corr_list[int(axis)]

    def set_acq_curr_off_corr(self, axis: CommandAddress | str | int, cargo2: int = 0x03FB):
        self.acq_curr_off_corr_list[int(axis)] = cargo2

    def get_acq_curr_gain_corr(self, axis: CommandAddress | str | int):
        return self.acq_curr_gain_corr_list[int(axis)]

    def set_acq_curr_gain_corr(self, axis: CommandAddress | str | int, cargo2: int = 0x074C):
        self.acq_curr_gain_corr_list[int(axis)] = cargo2

    def acq_axis_a_curr_read(self, axis: CommandAddress | str | int):
        return self.acq_axis_a_curr_read_list[int(axis)]

    def acq_axis_b_curr_read(self, axis: CommandAddress | str | int):
        return self.acq_axis_b_curr_read_list[int(axis)]

    def get_prof_gen_axis_step(self, axis: CommandAddress | str | int):
        return self.prof_gen_axis_step_list[int(axis)]

    def set_prof_gen_axis_step(self, axis: CommandAddress | str | int, cargo2: int = 0x0480):
        self.prof_gen_axis_step_list[int(axis)] = cargo2

    def get_prof_gen_axis_speed(self, axis: CommandAddress | str | int):
        return self.prof_gen_axis_speed_list[int(axis)]

    def set_prof_gen_axis_speed(self, axis: CommandAddress | str | int, cargo2: int = 0x1777):
        self.prof_gen_axis_speed_list[int(axis)] = cargo2

    def get_prof_gen_axis_state_start(self, axis: CommandAddress | str | int):
        return self.prof_gen_axis_state_start_list[int(axis)]

    def set_prof_gen_axis_state_start(self, axis: CommandAddress | str | int, cargo2: int = 0):
        self.prof_gen_axis_state_start_list[int(axis)] = cargo2


class TcuProxy(DynamicProxy, TcuInterface):
    """
    The TcuProxy class is used to connect to the TCU Control Server and send commands to the TCU Hardware Controller remotely.
    """

    def __init__(self):
        """Initialisation of a TCUProxy."""

        with RegistryClient() as reg:
            service = reg.discover_service(SERVICE_TYPE)

            if service:
                protocol = service.get("protocol", "tcp")
                hostname = service["host"]
                port = service["port"]

                super().__init__(connect_address(protocol, hostname, port), timeout=PROXY_TIMEOUT)

            else:
                raise RuntimeError(f"No service registered as {SERVICE_TYPE}")
