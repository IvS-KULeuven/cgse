""" Utility functions to build the TCU command strings.

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

from enum import StrEnum
import crcmod

from egse.ariel.tcu import TcuMode
from egse.decorators import static_vars

TCU_LOGICAL_ADDRESS = "03"  # RD02 -> Fig. 10
DATA_LENGTH = "0004"  # Vladimiro's code


class PacketType(StrEnum):
    """Packet types (read/write)."""

    W = WRITE = "20"  # Write command (RD02 -> Sect. 4.1.1)
    R = READ = "40"  # Read command (RD02 -> Sect. 4.1.2)


class CommandAddress(StrEnum):
    """Identifiers of the components of the TCU the commands have to be sent to."""

    # Adopted from Vladimiro's code

    GENERAL = "0000"  # General TCU commands -> see `show_messageGEN`, where the command string is built
    M2MD_1 = "0001"  # M2MD axis-1 commands -> see `show_messageM2M`, where the command string is built
    M2MD_2 = "0002"  # M2MD axis-2 commands -> see `show_messageM2M`, where the command string is built
    M2MD_3 = "0003"  # M2MD axis-3 commands -> see `show_messageM2M`, where the command string is built
    TSM = "0004"  # TSM commands -> see `show_messageTSM`, where the command string is built
    HK = "0005"  # HK commands -> see `show_messageHK`, where the command string is built


#####################
# Command identifiers
#####################


class GeneralCommandIdentifier(StrEnum):
    """Identifiers for the general TCU commands."""

    # Adopted from Vladimiro's code

    TCU_FIRMWARE_ID = "0000"  # Read
    TCU_MODE = "0001"  # Read/Write
    TCU_STATUS = "0002"  # Read
    TCU_SIMULATED = "0003"  # Write
    RESTART_LINKS_PERIOD_LATCH = "0004"  # Write
    RESTART_LINKS_PERIOD = "0005"  # Read/Write


class M2MDCommandIdentifier(StrEnum):
    """Identifiers for the M2MD commands."""

    # Adopted from Vladimiro's code

    OPE_MNG_COMMAND = "0000"  # Write
    OPE_MNG_EVENT_CLEAR_PROTECT_FLAG = "0001"  # Write
    OPE_MNG_EVENT_CLEAR = "0002"  # Write
    OPE_MNG_STATUS = "0003"  # Read
    OPE_MNG_EVENT_REG = "0004"  # Read
    ACQ_CURR_OFF_CORR = "1000"  # Read/Write
    ACQ_CURR_GAIN_CORR = "1001"  # Read/Write
    ACQ_AXIS_A_CURR_READ = "1002"  # Read
    ACQ_AXIS_B_CURR_READ = "1003"  # Read
    ACQ_AVE_LPF_EN = "1004"  # Write
    ACQ_OVC_CFG_FILTER = "1005"  # Write
    ACQ_AVC_FILT_TIME = "1006"  # Write
    ACQ_AVERAGE_TYPE = "1007"  # Write
    ACQ_SPK_FILT_COUNTER_LIM = "1008"  # Write
    ACQ_SPK_FILT_INCR_THR = "1009"  # Write
    PROF_GEN_AXIS_STEP = "2000"  # Read/Write
    PROF_GEN_AXIS_SPEED = "2001"  # Read/Write
    PROF_GEN_AXIS_STATE_START = "2002"  # Read/Write
    SW_RS_XX_SW_RISE = "3001"  # Read
    # TODO Check whether this is correct:
    # This is how it is hard-coded in Vladimiro's code, but in his `show_messageM2M` function, he states that there's
    # an offset of 20 between SW_RS_XX_SW_RISE and SW_RS_XX_SW_FALL (where position must in 1,...,20).  That would mean
    # that for position 15, SW_RS_XX_SW_RISE is 3015, which clashes with the hard-coded value for
    # SW_RS_XX_SW_FALL.
    SW_RS_XX_SW_FALL = "3015"  # Read


class TSMCommandIdentifier(StrEnum):
    """Identifiers for the TSM commands."""

    TSM_LATCH = "0000"  # Write
    TSM_CURRENT_VALUE = "0001"  # Read/Write
    TSM_CURRENT_OFFSET = "0002"  # Read/Write
    TSM_ADC_REGISTER_LATCH = "1000"  # Write
    TSM_ADC_ID_REGISTER = "1001"  # Read
    TSM_ADC_CONFIGURATION_REGISTER = "1002"  # Read
    TSM_ADC_HPF_REGISTER = "1003"  # Read/Write
    TSM_ADC_OFC_REGISTER = "1004"  # Read/Write
    TSM_ADC_FSC_REGISTER = "1006"  # Read/Write
    TSM_ADC_COMMAND_LATCH = "1008"  # Write
    TSM_ADC_COMMAND = "1009"  # Write
    TSM_ADC_CALIBRATION = "100A"  # Write
    TSM_ADC_VALUE_XX_CURRENTN = "2000"  # Read
    TSM_ADC_VALUE_XX_BIASN = "2001"  # Read
    TSM_ADC_VALUE_XX_CURRENTP = "2002"  # Read
    TSM_ADC_VALUE_XX_BIASP = "2003"  # Read
    TSM_ACQ_COUNTER = "20C0"  # Read


class HKCommandIdentifier(StrEnum):
    """Identifiers for the HK commands."""

    # Adopted from Vladimiro's code

    VHK_PSU_VMOTOR = "0000"  # Read
    VHK_PSU_VHI = "0001"  # Read
    VHK_PSU_VLOW = "0002"  # Read
    VHK_PSU_VMEDP = "0003"  # Read
    VHK_PSU_VMEDN = "0004"  # Read
    IHK_PSU_VMEDN = "0005"  # Read
    IHK_PSU_VMEDP = "0006"  # Read
    IHK_PSU_VLOW = "0007"  # Read
    IHK_PSU_VHI = "0008"  # Read
    IHK_PSU_VMOTOR = "0009"  # Read
    THK_PSU_FIRST = "000A"  # Read
    THK_M2MD_FIRST = "000B"  # Read
    THK_PSU_SECOND = "000C"  # Read
    THK_M2MD_SECOND = "000D"  # Read
    THK_CTS_Q1 = "000E"  # Read
    THK_CTS_Q2 = "000F"  # Read
    THK_CTS_Q3 = "0010"  # Read
    THK_CTS_Q4 = "0011"  # Read
    THK_CTS_FPGA = "0012"  # Read
    THK_CTS_ADS1282 = "0013"  # Read
    VHK_THS_RET = "0014"  # Read
    HK_ACQ_COUNTER = "0015"  # Read


def get_tsm_adc_value_xx_currentn_cmd_id(probe: int) -> str:
    """Determines the command identifier for the TSM_ADC_VALUE_XX_CURRENTN for the given probe.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command identifier for the TSM_ADC_VALUE_XX_CURRENTN for the given probe.
    """

    return get_tsm_adc_value_xx_cmd_id(TSMCommandIdentifier.TSM_ADC_VALUE_XX_CURRENTN, probe)


def get_tsm_adc_value_xx_biasn_cmd_id(probe: int) -> str:
    """Determines the command identifier for the TSM_ADC_VALUE_XX_BIASN for the given probe.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command identifier for the TSM_ADC_VALUE_XX_BIASN for the given probe.
    """

    return get_tsm_adc_value_xx_cmd_id(TSMCommandIdentifier.TSM_ADC_VALUE_XX_BIASN, probe)


def get_tsm_adc_value_xx_currentp_cmd_id(probe: int) -> str:
    """Determines the command identifier for the TSM_ADC_VALUE_XX_CURRENTP for the given probe.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command identifier for the TSM_ADC_VALUE_XX_CURRENTP for the given probe.
    """

    return get_tsm_adc_value_xx_cmd_id(TSMCommandIdentifier.TSM_ADC_VALUE_XX_CURRENTP, probe)


def get_tsm_adc_value_xx_biasp_cmd_id(probe: int) -> str:
    """Determines the command identifier for the TSM_ADC_VALUE_XX_BIASP for the given probe.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command identifier for the TSM_ADC_VALUE_XX_BIASP for the given probe.
    """

    return get_tsm_adc_value_xx_cmd_id(TSMCommandIdentifier.TSM_ADC_VALUE_XX_BIASP, probe)


def get_tsm_adc_value_xx_cmd_id(tsm_cmd_id: TSMCommandIdentifier | str, probe: int):
    """Determines the command identifier for the given TSM_ADC_VALUE_XX for the given probe.

    Args:
        tsm_cmd_id (TSMCommandIdentifier | str): TSM command identifier.
        probe (int): Thermistor identifier.

    Returns:
        Command identifier for the
        TSM_ADC_VALUE_XX_CURRENTN/TSM_ADC_VALUE_XX_BIASN/TSM_ADC_VALUE_XX_CURRENTP/TSM_ADC_VALUE_XX_BIASP for the given
        probe.
    """

    # Adopted from Vladimiro's code
    return tsm_cmd_id.value[:2] + hex(probe * 4 + int(tsm_cmd_id.value[-1]))[2:].zfill(2)


def get_sw_rs_xx_sw_cmd_id(cmd_identifier: M2MDCommandIdentifier, position: int) -> str:
    """Determines the command identifier for the given SW_RS_XX_SW for the given probe.

    Args:
        cmd_identifier (M2MDCommandIdentifier): TSM command identifier.
        position (int):

    Returns:
        Command identifier for the SW_RS_XX_SW_RISE/SW_RS_XX_SW_FALL for the given probe.
    """

    # Adopted from Vladimiro's code
    return f"{cmd_identifier.value[:2]}{hex(position)[2:].zfill(2)}"


##############################
# Building the command strings
##############################


def format_value(value: int | str | StrEnum) -> str:
    """Formats the given value to a 4-digit hex string without leading "0x".

    Args:
        value (int | str | StrEnum): Value to format.

    Returns:
        str: Formatted value.
    """

    if isinstance(value, StrEnum):
        value = value.value
    if isinstance(value, int):
        value = hex(value)  # Integer -> Hex string
    if value.startswith("0x"):  # Strip off leading 0x
        value = value[2:]
    return value.zfill(4)


def _create_write_cmd_string(
    cmd_address: CommandAddress | str,
    cmd_identifier: GeneralCommandIdentifier | TSMCommandIdentifier | M2MDCommandIdentifier | HKCommandIdentifier | str,
    cargo1: str = "0000",
    cargo2: str = "0000",
) -> str:
    """Creates a write-command string to send to the TCU Arduino.

    Note that this function should not be called directly in the `@dynamic_command` decorator (in the `cmd_string`
    attribute), as this will increase the transaction identifier without actually calling the function (merely
    importing the interface in which such a decorator call is made will increase the transaction identifier)..

    Args:
        cmd_address (CommandAddress): Identifier of the commanded device.  In case of a M2MD axis, it is the reference
                                      to the axis (typically "{axis:04x}") rather than the axis identifier enumeration.
        cmd_identifier (GeneralCommandIdentifier | TSMCommandIdentifier | M2MDCommandIdentifier | HKCommandIdentifier):
                       Command identifier, internal to the commanded device.
        cargo1 (str): Reference to the first 16-bit cargo word (typically "{cargo1:04x}").  The exact value will be
                      filled out upon command execution.
        cargo2 (str): Reference to the second 16-bit cargo word (typically "{cargo2:04x}").  The exact value will be
                      filled out upon command execution.

    Returns:
        Write-command string to send to the TCU Arduino.
    """

    return _create_cmd_string(PacketType.WRITE, cmd_address, cmd_identifier, cargo1, cargo2)


def _create_read_cmd_string(
    cmd_address: CommandAddress | str,
    cmd_identifier: GeneralCommandIdentifier | TSMCommandIdentifier | M2MDCommandIdentifier | HKCommandIdentifier | str,
    cargo1: str = "0000",
    cargo2: str = "0000",
) -> str:
    """Creates a read-command string to send to the TCU Arduino.

    Note that this function should not be called directly in the `@dynamic_command` decorator (in the `cmd_string`
    attribute), as this will increase the transaction identifier without actually calling the function (merely
    importing the interface in which such a decorator call is made will increase the transaction identifier)..

    Args:
        cmd_address (CommandAddress): Identifier of the commanded device.  In case of a M2MD axis, it is the reference
                                      to the axis (typically "${axis}") rather than the axis identifier enumeration.
        cmd_identifier (GeneralCommandIdentifier | TSMCommandIdentifier | M2MDCommandIdentifier | HKCommandIdentifier):
                       Command identifier, internal to the commanded device.
        cargo1 (str): Reference to the first 16-bit cargo word (typically "${cargo1}").  The exact value will be filled
                      out upon command execution.
        cargo2 (str): Reference to the second 16-bit cargo word (typically "${cargo2}").  The exact value will be filled
                      out upon command execution.

    Returns:
        Read-command string to send to the TCU Arduino.
    """

    return _create_cmd_string(PacketType.READ, cmd_address, cmd_identifier, cargo1, cargo2)


@static_vars(transaction_id=-1)
def _create_cmd_string(
    packet_type: PacketType,
    cmd_address: CommandAddress | str,
    cmd_identifier: GeneralCommandIdentifier | TSMCommandIdentifier | M2MDCommandIdentifier | HKCommandIdentifier | str,
    cargo1: str = "0000",
    cargo2: str = "0000",
) -> str:
    """Creates a command string to send to the TCU Arduino.

    Packet format (text):
        "03XX TTTT 0004 AAAA BBBB CCCC DDDD CRC"
    with:
        - 03: TCU logical address;
        - XX: Indicates whether it's a read (40) or write (20) command (without reply);
        - TTTT: Transaction identifier (basically a counter that increments for each command call);
        - 0004: Data length (always 4 bytes);
        - AAAA: Identifier of the commanded device:
            - 0000: General commands;
            - 0001: M2MD axis-1 commands;
            - 0002: M2MD axis-2 commands;
            - 0003: M2MD axis-3 commands;
            - 0020: TSM commands;
        - BBBB: Command identifier, internal to the commanded device;
        - CCCC: First 16-bit cargo word;
        - DDDD: Second 16-bit cargo word;
        - CRC: Cyclic Redundancy Check (CRC-16), determined from the packet string.

    Note that this function should not be called directly in the `@dynamic_command` decorator (in the `cmd_string`
    attribute), as this will increase the transaction identifier without actually calling the function (merely
    importing the interface in which such a decorator call is made will increase the transaction identifier)..

    Args:
        packet_type (PacketType): Type of the packet (read or write).
        cmd_address (CommandAddress): Identifier of the commanded device.  In case of a M2MD axis, it is the reference
                                      to the axis (typically "${axis}") rather than the axis identifier enumeration.
        cmd_identifier (GeneralCommandIdentifier | TSMCommandIdentifier | M2MDCommandIdentifier | HKCommandIdentifier
                       | str): Command identifier, internal to the commanded device.
        cargo1 (str): Reference to the first 16-bit cargo word (typically "${cargo1}").  The exact value will be filled
                      out upon command execution.
        cargo2 (str): Reference to the second 16-bit cargo word (typically "${cargo2}").  The exact value will be filled
                      out upon command execution.

    Returns:
        Command string to send to the TCU Arduino.
    """

    _create_cmd_string.transaction_id += 1

    # Adopted from Vladimiro's code

    address = format_value(cmd_address)
    cmd_identifier = format_value(cmd_identifier)
    cargo1 = format_value(cargo1)
    cargo2 = format_value(cargo2)

    transaction_id = hex(_create_cmd_string.transaction_id)[2:].zfill(4)

    cmd_string = (
        f"{TCU_LOGICAL_ADDRESS}{packet_type.value} {transaction_id} {DATA_LENGTH} "
        f"{address} {cmd_identifier} {cargo1} {cargo2}"
    )

    cmd_string = append_crc16(cmd_string)
    return cmd_string


def create_crc16(cmd_str: str, ln: int = 14) -> str:
    """Calculates the 16-bit Cyclic Redundancy Check (CRC) checksum for the given command string.

    The CRC-16 is an error-detecting code that generates a 16-bit checksum to verify data integrity during
    transmission.  It works by performing a polynomial division (using XOR operations) on the data, with the remainder
    becoming the CRC checksum.  The receiver performs the same division: A zero remainder indicates the data arrived
    uncorrupted, while a non-zero remainder signals a potential error.

    The leading "0x" is stripped off and the CRC is padded with leading zeros to ensure it is always 4 characters long.

    Args:
        cmd_str (str): Command string for which the CRC will be calculated.
        ln (int): Number of bytes to include in the CRC calculation.

    Returns:
        Calculated 16-bit CRC checksum.
    """

    # Adapted from Vladimiro's code

    byte_array = bytearray([int(cmd_str[2 * i : 2 * i + 2], 16) for i in range(ln)])

    crc16_func = crcmod.mkCrcFun(0x11021, 0xFFFF, False, 0x0)
    crc16 = hex(crc16_func(byte_array))

    crc16 = crc16[2:6].zfill(4)  # Crop leading "0x" + ensure 4 characters

    return crc16


def append_crc16(cmd_string: str, ln: int = 14) -> str:
    """Appends a 16-bit CRC checksum to the given command string.

    Args:
        cmd_string (str): Command string to which the CRC will be appended.
        ln (int): Number of bytes to include in the CRC calculation.

    Returns:
        Command string with the appended CRC checksum.
    """

    crc16 = create_crc16(cmd_string, ln)

    return f"{cmd_string} {crc16}"


# General commands


def tcu_firmware_id() -> str:
    """Builds the command string for the general TCU_FIRMWARE_ID read command.

    Returns:
        Command string for the general TCU_FIRMWARE_ID read command.
    """

    return _create_read_cmd_string(CommandAddress.GENERAL, GeneralCommandIdentifier.TCU_FIRMWARE_ID)


def get_tcu_mode() -> str:
    """Builds the command string for the general TCU_MODE read command.

    Returns:
        Command string for the general TCU_MODE read command.
    """

    return _create_read_cmd_string(CommandAddress.GENERAL, GeneralCommandIdentifier.TCU_MODE)


def set_tcu_mode(tcu_mode: TcuMode | str | int = TcuMode.IDLE):
    """Builds the command string for the general TCU_MODE write command.

    Args:
        tcu_mode (TcuMode | str | int): TCU mode.

    Returns:
        Command string for the general TCU_MODE write command.
    """

    return _create_write_cmd_string(CommandAddress.GENERAL, GeneralCommandIdentifier.TCU_MODE, cargo2=tcu_mode)


def tcu_status() -> str:
    """Builds the command string for the general TCU_STATUS read command.

    Returns:
        Command string for the general TCU_STATUS read command.
    """

    return _create_read_cmd_string(CommandAddress.GENERAL, GeneralCommandIdentifier.TCU_STATUS)


def tcu_simulated(cargo2: str | int):
    """Builds the command string for the general TCU_SIMULATED write command.

    Args:
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the general TCU_SIMULATED write command.
    """

    return _create_write_cmd_string(CommandAddress.GENERAL, GeneralCommandIdentifier.TCU_SIMULATED, cargo2=cargo2)


def restart_links_period_latch(cargo2: str | int):
    """Builds the command string for the general RESTART_LINKS_PERIOD_LATCH write command.

    Args:
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the general RESTART_LINKS_PERIOD_LATCH write command.
    """

    return _create_write_cmd_string(
        CommandAddress.GENERAL, GeneralCommandIdentifier.RESTART_LINKS_PERIOD_LATCH, cargo2=cargo2
    )


def get_restart_links_period() -> str:
    """Builds the command string for the general RESTART_LINKS_PERIOD_LATCH read command.

    Returns:
        Command string for the general RESTART_LINKS_PERIOD_LATCH read command.
    """

    return _create_read_cmd_string(CommandAddress.GENERAL, GeneralCommandIdentifier.RESTART_LINKS_PERIOD)


def set_restart_links_period(link_period: str | int = "0xFFFF") -> str:
    """Builds the command string for the general RESTART_LINKS_PERIOD write command.

    Args:
        link_period (str | int): Link period.

    Returns:
        Command string for the general RESTART_LINKS_PERIOD write command.
    """

    return _create_write_cmd_string(
        CommandAddress.GENERAL,
        GeneralCommandIdentifier.RESTART_LINKS_PERIOD,
        cargo2=link_period,
    )


# M2MD commands


def ope_mng_command(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string fort he M2MD OPE_MNG_COMMAND write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD OPE_MNG_COMMAND write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.OPE_MNG_COMMAND, cargo2=cargo2)


def ope_mng_event_clear_protect_flag(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD OPE_MNG_EVENT_CLEAR_PROTECT_FLAG write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD OPE_MNG_EVENT_CLEAR_PROTECT_FLAG write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG, cargo2=cargo2)


def ope_mng_event_clear(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD OPE_MNG_EVENT_CLEAR write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD OPE_MNG_EVENT_CLEAR write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR, cargo2=cargo2)


def ope_mng_status(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD OPE_MNG_STATUS read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD OPE_MNG_STATUS read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.OPE_MNG_STATUS)


def ope_mng_event_reg(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD OPE_MNG_EVENT_REG read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD OPE_MNG_EVENT_REG read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.OPE_MNG_EVENT_REG)


def get_acq_curr_off_corr(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD ACQ_CURR_OFF_CORR read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD ACQ_CURR_OFF_CORR read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.ACQ_CURR_OFF_CORR)


def set_acq_curr_off_corr(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD ACQ_CURR_OFF_CORR write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_CURR_OFF_CORR write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_CURR_OFF_CORR, cargo2=cargo2)


def get_acq_curr_gain_corr(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD ACQ_CURR_GAIN_CORR read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD ACQ_CURR_GAIN_CORR read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR)


def set_acq_curr_gain_corr(axis: CommandAddress | str | int, cargo2: str | int = 0):
    """Builds the command string for the M2MD ACQ_CURR_GAIN_CORR write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_CURR_GAIN_CORR write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR, cargo2=cargo2)


