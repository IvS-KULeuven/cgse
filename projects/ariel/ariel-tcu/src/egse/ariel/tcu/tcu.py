"""Ariel Telescope Control Unit (TCU) commanding.

Commanding is done by communicating with the TCU Arduino via a serial port (with the PySerial package).

We discern between the following types of commands:
    - General commands;
    - M2MD commands (on a per-axis basis);
    - Thermal Monitoring System (TSM) commands;
    - HK commands.

Reference documents:
    - RD01: TCU User Manual (ARIEL-IEEC-PL-TN-006), v1.2
    - RD02: ARIEL TCU Data Handling (ARIEL-IEEC-PL-TN-007), v1.0
    - RD02: TCU code provided by Vladimiro Noce (priv. comm.)
"""

from enum import IntEnum, StrEnum
from typing import Union

import crcmod
from serial.tools import list_ports
from egse.device import DeviceInterface
from egse.mixin import dynamic_command, CommandType
from egse.proxy import Proxy
from egse.ariel.tcu.tcu_devif import TcuDeviceInterface

TCU_LOGICAL_ADDRESS = "03"
DATA_LENGTH = "0004"


class PacketType(StrEnum):
    """Packet types (read/write).

    Reference document: ARIEL TCU Data Handling (ARIEL-IEEC-PL-TN-007), v1.0 -> Sect. 4.1
    """

    W = WRITE = "20"  # Write command (Sect. 4.1.1)
    R = READ = "40"  # Read command (Sect. 4.1.2)


class CommandAddress(StrEnum):
    """Identifier of the component of the TCU the commands have to be sent to."""

    GENERAL = "0000"  # General TCU commands
    M2MD_1 = "0001"  # M2MD axis-1 commands
    M2MD_2 = "0002"  # M2MD axis-2 commands
    M2MD_3 = "0003"  # M2MD axis-3 commands
    TSM = "0020"  # TSM commands
    HK = "0005"  # HK commands


class GeneralCommandIdentifier(StrEnum):
    """Identifiers for the general TCU commands."""

    TCU_FIRMWARE_ID = "0000"  # Read
    TCU_MODE = "0001"  # Read/Write
    TCU_STATUS = "0002"  # Read
    TCU_SIMULATED = "0003"  # Write
    RESTART_LINKS_PERIOD_LATCH = "0004"  # Write
    RESTART_LINKS_PERIOD = "0005"  # Read/Write


class M2MDCommandIdentifier(StrEnum):
    """Identifiers for the M2MD commands."""

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


# Combine all command identifiers into one big enumeration

CommandIdentifier = Union[GeneralCommandIdentifier, M2MDCommandIdentifier, TSMCommandIdentifier, HKCommandIdentifier]


class TcuMode(IntEnum):
    """Ariel TCU operating modes.

    Reference document: TCU User Manual (ARIEL-IEEC-PL-MAN-002), v1.1 -> Sect. 4.2
    """

    IDLE = 0x0000  # Waiting for commands, minimum power consumption
    BASE = 0x0001  # HK + TSM circuitry on
    CALIBRATION = 0x0003  # HK + TSM + M2MD circuitry on


class MotorState(IntEnum):
    """State of the M2MD motors.

    Reference document: TCU User Manual (ARIEL-IEEC-PL-MAN-002), v1.1 -> Sect. 5.1
    """

    STANDBY = 0x0001  # No motion
    OPERATION = 0x0010  # Motor moving


def create_write_cmd_string(
    transaction_id: int,
    cmd_address: CommandAddress | str,
    cmd_identifier: CommandIdentifier,
    cargo1: str = "0000",
    cargo2: str = "0000",
):
    """Creates a write-command string to send to the TCU Arduino.

    Args:
        transaction_id (int): Transaction identifier (i.e. counter that is incremented upon each command call).
        cmd_address (CommandAddress): Identifier of the commanded device.  In case of a M2MD axis, it is the reference
                                      to the axis (typically "${axis}") rather than the axis identifier enumeration.
        cmd_identifier (CommandIdentifier): Command identifier, internal to the commanded device.
        cargo1 (str): Reference to the first 16-bit cargo word (typically "${cargo1}").
        cargo2 (str): Reference to the second 16-bit cargo word (typically "${cargo2}").

    Returns:
        Write-command string to send to the TCU Arduino.
    """

    return create_cmd_string(PacketType.WRITE, transaction_id, cmd_address, cmd_identifier, cargo1, cargo2)


