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
    - RD03: TCU code provided by Vladimiro Noce (priv. comm.)
    - RD04: ARIEL Telescope Control Unit Design Description Document (ARIEL-IEEC-PL-DD-001), v1.10
    - RD05: ARIEL TCU FW Architecture Design(ARIEL-IEEC-PL-DD-002), v1.5
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
from egse.ariel.tcu.tcu_devif import TcuDeviceInterface, TcuHexInterface
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address

LOGGER = logging.getLogger("egse.ariel.tcu")


def get_all_serial_ports() -> list:
    """Returns a list of all available serial ports.

    Returns:
        List of all available serial ports.
    """

    ports = list_ports.comports()

    for port in ports:
        print(port)

    return ports


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
        """Returns the TCU status.

        The TCU status is a bit word that indicates the current state of the TCU.  The meaning of a bit being set
        to one is as follows:

            - bit 0: main link enabled
            - bit 1: secondary link enabled
            - bit 2: TSM enabled
            - bit3: M2MD enabled
            - bit 4: TSM in simulated mode
            - bit 5: M2MD in simulated mode
            - bit 6: HK in simulated mode
            - bit 7: M2MD axis 1 enabled
            - bit 8: M2MD axis 2 enabled
            - bit 9: M2MD axis 3 enabled
            - bit 10: TSM initialised
            - bit 11: ADS_MFLAG active
            - bit 12: ADS_REGISTERS_ERROR active

        Returns:
            Bit word that indicated the current state of the TCU.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tcu_simulated)
    def tcu_simulated(self, cargo2: int):
        """Changes a TCU sub-system in simulated mode.

        This is only possible in IDLE mode.

        The cargo2 parameter denotes which sub-system to change to simulated mode.  The meaning of a bit being set to
        one is as follows:

            - bit 0: TBD
            - bit 1: TBD
            - bit 2: TBD
            - bit 3: TBD
            - bit 4: Put the TSM in simulated mode
            - bit 5: Put the M2MD in simulated mode
            - bit 6: Put the HK in simulated mode

        Args:
            cargo2 (int): Cargo 2 part of the command string.
        """
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=restart_links_period_latch)
    def restart_links_period_latch(self, cargo2: int):
        """Re-starts the link period latch.

        This is only possible in IDLE mode.


        Note that a read does not disarm the latch.

        Args:
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_restart_links_period)
    def get_restart_links_period(self):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_restart_links_period)
    def set_restart_links_period(self, link_period: int = 0xFFFF):
        """Re-start both links if no message is received after the given link period +1s.

        Args:
            link_period (int): 1s after this time duration, both links will be re-started if no message is received.
        """
        pass

    # M2MD commands

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_command)
    def ope_mng_command(self, axis: CommandAddress | str | int, cargo2: int = 0x0002):
        """Commands the action to the SENER motor driver IP core for the given M2MD axis.

        The cargo2 parameter denotes the action to be performed.  The meaning of a bit being set to
        one is as follows:

            - bit 0: Activate motion
            - bit 1: Stop motion

        Args:
            axis (CommandAddress): Axis to which the command is sent.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_event_clear_protect_flag)
    def ope_mng_event_clear_protect_flag(self, axis: CommandAddress | str | int, cargo2: int = 0xAAAA):
        """Clears the event register protection flag.

        Args:
            axis (CommandAddress): Axis to which the command is sent.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_event_clear)
    def ope_mng_event_clear(self, axis: CommandAddress | str | int, cargo2: int = 0x0001):
        """Clears the event register for the given M2MD axis.

        Args:
            axis (CommandAddress): Axis to which the command is sent.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_status)
    def ope_mng_status(self, axis: CommandAddress | str | int):
        """Returns the current status of the motor for the given M2MD axis.

        Args:
            axis (CommandAddress): Axis to which the command is sent.

        Returns:
            Current status of the motor for the given M2MD axis. Bit 0 being set to one means that the motor is
            in stand-by mode; bit 1 being set to one means that the motor is in operation state.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ope_mng_event_reg)
    def ope_mng_event_reg(self, axis: CommandAddress | str | int):
        """Returns the list of all events since wake-up or the last clear event.

        Args:
            axis (CommandAddress): Axis to which the command is sent.

        Returns:
            List of all events since wake-up or the last clear event.
        """

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
        """Axis position command for the given M2MD axis.

        The cargo2 parameter denotes the desired positioning. The meaning of its constituent bits is as follows:

            - bits 0-14: Number of steps to be carried out
            - bit 15: Direction of motion (0: counterclockwise, 1: clockwise)

        Args:
            axis (CommandAddress | str | int): Axis to which the command is sent.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_prof_gen_axis_speed)
    def get_prof_gen_axis_speed(self, axis: CommandAddress | str | int):
        """Returns the axis writing speed for the given M2MD axis.

        Args:
            axis (CommandAddress | str | int): Axis to which the command is sent.
        """
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_prof_gen_axis_speed)
    def set_prof_gen_axis_speed(self, axis: CommandAddress | str | int, cargo2: int = 0x0177):
        """Axis velocity command for the given M2MD axis.

        The cargo2 parameter denotes the desired velocity.

        Args:
            axis (CommandAddress | str | int): Axis to which the command is sent.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_prof_gen_axis_state_start)
    def get_prof_gen_axis_state_start(self, axis: CommandAddress | str | int):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_prof_gen_axis_state_start)
    def set_prof_gen_axis_state_start(self, axis: CommandAddress | str | int, cargo2: int = 0):
        """Changes the starting point of the magnetic state for the given M2MD axis.


        Args:
            axis (CommandAddress | str | int): Axis to which the command is sent.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=sw_rs_xx_sw_rise)
    def sw_rs_xx_sw_rise(self, axis: CommandAddress | str | int, position: int = 1):
        """Position switch rise.

        Args:
            axis (CommandAddress | str | int): Axis to which the command is sent.
            position (int): Position of the SW_RS_XX_SW_RISE command.

        Returns:
            Relative position measured when the rising edge of the given switch is detected.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=sw_rs_xx_sw_fall)
    def sw_rs_xx_sw_fall(self, axis: CommandAddress | str | int, position: int = 1):
        """Position switch fall.

        Args:
            axis (CommandAddress | str | int): Axis to which the command is sent.
            position (int): Position of the SW_RS_XX_SW_FALL command.

        Returns:
            Relative position measured when the falling edge of the given switch is detected.
        """

        pass

    # TSM commands

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_latch)
    def tsm_latch(self, cargo1: str | int, cargo2: int = 0):
        """Latches to allow the modification of the operation management register.

        Args:
            cargo1 (str | int): Cargo 1 part of the command string.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_current_value)
    def get_tsm_current_value(self):
        """Returns the TSM current.

        Returns:
            TSM current.
        """
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_current_value)
    def set_tsm_current_value(self, cargo1: int = 0, cargo2: int = 0):
        """Sets the TSM current value.

        Args:
            cargo1 (int): Cargo 1 part of the command string.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_current_offset)
    def get_tsm_current_offset(self):
        """Returns the TSM current offset.

        Returns:
            TSM current offset.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_current_offset)
    def set_tsm_current_offset(self, cargo1: int = 0, cargo2: int = 0):
        """Sets the TSM current offset.

        Args:
            cargo1 (int): Cargo 1 part of the command string.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_register_latch)
    def tsm_adc_register_latch(self, cargo1: int = 0, cargo2: int = 0):
        """Re-starts the TSM ADC register latch.

        Args:
            cargo1 (int): Cargo 1 part of the command string.
            cargo2 (int): Cargo 2 part of the command string.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_id_register)
    def tsm_adc_id_register(self):
        """Returns the content of the TSM ADC identifier register.

        Returns:
            Content of the TSM ADC identifier register.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=tsm_adc_configuration_register)
    def tsm_adc_configuration_register(self):
        """Returns the content of the TSM ADC configuration register.

        Returns:
            Content of the TSM ADC configuration register.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_adc_hpf_register)
    def get_tsm_adc_hpf_register(self):
        """Returns the content of the high-pass corner frequency register.

        Returns:
            Content of the high-pass corner frequency register.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_adc_hpf_register)
    def set_tsm_adc_hpf_register(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_adc_ofc_register)
    def get_tsm_adc_ofc_register(self):
        """Returns the content of the offset calibration register.

        Returns:
            Content of the offset calibration register.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=set_tsm_adc_ofc_register)
    def set_tsm_adc_ofc_register(self, cargo1: int = 0, cargo2: int = 0):
        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=get_tsm_adc_fsc_register)
    def get_tsm_adc_fsc_register(self):
        """Returns the content of the full-scale calibration register.

        Returns:
            Content of the full-scale calibration register.
        """

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
        """Returns the HK PSU medium negative current value.

        Returns:
            HK PSU medium negative current value.
        """

        pass

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string_func=ihk_psu_vmedp)
    def ihk_psu_vmedp(self):
        """Returns the HK PSU medium positive current value.

        Returns:
            HK PSU medium positive current value.
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
        """Checks whether the serial port to the TCU Arduino is open.

        Returns:
            True if the serial port to the TCU Arduino is open; False otherwise.
        """

        return self.tcu.is_connected()

    def connect(self):
        """Opens the serial port to the TCU Arduino.

        Raises:
            TcuError: When the serial port could not be opened.
        """

        self.tcu.connect()

    def disconnect(self):
        """Closes the serial port to the TCU Arduino.

        Raises:
            TcuError: When the serial port could not be closed.
        """

        self.tcu.disconnect()

    def reconnect(self):
        """Re-connects to the Ariel TCU Arduino."""

        self.tcu.reconnect()