def acq_axis_a_curr_read(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD ACQ_AXIS_A_CURR_READ read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD ACQ_AXIS_A_CURR_READ read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.ACQ_AXIS_A_CURR_READ)


def acq_axis_b_curr_read(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD ACQ_AXIS_B_CURR_READ read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD ACQ_AXIS_B_CURR_READ read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.ACQ_AXIS_B_CURR_READ)


def acq_ave_lpf_en(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD ACQ_AVE_LPF_EN write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_AVE_LPF_EN write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_AVE_LPF_EN, cargo2=cargo2)


def acq_ovc_cfg_filter(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD ACQ_OVC_CFG_FILTER write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_OVC_CFG_FILTER write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER, cargo2=cargo2)


def acq_avc_filt_time(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD ACQ_AVC_FILT_TIME write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_AVC_FILT_TIME write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_AVC_FILT_TIME, cargo2=cargo2)


def acq_average_type(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD ACQ_AVERAGE_TYPE write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_AVERAGE_TYPE write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_AVERAGE_TYPE, cargo2=cargo2)


def acq_spk_filt_counter_lim(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD ACQ_SPK_FILT_COUNTER_LIM write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_SPK_FILT_COUNTER_LIM write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM, cargo2=cargo2)


def acq_spk_filt_incr_thr(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD ACQ_SPK_FILT_INCR_THR write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD ACQ_SPK_FILT_INCR_THR write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR, cargo2=cargo2)