def create_read_cmd_string(
    transaction_id: int,
    cmd_address: CommandAddress | str,
    cmd_identifier: CommandIdentifier,
    cargo1: str = "0000",
    cargo2: str = "0000",
):
    """Creates a read-command string to send to the TCU Arduino.

    Args:
        transaction_id (int): Transaction identifier (i.e. counter that is incremented upon each command call).
        cmd_address (CommandAddress): Identifier of the commanded device.  In case of a M2MD axis, it is the reference
                                      to the axis (typically "${axis}") rather than the axis identifier enumeration.
        cmd_identifier (CommandIdentifier): Command identifier, internal to the commanded device.
        cargo1 (str): Reference to the first 16-bit cargo word (typically "${cargo1}").
        cargo2 (str): Reference to the second 16-bit cargo word (typically "${cargo2}").

    Returns:
        Read-command string to send to the TCU Arduino.
    """

    return create_cmd_string(PacketType.READ, transaction_id, cmd_address, cmd_identifier, cargo1, cargo2)


def create_cmd_string(
    packet_type: PacketType,
    transaction_id: int,
    cmd_address: CommandAddress | str,
    cmd_identifier: CommandIdentifier,
    cargo1: str = "0000",
    cargo2: str = "0000",
):
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
        - CRC: Cyclic Redundancy Check (CRC-16), determined from the packet string (without the CRC itself).

    Args:
        packet_type (PacketType): Type of the packet (read or write).
        transaction_id (int): Transaction identifier (i.e. counter that is incremented upon each command call).
        cmd_address (CommandAddress): Identifier of the commanded device.  In case of a M2MD axis, it is the reference
                                      to the axis (typically "${axis}") rather than the axis identifier enumeration.
        cmd_identifier (CommandIdentifier): Command identifier, internal to the commanded device.
        cargo1 (str): Reference to the first 16-bit cargo word (typically "${cargo1}").
        cargo2 (str): Reference to the second 16-bit cargo word (typically "${cargo2}").

    Returns:
        Command string to send to the TCU Arduino.
    """

    address = cmd_address.value if isinstance(cmd_address, CommandAddress) else cmd_address

    cmd_string = (
        f"{TCU_LOGICAL_ADDRESS}{packet_type.value} {hex(transaction_id)[2:].zfill(4)} {DATA_LENGTH} "
        f"{address} {cmd_identifier.value} {cargo1} {cargo2}"
    )
    # cmd_string = append_crc16(cmd_string)     # FIXME: CRC has to be added when the command string is complete

    return cmd_string


def process_general_kwargs(kv_pairs: dict):
    """Processes the keyword arguments for a general TCU command.

    Only write commands can have a single input argument, which has to be written to the `cargo2` part of the command
    string.  Note that the keyword in the given dictionary can have any name (so no necessarily `cargo2`).

    In this  function, we make sure that its value (which can be either a string or an integer) is converted into a hex
    string of four characters without the leading 0x.

    Args:
        kv_pairs (dict): Dictionary of keyword arguments for a general TCU write command.

    Returns:
        Dictionary of the processed keyword arguments.
    """

    for key, value in kv_pairs.items():
        # Cargo 2 -> Has to be hex strings of 4 characters without leading 0x

        if isinstance(value, int):
            value = hex(value)  # Integer -> Hex string
        if value.startswith("0x"):
            kv_pairs[key] = value[2:]  # Strip off leading 0x
        kv_pairs[key] = value.zfill(4)  # Ensure 4 characters

    return kv_pairs


def process_m2md_kwargs(kv_pairs: dict):
    """Processes the keyword arguments for an M2MD command.

    Read commands can ha a single input argument, which has to be written to the `cmd_address` part of the command
    string.  Write commands can have a two input arguments, which have to be written to the `cmd_address` and `cargo2`
    parts of the command string.  Note that the keywords in the given dictionary can have any name (so no necessarily
    `axis` and `cargo2`).

    In this function, we make sure that both values (which can be an enumeration, integer, or string) are converted into
    hex strings of four characters without leading 0x.

    Args:
        kv_pairs (dict): Dictionary of keyword arguments for an M2MD TCU write command.

    Returns:
        Dictionary of the processed keyword arguments.
    """

    for key, value in kv_pairs.items():
        if isinstance(value, CommandAddress):
            kv_pairs[key] = value.value  # Replaces the axis identifier with its enumeration value
            continue
        elif isinstance(value, int):
            value = hex(value)  # Integer -> Hex string
        if value.startswith("0x"):
            value = value[2:]  # Strip off leading 0x

            kv_pairs[key] = value.zfill(4)  # Ensure 4 characters

    return kv_pairs


def process_tsm_kwargs(kv_pairs: dict):
    """Processes the keyword arguments for a TSM command.

    Only write commands can have two input arguments, which have to be written to the `cargo1` and `cargo2` parts of the
    command string.  Note that the keywords in the given dictionary can have any name (so no necessarily `cargo1` and
    `cargo2`).

    In this function, we make sure that both values (which can be an integer or string) are converted into hex strings
    of four characters without leading 0x.

    Args:
        kv_pairs (dict): Dictionary of keyword arguments for a TSM TCU write command.

    Returns:
        Dictionary of the processed keyword arguments.
    """

    for key, value in kv_pairs.items():
        # Cargo 1 & 2 -> Have to be hex strings of 4 characters without leading 0x

        if isinstance(value, int):
            value = hex(value)  # Integer -> Hex string
        if value.startswith("0x"):
            value = value[2:]  # Strip off leading 0x
        kv_pairs[key] = value.zfill(4)  # Ensure 4 characters

    return kv_pairs


def create_crc16(cmd_str: str, ln: int = 14):
    """Calculates the 16-bit Cyclic Redundancy Check (CRC) checksum for the given command string.

    The CRC-16 is an error-detecting code that generates a 16-bit checksum to verify data integrity during
    transmission.  It works by performing a polynomial division (using XOR operations) on the data, with the remainder
    becoming the CRC checksum.  The receiver performs the same division: A zero remainder indicates the data arrived
    uncorrupted, while a non-zero remainder signals a potential error.

    Args:
        cmd_str (str): Command string for which the CRC will be calculated.
        ln (int): Number of bytes to include in the CRC calculation.

    Returns:
        Calculated 16-bit CRC checksum.
    """

    byte_array = bytearray([int(cmd_str[2 * i : 2 * i + 2], 16) for i in range(ln)])

    crc16_func = crcmod.mkCrcFun(0x11021, 0xFFFF, False, 0x0)
    crc16 = hex(crc16_func(byte_array))

    return crc16


def append_crc16(cmd_string: str, ln: int = 14):
    """Appends a 16-bit CRC checksum to the given command string.

    Args:
        cmd_string (str): Command string to which the CRC will be appended.
        ln (int): Number of bytes to include in the CRC calculation.

    Returns:
        str: Command string with the appended CRC checksum.
    """

    # Crop leading "0x" + ensure 4 characters

    crc16 = create_crc16(cmd_string, ln)[2:6].zfill(4)

    return f"{cmd_string} {crc16}"


def get_all_serial_ports() -> list:
    """Returns a list of all available serial ports.

    Returns:
        List of all available serial ports.
    """

    return list_ports.comports()


counter = 0


def increment_counter():
    """Increment the counter that is used as transaction identifier in the commands."""

    global counter
    counter += 1


class TcuInterface(DeviceInterface):
    # General commands

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.GENERAL, CommandIdentifier.TCU_FIRMWARE_ID),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tcu_firmware_id(self):
        """Selects the Instrument Control Unit (ICU) channel and returns the firmware version.

        Returns:
            Firmware version of the Ariel TCU.
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.GENERAL, CommandIdentifier.TCU_MODE),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
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

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, CommandAddress.GENERAL, CommandIdentifier.TCU_MODE, cargo2="${tcu_mode}"
        ),
        process_kwargs=process_general_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_tcu_mode(self, tcu_mode: TcuMode = TcuMode.IDLE):
        """Selects the Ariel TCU working mode.

        Args:
            tcu_mode (TcuMode): Ariel TCU working mode:
                - IDLE (0x0000): Waiting for commands, minimum power consumption
                - BASE (0x0001): HK + TSM Circuitry on
                - CALIBRATION (0x0003): HK + TSM + M2MD circuitry on
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.GENERAL, GeneralCommandIdentifier.TCU_STATUS),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tcu_status(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, CommandAddress.GENERAL, GeneralCommandIdentifier.TCU_SIMULATED, cargo2="${cargo2}"
        ),
        process_kwargs=process_general_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tcu_simulated(self, cargo2: str):
        # TODO How to pass the argument?
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, CommandAddress.GENERAL, GeneralCommandIdentifier.RESTART_LINKS_PERIOD_LATCH
        ),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def restart_links_period_latch(self, cargo2: str):
        # TODO How to pass the argument?
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(
            counter, CommandAddress.GENERAL, GeneralCommandIdentifier.RESTART_LINKS_PERIOD
        ),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_restart_links_period(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, CommandAddress.GENERAL, GeneralCommandIdentifier.RESTART_LINKS_PERIOD, cargo2="${link_period}"
        ),
        process_kwargs=process_general_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_restart_links_period(self, link_period: int = "0xFFFF"):
        # TODO How to pass the argument?
        pass

    # M2MD commands

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.OPE_MNG_COMMAND, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def ope_mng_command(self, axis: CommandAddress, cargo2: str = 0):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def ope_mng_event_clear_protect_flag(self, cargo2: str = 0):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def ope_mng_event_clear(self, axis: CommandAddress, cargo2: str = 0):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.OPE_MNG_STATUS),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def ope_mng_status(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.OPE_MNG_EVENT_REG),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def ope_mng_event_reg(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.ACQ_CURR_OFF_CORR),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_acq_curr_off_corr(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_CURR_OFF_CORR, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_acq_curr_off_corr(self, axis: CommandAddress, cargo2: str = 0):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_acq_curr_gain_corr(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_acq_curr_gain_corr(self, axis: CommandAddress, cargo2: str = 0):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.ACQ_AXIS_A_CURR_READ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_axis_a_curr_read(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.ACQ_AXIS_B_CURR_READ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_axis_b_curr_read(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_AVE_LPF_EN, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_ave_lpf_en(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_ovc_cfg_filter(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_AVC_FILT_TIME, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_avc_filt_time(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_AVERAGE_TYPE, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_average_type(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_spk_filt_counter_lim(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def acq_spk_filt_incr_thr(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.PROF_GEN_AXIS_STEP),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_prof_gen_axis_step(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.PROF_GEN_AXIS_STEP, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_prof_gen_axis_step(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_prof_gen_axis_speed(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
    )
    def set_prof_gen_axis_speed(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_prof_gen_axis_state_start(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, "${axis}", M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START, cargo2="${cargo2}"
        ),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_prof_gen_axis_state_start(self, axis: CommandAddress, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.SW_RS_XX_SW_RISE),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def sw_rs_xx_sw_rise(self, axis: CommandAddress):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, "${axis}", M2MDCommandIdentifier.SW_RS_XX_SW_FALL),
        process_kwargs=process_m2md_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def sw_rs_xx_sw_fall(self, axis: CommandAddress):
        pass

    # TSM commands

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_LATCH),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_latch(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_VALUE),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_tsm_current_value(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_VALUE, cargo1="${cargo1}", cargo2="${cargo2}"
        ),
        process_kwargs=process_tsm_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_tsm_current_value(self, cargo1: str, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_OFFSET),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_tsm_current_offset(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_CURRENT_OFFSET, cargo1="${cargo1}", cargo2="${cargo2}"
        ),
        process_kwargs=process_tsm_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_tsm_current_offset(self, cargo1: str, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_ID_REGISTER),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_id_register(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_CONFIGURATION_REGISTER
        ),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_configuration_register(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_HPF_REGISTER),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_tsm_adc_hpf_register(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter,
            CommandAddress.TSM,
            TSMCommandIdentifier.TSM_ADC_HPF_REGISTER,
            cargo1="${cargo1}",
            cargo2="${cargo2}",
        ),
        process_kwargs=process_tsm_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_tsm_adc_hpf_register(self, cargo1: str, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_OFC_REGISTER),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_tsm_adc_ofc_register(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_write_cmd_string(
            counter,
            CommandAddress.TSM,
            TSMCommandIdentifier.TSM_ADC_OFC_REGISTER,
            cargo1="${cargo1}",
            cargo2="${cargo2}",
        ),
        process_kwargs=process_tsm_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_tsm_adc_ofc_register(self, cargo1: str, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_FSC_REGISTER),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def get_tsm_adc_fsc_register(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(
            counter,
            CommandAddress.TSM,
            TSMCommandIdentifier.TSM_ADC_FSC_REGISTER,
            cargo1="${cargo1}",
            cargo2="${cargo2}",
        ),
        process_kwargs=process_tsm_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def set_tsm_adc_fsc_register(self, cargo1: str, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_COMMAND_LATCH),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_command_latch(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(
            counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_COMMAND, cargo1="${cargo1}", cargo2="${cargo2}"
        ),
        process_kwargs=process_tsm_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_command(self, cargo1: str, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(
            counter,
            CommandAddress.TSM,
            TSMCommandIdentifier.TSM_ADC_CALIBRATION,
            cargo1="${cargo1}",
            cargo2="${cargo2}",
        ),
        process_kwargs=process_tsm_kwargs,
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_calibration(self, cargo1: str, cargo2: str):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_VALUE_XX_CURRENTN),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_value_xx_currentn(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_VALUE_XX_BIASN),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_value_xx_biasn(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_VALUE_XX_CURRENTP),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_value_xx_currentp(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ADC_VALUE_XX_BIASP),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_adc_value_xx_biasp(self):
        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=create_read_cmd_string(counter, CommandAddress.TSM, TSMCommandIdentifier.TSM_ACQ_COUNTER),
        process_cmd_string=append_crc16,
        post_cmd=increment_counter,
    )
    def tsm_acq_counter(self):
        pass


class TcuController(TcuInterface):
    def __init__(self):
        """Initialisation of an Ariel TCU controller."""

        super().__init__()

        self.tcu = TcuDeviceInterface()

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


class TcuSimulator(TcuInterface):
    def __init__(self):
        super().__init__()
        self._is_connected = True

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


class TcuProxy(Proxy, TcuInterface):
    # TODO
    pass