class TcuSimulator(TcuInterface):
    VHK_PSU_MOTOR = 0x0080
    VHK_PSU_VHI = 0x0280
    VHK_PSU_VLOW = 0x0480
    VHK_PSU_VMEDP = 0x0680
    VHK_PSU_VMEDN = 0x0880
    IHK_PSU_VMEDN = 0x0A80
    IHK_PSU_VMEDP = 0x0A80
    IHK_PSU_VLOW = 0x0A80
    IHK_PSU_VHI = 0x0A80
    IHK_PSU_VMOTOR = 0x0A80
    THK_PSU_FIRST = 0x0A80
    THK_M2MD_FIRST = 0x0A80
    THK_PSU_SECOND = 0x0C80
    THK_M2MD_SECOND = 0x0C80
    THK_CTS_Q1 = 0x0A80
    THK_CTS_Q2 = 0x0C80
    THK_CTS_Q3 = 0x0C80
    THK_CTS_Q4 = 0x0C80
    THK_CTS_FPGA = 0x0A80
    THK_CTS_ADS1282 = 0x0C80
    VHK_THS_RET = 0x0E80
    HK_ACQ_COUNTER = 0x002A

    def __init__(self):
        """Initialisation of an Ariel TCU simulator."""

        super().__init__()

        self._is_connected = True

        self.tcu_mode = TcuMode.IDLE.value
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

    def vhk_psu_vmotor(self):
        return TcuSimulator.VHK_PSU_MOTOR

    def vhk_psu_vhi(self):
        return TcuSimulator.VHK_PSU_VHI

    def vhk_psu_vlow(self):
        return TcuSimulator.VHK_PSU_VLOW

    def vhk_psu_vmedp(self):
        return TcuSimulator.VHK_PSU_VMEDP

    def vhk_psu_vmedn(self):
        return TcuSimulator.VHK_PSU_VMEDN

    def ihk_psu_vmedn(self):
        return TcuSimulator.IHK_PSU_VMEDN

    def ihk_psu_vmedp(self):
        return TcuSimulator.IHK_PSU_VMEDP

    def ihk_psu_vlow(self):
        return TcuSimulator.IHK_PSU_VLOW

    def ihk_psu_vhi(self):
        return TcuSimulator.IHK_PSU_VHI

    def ihk_psu_vmotor(self):
        return TcuSimulator.IHK_PSU_VMOTOR

    def thk_psu_first(self):
        return TcuSimulator.THK_PSU_FIRST

    def thk_m2md_first(self):
        return TcuSimulator.THK_M2MD_FIRST

    def thk_psu_second(self):
        return TcuSimulator.THK_PSU_SECOND

    def thk_m2md_second(self):
        return TcuSimulator.THK_M2MD_SECOND

    def thk_cts_q1(self):
        return TcuSimulator.THK_CTS_Q1

    def thk_cts_q2(self):
        return TcuSimulator.THK_CTS_Q2

    def thk_cts_q3(self):
        return TcuSimulator.THK_CTS_Q3

    def thk_cts_q4(self):
        return TcuSimulator.THK_CTS_Q4

    def thk_cts_fpga(self):
        return TcuSimulator.THK_CTS_FPGA

    def thk_cts_ads1282(self):
        return TcuSimulator.THK_CTS_ADS1282

    def vhk_ths_ret(self):
        return TcuSimulator.VHK_THS_RET

    def hk_acq_counter(self):
        return TcuSimulator.HK_ACQ_COUNTER


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


class TcuHex(TcuInterface, DynamicCommandMixin):
    def __init__(self):
        super().__init__()
        self.transport = self.tcu = TcuHexInterface()