def get_prof_gen_axis_step(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD PROF_GEN_AXIS_STEP read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD PROF_GEN_AXIS_STEP read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.PROF_GEN_AXIS_STEP)


def set_prof_gen_axis_step(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD PROF_GEN_AXIS_STEP write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD PROF_GEN_AXIS_STEP write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.PROF_GEN_AXIS_STEP, cargo2=cargo2)


def get_prof_gen_axis_speed(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD PROF_GEN_AXIS_SPEED read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD PROF_GEN_AXIS_SPEED read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED)


def set_prof_gen_axis_speed(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD PROF_GEN_AXIS_SPEED write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD PROF_GEN_AXIS_SPEED write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED, cargo2=cargo2)


def get_prof_gen_axis_state_start(axis: CommandAddress | str | int) -> str:
    """Builds the command string for the M2MD PROF_GEN_AXIS_STATE_START read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.

    Returns:
        Command string for the M2MD PROF_GEN_AXIS_STATE_START read command.
    """

    return _create_read_cmd_string(axis, M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START)


def set_prof_gen_axis_state_start(axis: CommandAddress | str | int, cargo2: str | int = 0) -> str:
    """Builds the command string for the M2MD PROF_GEN_AXIS_STATE_START write command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the M2MD PROF_GEN_AXIS_STATE_START write command.
    """

    return _create_write_cmd_string(axis, M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START, cargo2=cargo2)


def sw_rs_xx_sw_rise(axis: CommandAddress | str | int, position: int) -> str:
    """Builds the command string for the M2MD SW_RS_XX_SW_RISE read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        position (int): Position of the SW_RS_XX_SW_RISE command.

    Returns:
        Command string for the M2MD SW_RS_XX_SW_RISE read command.
    """

    # Adopted from Vladimiro's code
    m2md_cmd_id = get_sw_rs_xx_sw_cmd_id(M2MDCommandIdentifier.SW_RS_XX_SW_RISE, position)

    return _create_read_cmd_string(axis, cmd_identifier=m2md_cmd_id)


def sw_rs_xx_sw_fall(axis: CommandAddress | str | int, position: int) -> str:
    """Builds the command string for the M2MD SW_RS_XX_SW_FALL read command.

    Args:
        axis (CommandAddress | str | int): Axis to which the command is sent.
        position (int): Position of the SW_RS_XX_SW_FALL command.

    Returns:
        Command string for the M2MD SW_RS_XX_SW_FALL read command.
    """

    # Adopted from Vladimiro's code
    offset_position = position + 21
    m2md_cmd_id = get_sw_rs_xx_sw_cmd_id(M2MDCommandIdentifier.SW_RS_XX_SW_FALL, offset_position)

    return _create_read_cmd_string(axis, cmd_identifier=m2md_cmd_id)


# TSM commands


def tsm_latch(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_LATCH write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_LATCH write command.
    """

    return _create_write_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_LATCH, cargo1=cargo1, cargo2=cargo2)


def get_tsm_current_value() -> str:
    """Builds the command string for the TSM TSM_CURRENT_VALUE read command.

    Returns:
        Command string for the TSM TSM_CURRENT_VALUE read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_VALUE)


def set_tsm_current_value(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_CURRENT_VALUE write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_CURRENT_VALUE write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_VALUE, cargo1=cargo1, cargo2=cargo2
    )


def get_tsm_current_offset() -> str:
    """Builds the command string for the TSM TSM_CURRENT_OFFSET read command.

    Returns:
        Command string for the TSM TSM_CURRENT_OFFSET read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_OFFSET)


def set_tsm_current_offset(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_CURRENT_OFFSET write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_CURRENT_OFFSET write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_OFFSET, cargo1=cargo1, cargo2=cargo2
    )


def tsm_adc_register_latch(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_ADC_REGISTER_LATCH write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_ADC_REGISTER_LATCH write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_REGISTER_LATCH, cargo1=cargo1, cargo2=cargo2
    )


def tsm_adc_id_register() -> str:
    """Builds the command string for the TSM TSM_ADC_ID_REGISTER read command.

    Returns:
        Command string for the TSM TSM_ADC_ID_REGISTER read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_ID_REGISTER)


def tsm_adc_configuration_register() -> str:
    """Builds the command string for the TSM TSM_ADC_CONFIGURATION_REGISTER read command.

    Returns:
        Command string for the TSM TSM_ADC_CONFIGURATION_REGISTER read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_CONFIGURATION_REGISTER)


def get_tsm_adc_hpf_register() -> str:
    """Builds the command string for the TSM TSM_ADC_HPF_REGISTER read command.

    Returns:
        Command string for the TSM TSM_ADC_HPF_REGISTER read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_HPF_REGISTER)


def set_tsm_adc_hpf_register(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_ADC_HPF_REGISTER write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_ADC_HPF_REGISTER write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_HPF_REGISTER, cargo1=cargo1, cargo2=cargo2
    )


def get_tsm_adc_ofc_register() -> str:
    """Builds the command string for the TSM TSM_ADC_OFC_REGISTER read command.

    Returns:
        Command string for the TSM TSM_ADC_OFC_REGISTER read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_OFC_REGISTER)


def set_tsm_adc_ofc_register(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_ADC_OFC_REGISTER write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_ADC_OFC_REGISTER write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_OFC_REGISTER, cargo1=cargo1, cargo2=cargo2
    )


def get_tsm_adc_fsc_register() -> str:
    """Builds the command string for the TSM TSM_ADC_FSC_REGISTER read command.

    Returns:
        Command string for the TSM TSM_ADC_FSC_REGISTER read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_FSC_REGISTER)


def set_tsm_adc_fsc_register(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_ADC_FSC_REGISTER write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_ADC_FSC_REGISTER write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_FSC_REGISTER, cargo1=cargo1, cargo2=cargo2
    )


def tsm_adc_command_latch(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_ADC_COMMAND_LATCH write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_ADC_COMMAND_LATCH write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_COMMAND_LATCH, cargo1=cargo1, cargo2=cargo2
    )


def tsm_adc_command(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_ADC_COMMAND write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_ADC_COMMAND write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_COMMAND, cargo1=cargo1, cargo2=cargo2
    )


def tsm_adc_calibration(cargo1: str | int, cargo2: str | int) -> str:
    """Builds the command string for the TSM TSM_ADC_CALIBRATION write command.

    Args:
        cargo1 (str | int): Cargo 1 part of the command string.
        cargo2 (str | int): Cargo 2 part of the command string.

    Returns:
        Command string for the TSM TSM_ADC_CALIBRATION write command.
    """

    return _create_write_cmd_string(
        CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_CALIBRATION, cargo1=cargo1, cargo2=cargo2
    )


def tsm_adc_value_xx_currentn(probe: int) -> str:
    """Builds the command string for the TSM TSM_ADC_VALUE_XX_CURRENTN read command.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command string for the TSM TSM_ADC_VALUE_XX_CURRENTN read command.
    """

    tsm_cmd_id = get_tsm_adc_value_xx_currentn_cmd_id(probe)

    return _create_read_cmd_string(CommandAddress.TSM, tsm_cmd_id)


def tsm_adc_value_xx_biasn(probe: int):
    """Builds the command string for the TSM TSM_ADC_VALUE_XX_BIASN read command.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command string for the TSM TSM_ADC_VALUE_XX_BIASN read command.
    """

    tsm_cmd_id = get_tsm_adc_value_xx_biasn_cmd_id(probe)

    return _create_read_cmd_string(CommandAddress.TSM, tsm_cmd_id)


def tsm_adc_value_xx_currentp(probe: int) -> str:
    """Builds the command string for the TSM TSM_ADC_VALUE_XX_CURRENTP read command.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command string for the TSM TSM_ADC_VALUE_XX_CURRENTP read command.
    """

    tsm_cmd_id = get_tsm_adc_value_xx_currentp_cmd_id(probe)

    return _create_read_cmd_string(CommandAddress.TSM, tsm_cmd_id)


def tsm_adc_value_xx_biasp(probe: int) -> str:
    """Builds the command string for the TSM TSM_ADC_VALUE_XX_BIASP read command.

    Args:
        probe (int): Thermistor identifier.

    Returns:
        Command string for the TSM TSM_ADC_VALUE_XX_BIASP read command.
    """

    tsm_cmd_id = get_tsm_adc_value_xx_biasp_cmd_id(probe)

    return _create_read_cmd_string(CommandAddress.TSM, tsm_cmd_id)


def tsm_acq_counter() -> str:
    """Builds the command string for the TSM TSM_ACQ_COUNTER read command.

    Returns:
        Command string for the TSM TSM_ACQ_COUNTER read command.
    """

    return _create_read_cmd_string(CommandAddress.TSM, TSMCommandIdentifier.TSM_ACQ_COUNTER)
