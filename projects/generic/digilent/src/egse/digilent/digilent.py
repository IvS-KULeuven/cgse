import datetime
import logging
import re
import struct

from navdict import navdict

from egse.device import DeviceInterface
from egse.digilent.measurpoint.digilent_devif import DigilentEthernetInterface
from egse.mixin import dynamic_command, CommandType, add_lf, DynamicCommandMixin
from egse.setup import load_setup, Setup

logger = logging.getLogger("egse.digilent.digilent")


class ScanRecord:
    def __init__(self, timestamp_s: int, timestamp_ms: int, scan_index: int, num_values: int, values: list[float]):
        """Initialisation of a scan record.

        Depending on the configuration of the channel(s), the values are expressed in °C, Ω, or V.

        Args:
            timestamp_s (int): Timestamp of the scan records, defined as the number of seconds that have elapsed since
                            Coordinated Universal Time (UTC).
            timestamp_ms (int): Number of milliseconds after `timestamp_s` at which the sample was acquired.
            scan_index (int): Index of the scan record in the circular buffer.
            num_values (int): Number of single-precision values that follow in the record.
            values (list[float]): Variable size array with a value from each channel that was specified in the channel
                                  list.
        """

        self._timestamp_s = timestamp_s
        self._timestamp_ms = timestamp_ms
        self._scan_index = scan_index
        self._num_values = num_values
        self._values = values

    @property
    def timestamp(self) -> float:
        """Returns the timestamp of the scan records, defined as the number of seconds that have elapsed since UTC.

        Returns:
            Timestamp of the scan records, defined as the number of seconds that have elapsed since UTC.
        """

        return self._timestamp_s + self._timestamp_ms / 1000

    @property
    def timestamp_s(self) -> int:
        """Returns the timestamp of the scan recordsm defined as the number of seconds that have elapsed since UTC.

        Returns:
            Timestamp of the scan recordsm defined as the number of seconds that have elapsed since UTC.
        """

        return self._timestamp_s

    @property
    def timestamp_ms(self) -> int:
        """Returns the number of milliseconds after `timestamp_s` at which the sample was acquired.

        Returns:
            Number of milliseconds after `timestamp_s` at which the sample was acquired.
        """

        return self._timestamp_ms

    @property
    def scan_index(self) -> int:
        """Returns the index of the scan record in the circular buffer.

        Returns:
            Index of the scan record in the circular buffer.
        """

        return self._scan_index

    @property
    def num_values(self):
        """Returns the number of single-precision values that follow in the record.

        Returns:
            Number of single-precision values that follow in the record.
        """

        return self._num_values

    def get_values(self):
        """Returns the array with a value from each channel that was specified in the channel list.

        Depending on the configuration of the channel(s), the values are expressed in °C, Ω, or V.

        Returns:
              Variable size array with a value from each channel that was specified in the channel list.
        """

        return self._values

    def get_value(self, index: int):
        """Returns the value at the specified index.

        Note that the index does not necessarily correspond to the channel index.

        Depending on the configuration of the channel(s), the value is expressed in °C, Ω, or V.

        Args:
            index (int): Index of the value to return.

        Returns:
            Value at the specified index.
        """
        return self._values[index]

    def get_datetime(self) -> tuple[datetime.datetime, str, str]:
        """Returns the datetime, date, and time of the scan record.

        Returns:
            Tuple containing the datetime of the scan record, the date (format: %Y%m%d), and the time (format: %H:%M:%S).
        """

        dt = datetime.datetime.fromtimestamp(self.timestamp, datetime.UTC)

        return dt, dt.strftime("%Y%m%d"), dt.strftime("%H:%M:%S")

    def __repr__(self) -> str:
        """Returns a string representation of the scan record.

        Returns:
            String representation of the scan record.
        """

        _, date, time = self.get_datetime()

        response = "ScanRecord:\n"
        response += f"  Timestamp [s] (raw):     {self._timestamp_s} (0x{self._timestamp_s:08x})\n"
        response += f"  Timestamp [ms]:          {self._timestamp_ms}  (0x{self._timestamp_ms:08x})\n"
        response += f"  Date:                    {date}\n"
        response += f"  Time:                    {time}\n"
        response += f"  Datetime:                {datetime.datetime.fromtimestamp(self.timestamp, datetime.UTC)}\n"
        response += f"  Scan index:              {self._scan_index}\n"
        response += f"  Number of values:        {self._num_values}\n"

        if self.num_values == 1:
            response += f"  Value:                   {self._values[0]}\n"
        else:
            response += f"  Values:                  {self._values}\n"

        return response

    def __str__(self) -> str:
        """Returns a printable string representation of the scan record.

        Returns:
            Printable string representation of the scan record.
        """

        return self.__repr__()


class ScanRecords:
    def __init__(self, scan_records: list[ScanRecord]):
        """Initialisation of a collection of scan records.

        Args:
            scan_records (list[ScanRecord]): List of scan records.
        """

        self._scan_records = scan_records

    def get_num_scan_records(self) -> int:
        """Returns the number of scan records in the collection."""
        return len(self._scan_records)

    def get_scan_record(self, index: int) -> ScanRecord:
        """Returns the scan record at the specified index.

        Note that the index does not necessarily correspond to the index in the circular buffer.

        Args:
            index (int): Index of the scan record to return.

        Returns:
            Scan record at the specified index.
        """

        return self._scan_records[index]

    def __repr__(self):
        """Returns a string representation of the collection of scan records.

        Returns:
            String representation of the collection of scan records.
        """

        response = ""

        for index, scan_record in enumerate(self._scan_records):
            _, date, time = scan_record.get_datetime()

            response += f"ScanRecord {index}:\n"
            response += f"  Timestamp [s] (raw):     {scan_record.timestamp_s} (0x{scan_record.timestamp_s:08x})\n"
            response += f"  Timestamp [ms]:          {scan_record.timestamp_ms}  (0x{scan_record.timestamp_ms:08x})\n"
            response += f"  Date:                    {date}\n"
            response += f"  Time:                    {time}\n"
            response += (
                f"  Datetime:                {datetime.datetime.fromtimestamp(scan_record.timestamp, datetime.UTC)}\n"
            )
            response += f"  Scan index:              {scan_record.scan_index}\n"
            response += f"  Number of values:        {scan_record.num_values}\n"

            if scan_record.num_values == 1:
                response += f"  Value:                   {scan_record.get_value(0)}\n\n"
            else:
                response += f"  Values:                  {scan_record.get_values()}\n\n"

        return response

    def __str__(self):
        """Returns a printable string representation of the collection of scan records.

        Returns:
            Printable string representation of the collection of scan records.
        """

        return self.__repr__()


def split_result_on_comma(response: str) -> tuple[str, ...]:
    """Splits the given response string on commas.

    Args:
        response (str): Response string to split.

    Returns:
        Tuple of strings split on commas.
    """

    return tuple(response.split(","))


def int_to_bool(response: str) -> bool:
    """Converts the given response string to a boolean.

    Args:
        response (str): Response string to convert.

    Returns:
        bool: Boolean value converted from the response string.
    """

    return bool(int(response))


def to_int(response: str) -> int:
    """Converts the given response string to an integer.

    Args:
        response (str): Response string to convert.

    Returns:
        Integer value converted from the response string.
    """

    return int(response)


def to_float(response: str) -> float:
    """Converts the given response string to a float.

    Args:
        response (str): Response string to convert.

    Returns:
        Float value converted from the response string.
    """

    return float(response)


def split_on_comma_to_int(response: str) -> tuple[int, ...]:
    """Splits the given response string on commas.

    Args:
        response (str): Response string to split.

    Returns:
         Tuple of integers split on commas.
    """

    response = split_result_on_comma(response)

    return tuple(int(x) for x in response)


def format_to_time(response: str) -> str:
    """Converts the given response string to time.

    Args:
        response (str): Response string to convert.

    Returns:
        Time string converted from the response string.
    """

    hours, minutes, seconds = split_result_on_comma(response)

    return f"{hours.zfill(2)}:{minutes.zfill(2)}:{seconds.zfill(2)}"


def to_date(response: str) -> datetime.datetime:
    """Converts the given response string to a date.

    Args:
        response (str): Response string to convert.

    Returns:
        Date string converted from the response string.
    """

    return datetime.datetime.strptime(response, "%Y,%m,%d")


def parse_error(response: str) -> tuple[int, str]:
    """Converts the given response string of a tuple of an error code and the corresponding error message.

    Args:
        response (str): Response string to convert

    Returns:
        Tuple of an error code and the corresponding error message.
    """
    code, description = split_result_on_comma(response)

    return int(code), description


def parse_single_measurement(response: bytes) -> tuple[float, ...]:
    """Converts the given response bytes to a float.

    Args:
        response (bytes): Response bytes to convert.

    Returns:
        Depending on the configuration of the channel(s), the values are expressed in °C, Ω, or V.

    """

    endian_char = ">"
    offset = 0

    binary_data = response[3:-1]

    values = []

    while offset + 4 <= len(binary_data):
        # Unpack float values

        value = struct.unpack_from(f"{endian_char}f", binary_data, offset)[0]
        offset += 4

        values.append(value)

    return tuple(values)


def parse_scan_records(response: bytes) -> ScanRecords:
    """Converts the given response bytes to a collection of scan records.

    Args:
        response (bytes): Response bytes to convert.

    Returns:
        Collection of scan records.
    """

    # Skip the header

    if response.startswith(b"#"):
        header_end = 6
        binary_data = response[header_end:-1]  # -1 to skip trailing newline
    else:
        binary_data = response

    endian_char = ">"
    offset = 0
    record_num = 1

    scan_records = []

    while offset + 16 <= len(binary_data):
        # Unpack header (4 unsigned longs)
        header = struct.unpack_from(f">IIII", binary_data, offset)
        timestamp_s, timestamp_ms, scan_index, num_values = header

        offset += 16

        # Unpack float values

        values = []

        if 0 < num_values < 100:  # Sanity check
            for i in range(num_values):
                if offset + 4 <= len(binary_data):
                    value = struct.unpack_from(f"{endian_char}f", binary_data, offset)[0]
                    offset += 4

                    values.append(value)
        else:
            break

        scan_record = ScanRecord(timestamp_s, timestamp_ms, scan_index, num_values, values)
        scan_records.append(scan_record)

        record_num += 1

    return ScanRecords(scan_records)


def get_channel_list(channel_list: str) -> list[str]:
    """Generates a list of channel names from a given channel list.

    The "names" of the channels are the indices of the channels, as strings.

    Args:
        channel_list: a channel list as understood by the SCPI commands of DAQ6510.

    Returns:
        List of channel names.
    """

    match = re.match(r"\(@(.*)\)", channel_list)
    group = match.groups()[0]

    parts = group.replace(" ", "").split(",")
    names = []
    for part in parts:
        if ":" in part:
            channels = part.split(":")
            names.extend(str(ch) for ch in range(int(channels[0]), int(channels[1]) + 1))
        else:
            names.append(part)

    return names


class DigilentInterface(DeviceInterface):
    """Base class for Digilent TEMPpoint, VOLTpoint, and MEASURpoint instruments."""

    def __init__(self):
        super().__init__()

        self.channel_lists = navdict()
        self.channels = navdict()

    def config_channels(self, setup: Setup = None):
        """Reads the channel configuration from the setup + apply it to the device.

        Args
            setup (Setup): Setup from which load read the channel configuration.
        """

        self.channel_lists = navdict()
        self.channels = navdict()

        setup = setup or load_setup()

        try:
            channel_config = setup.gse.pmx_a

            if "RTD" in channel_config:
                self.channels["RTD"] = navdict()
                self.channel_lists["RTD"] = navdict()

                for rtd_type in channel_config.RTD:
                    if rtd_type != "channels":
                        channels = channel_config.RTD[rtd_type].channels

                        self.channels.RTD[rtd_type] = channels
                        self.channel_lists.RTD[rtd_type] = get_channel_list(channels)

                        self.set_rtd_temperature_channels(rtd_type=rtd_type, channels=channels)

            if "THERMOCOUPLE" in channel_config:
                self.channels["THERMOCOUPLE"] = navdict()
                self.channel_lists["THERMOCOUPLE"] = navdict()

                for tc_type in channel_config.THERMOCOUPLE:
                    if tc_type != "channels":
                        channels = channel_config.THERMOCOUPLE[tc_type].channels

                        self.channels.RTD[tc_type] = channels
                        self.channel_lists.RTD[tc_type] = get_channel_list(channels)

                        self.set_thermocouple_temperature_channels(rtd_type=tc_type, channels=channels)

            if "RESISTANCE" in channel_config:
                channels = channel_config.RESISTANCE.channels

                self.channels["RESISTANCE"] = channels
                self.channel_lists["RESISTANCE"] = get_channel_list(channels)

                self.set_resistance_channels(channels=channels)

            if "VOLTAGE" in channel_config:
                channels = channel_config.VOLTAGE.channels

                self.channels["VOLTAGE"] = channels
                self.channel_lists["VOLTAGE"] = get_channel_list(channels)

                self.set_voltage_channels(channels=channels)

            if "VOLTAGE_RANGE" in channel_config:
                channels = channel_config.VOLTAGE_RANGE.channels

                self.channels["VOLTAGE_RANGE"] = channels
                self.channel_lists["VOLTAGE_RANGE"] = get_channel_list(channels)

                self.set_voltage_range_channels(channels=channels)

            if len(self.channel_lists) == 0:
                logger.warning("No channels configured, check the log messages.")
        except AttributeError:
            logger.warning(f"Couldn't configure the channels, check the log messages.")

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*CLS",
        process_cmd_string=add_lf,
    )
    def clear_status(self) -> None:
        """Clears all event registers summarised in the Status Byte (STB) register.

        All queues that are summarised in the Status Byte (STB) register, except the output queue, are emptied.  The
        device is forced into the operation complete idle state.
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*ESE ${bits}",
        process_cmd_string=add_lf,
    )
    def set_std_event_status_enable_register(self, bits: int) -> None:
        """Enables specified bits in the Standard Event Status Enable register.

        The bits in the Standard Event Status Enable register are:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 0 | 1 | OPC (Operation complete) |
            | 1 | 2 | RQC (Request control) |
            | 2 | 4 | QYE (Query error) |
            | 3 | 8 | DDE (Device-dependent error) |
            | 4 | 16 | E (Execution error) |
            | 5 | 32 | CME (Command error) |
            | 6 | 64 | NU (Not used) |
            | 7 | 128 | PON (Power on) |

        Refer to IEEE Std 488.2-1992, Sect. 11.5.1.3, for more information.

        This is a password-protected command.

        Args:
            bits (int): Integer value expressed in base 2 (binary) that represents the weighted bit value of the
                        Standard Event Status Enable register and the binary-weighted decimal value for each bit.

        Examples:
            The following command enables bits 0, 2, 3, 4, 5, and 7 of the Standard Event Status Enable register:
            > *ESE 189
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*ESE?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_std_event_status_enable_register(self) -> int:
        """Returns the current value of the Standard Event Status Enable register.

        The bits in the Standard Event Status Enable register are:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 0 | 1 | OPC (Operation complete) |
            | 1 | 2 | RQC (Request control) |
            | 2 | 4 | QYE (Query error) |
            | 3 | 8 | DDE (Device-dependent error) |
            | 4 | 16 | E (Execution error) |
            | 5 | 32 | CME (Command error) |
            | 6 | 64 | NU (Not used) |
            | 7 | 128 | PON (Power on) |

        Refer to IEEE Std 488.2-1992, Sect. 11.4.2.3.2, and IEEE Std 488.2, Sect. 8.7.1, for more information.

        Returns:
            Integer value expressed in base 2 (binary) that represents the weighted bit value of the Standard Event
            Status Enable register and the binary-weighted decimal value for each bit.  Values range from 0 to 255.

        Examples:
            The following command queries the Standard Event Status Enable register:

                > *ESE?
                < 189

            This value indicates that bits 0, 2, 3, 4, 5, and 7 of the Standard Event Status Enable register are enabled.
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*ESR?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_std_event_status_register(self) -> int:
        """Returns the current value of the Standard Event Status register.

        The bits in the Standard Event Status  register are:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 0 | 1 | OPC (Operation complete) |
            | 1 | 2 | RQC (Request control) |
            | 2 | 4 | QYE (Query error) |
            | 3 | 8 | DDE (Device-dependent error) |
            | 4 | 16 | E (Execution error) |
            | 5 | 32 | CME (Command error) |
            | 6 | 64 | NU (Not used) |
            | 7 | 128 | PON (Power on) |

        Bits in the Standard Event Status register should be unmasked by settings the corresponding bit in the Standard
        Status Enable register.  On power-up, the Standard Event Status Enable register is zero; therefore, all bits in
        the Standard Event Status register are masked.

        Returns:
            Integer value expressed in base 2 (binary) that represents the weighted bit value of the Standard Event
            Status register and the binary-weighted decimal value for each bit.  Values range from 0 to 255.

        Examples:
            The following example unmasks all error bits in the Standard Event Status register:

                > *ESE?; *ESE 255; *ESE?
                < 0; ;255

            Then, an illegal command it sent and the Standard Event Status register is queried; a value of 32 is
            returned, indicating that bit 5 (Command error) of the Standard Event Status register was set:

                > *bad
                > *ESR?
                < 32

            In the following example, the scan rate is set to an illegal value; a value of 16 is returned, indicating
            that bit 4 (Execution error) of the Standard Event Status register was set:

                > :CONF:SCAN:RATe:HZ 50
                > *ESR?
                < 16
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*IDN?",
        process_cmd_string=add_lf,
        process_response=split_result_on_comma,
    )
    def get_id(self) -> tuple[str, str, str, str]:
        """Returns the unique identifier of your TEMPpoint, VOLTpoint, or MEASURpoint LXI instrument.

        Refer to IEEE 488.2-1992, Sects. 6.5.7.5 snd 10.14, for more information.

        Returns:
            Manufacturer: Defines the manufacturer of the instrument (Data Translation).
            Model: Identifies the model of the instrument.
            Serial number: Identifies the serial number of the instrument.
            Firmware revision: Identifies the version of the firmware that is loaded on the instrument.

        Examples:
                > *IDN?
                < Data Translation,DT8874-08T-00R-08V,201129241,2.2.0.0
            This response indicates that Data Translation is the manufacturer of the device, DT8874-08T-00R-08V is the
            model of the instrument (where 08T indicates that the instrument contains 8 thermocouple channels, 00R
            indicates that the instrument contains 0 RTD channels, and 08V indicates that the instrument contains 8
            voltage channels), 201129241 is the serial number of the instrument, and 2.2.0.0 is the version of the
            firmware.
        """

        pass

    @dynamic_command(
        cmd_string="*RST",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def reset(self) -> None:
        """Resets the instrument.

        Clears the Standard Event Status register, message queue, error queue, and Status Byte register, and stops any scans that are in progress.

        This command has no effect on the instrument's password or password enable/disable state.

        Refer to IEE 388.2-1992, Sect. 10.32, for more information.
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*STB?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_status_byte_register(self) -> int:
        """Returns the current value of the Status Byte register.

        The weighted sum of the bit values of the Status Byte register is returned, ranging from 0 to 255.  The
        following bits, described in 1999 SCPI Syntax & Stype, Sect. 9, are supported:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 7 | 128 | Summary of device-dependent Operation Status register |
            | 5 | 32 | Event Status Bit Summary (ESB); "1" = ESR is non-zero, "0" otherwise |
            | 4 | 16 | Message Available Queue Summary (MAV); "1" = message queue not empty |
            | 2 | 4 | Error/Event Queue Summary; "1" = error queue not empty |

        Refer to IEE 388.2-1992, Sect. 10.36, for more information.

        Returns:
            Weighted sum of the bit values of the Status Byte register, ranging from 0 to 255.

        Examples:
            The following example shows a query that is correct and causes no errors:

                > *IDN?;*ESR?;*STB?
                < Data Translation,DT8874-08T-00R-08V,-1,1.2;16

            This example shows an illegal command being sent, and the status of the Status Byte register and the error
            queue:

                > bad
                > *STB?
                < 16

            A value of 36 indicates that bit 5 (Standard Event Status Bit Summary) and 2 (Error/Event Queue Summary) of
            the Status Byte register are set.

            The following example shows the status of the Event Status register:

                > *ESR?
                < 32

            A value of 32 indicates that bit 5 (Command Error) of the Event Status register is set.  The following
            updates the status of the Status Byte register:

                > *STB?
                < 4

             A value of 4 indicates that bit 2 (Error/Event Queue Summary) of the Status Byte register is set.  The
             following shows the error codes that are returned and updates that status of the Status Byte register:

                > :SYST:ERR?
                < -110,"Command header error;bad"
                > :SYST:ERR?
                < 0;"No error"
                > *STB?
                < 0
        """

        pass

    @dynamic_command(
        cmd_string="STATus:OPERation:CONDition?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_operation_condition(self) -> int:
        """Returns the current value of the Operation Status register.

        It is a 14-bit value, for which only the following bits can be set to "1":

            - Bit 4 (binary weight: 16):
                - If this bit is 1:
                    - Bit 5 is 1: Waiting for trigger,
                    - Bit 5 is 0: Scanning in progress,
                - If this bit is 0:
                    - Bit 5 is 0: Scanning is stopped.
            - Bit 5 (binary weight: 32):
                - If this bit is 1:
                    - Bit 4 is 1: Waiting for trigger,
                - If this bit is 0:
                    - Bit 4 is 1: Scanning in progress,
                    - Bit 4 is 0: Scanning is stopped.

        Examples:
            The following example shows the status of the Operation Status register and the Status Byte register when a
            scan is in progress and a software trigger is used:

                > :STAT:OPER:COND?
                < 16
                > *STB?
                < 128

            A value of 16 indicates that bit 4 (Scan status) of the Operation Status register is set to 1.  A value of
            128 indicates that bit 7 (Operation Status Register Summary) of the Status Byte register is set to 1.

            The following example shows the status of the Operation Status register and the Status Byte register when
            a scan is in progress and the instrument is waiting for an external digital trigger:

                > :STAT:OPER:COND?
                < 48
                > *STB?
                < 128

            A value of 48 indicates that bit (Scan Status) and bit 5 (Trigger Status) of the Operation Status are set
            to 1.  A value of 128 indicates that bit 7 (Operation Status Register Summary) of the Status Byte register
            is set to 1.

            The following example shows the status of the Operation Status register and the Status Byte register when
            the instrument is idle:

                > :STAT:OPER:COND?
                < 0
                > *STB?
        """
        pass

    @dynamic_command(
        cmd_string=":STATus:SCAn?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=split_on_comma_to_int,
    )
    def get_scan_record_status(self) -> tuple[int, int]:
        """Returns the indices of the chronologically oldest and most recent scan records in the instrument's FIFO.

        If the circular buffer is empty (because a scan has not been started, or started and stopped), both indices
        will be 0.  Otherwise, the indices will be non-zero.

        Returns:
            Index of the chronologically oldest scan record in the instrument's circular buffer.
            Index of the chronologically most recent scan record in the instrument's circular buffer.

        Examples:
            The following example shows that starting index (1001) and ending index (1050) when the circular buffer
            consists of scan records 1001 to 1050:

                > :STAT:SCAn?
                < 1001,1050
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:CALibrate",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def auto_calibrate(self) -> None:
        """Auto-calibrates (auto-zeroes) all analogue input channels on the instrument.

        This is a password-protected command.

        Examples:
            This command auto-zeroes all analogue input channels on the instrument:

                > :SYST:CAL
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:DATE?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_date,
    )
    def get_date(self) -> datetime.datetime:
        """Returns the current date of the instrument.

        This date is updated automatically by an SNTP (Simple Network Time Protol) server.

        Returns:
            Year.
            Month, in the range 1 to 12.
            Day, in the range 1 to 31

        Examples:
            This response indicates that the data of the instrument is January 15th, 2008:

                > :SYST:DATE?
                < 2008,1,15
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:ERRor?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=parse_error,
    )
    def get_error(self) -> tuple[int, str]:
        """Reads an error message from the error queue and then removes it from the queue.

        Potential errors are:
            - No error (0): Normal operation; no error occurred.
            - Command error (-100): A command is missing a parameter, or the command contains too many parameters or
                                    too many dimensions.
            - Syntax error (-110): An unrecognised command or data type was encountered (e.g. a string was received when
                                   the instrument does not accept strings).
            - Data type error (-104): A data element different from the one allowed was encountered (e.g. numeric data
                                      was expected but string data was encountered).
            - Command header error (-110): The command header is invalid.
            - Unexpected number of parameters (-115): The number of parameters received does not correspond to the number
                                                     of parameters expected by the command.
            - Numeric data error (-120): The value of a parameter overflowed, has the wrong dimensions, or contains an
                                         invalid value.
            - Invalid suffix (-131): The suffix does not follow the syntax described in IEEE 488.2, Sect. 7.7.3.2, or
                                     the suffix is inappropriate for this instrument.
            - Execution error (-200): A <PROGRAM DATA> element following a header was evaluated by the instrument as
                                      outside its legal input range or is otherwise inconsistent with the instrument's
                                      capabilities.  A valid programme message could not be executed properly due to
                                      some condition of the instrument.
            - Command protected (-203): This is a password-protected command.  Password protection is currently
                                        disabled.  To use this command you must enable password protection.
            - Settings conflict (-221): The specified channels of the instrument do not support the requested operation,
                                        or an invalid current password was entered.  E.g. this error is returned if you
                                        try to configure a thermocouple type for channels that do not support
                                        temperature, or try to configure a voltage range that is not supported by the
                                        channel.
            - Data out of range (-222): A legal programme data element was parsed but could not be executed because the
                                        interpreted value was outside the legal range for the instrument.
            - Programme currently running (-284): Certain operations dealing with programmes are illegal while the
                                                  instrument is in the middle of executing a programme.
                                                  programme is running (e.g. you cannot configure/re-configure an
                                                  operation while a scan is in progress).
            - Queue overflow (-350): The error queue is full; subsequent errors cannot be added to the queue.  You must
                                     clear the queue.
            - Query interrupted (-410): THe query did not complete.

        The error queue is a FIFO with a capacity of 32 error messages.  By querying the error count before and after
        an SCPI commands (in a single command string), you can unambiguously determine whether the command that you
        issued caused an error.

        When the queue is full, subsequent errors cannot be added to the queue.

        Refer ro 1999 SCPI Command Reference, Sect. 21.8, for more information.

        Returns:
            Error/Event number: Unique integer in the range of -32 768 to 32 767.  A value of 0 indicates that no
                                error or event has occurred.
            Error/Event description: Quoted string that contains a description of the error that was read from the
                                     Error/Event Queue.

        Examples:
            The following shows the responses to this query after an invalid command is sent to the instrument:

                > :BADc
                > :SYST:ERR?
                < -110,"Command header error;:BADc"
                > :SYST:ERR?
                < 0,"No error"
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:ERRor:COUNt?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_num_errors(self) -> int:
        """Queries the error queue, returns the number of unread items and returns the count.

        The error queue is a FIFO with a capacity of 32 error messages.  By querying the error count before and after
        an SCPI commands (in a single command string), you can unambiguously determine whether the command that you
        issued caused an error.

        Returns:
            Number of unread items in the error queue. A value of 0 indicates that the queue is empty.

        Examples:
            The following shows how to query the number of error in the error queue, both before and after the
            INITialize command:

                > :SYST:ERR:COUN?;:INIT;:SYST:ERR:COUN?
                < 0
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:PRESet",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def reset_lan(self) -> None:
        """Sets the LAN configuration to its default values.

        The effect of this command is the same as pushing the LAN reset switch on the rear panel of the instrument.
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:COMMunicate:NETwork:IPADdress?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_ip_address(self) -> str:
        """Returns the static IP address that is currently used by the instrument on the network.

        Returns:
            Static IP address that is currently used by the instrument on the network.
        """

        # FIXME This actually returns the IP address of my laptop, rather than the instrument

        pass

    @dynamic_command(
        cmd_string=":SYSTem:COMMunicate:NETwork:MASk?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_lan_ip_subnet_mask(self) -> str:
        """Returns the static IP subnet mask that is currently used by the instrument on the network.

        Returns:
            Static IP subnet mask that is currently used by the instrument on the network.

        Examples:
            > :SYST:COMM:NET:MAS?
            < 255.255.255.0
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:PASSword:CDISable ${password}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def disable_pwd_protected_cmds(self, password: str) -> None:
        """Disables the use of commands and queries that are password-protected.

        On power-up, all password-protected commands are disabled.  If the instrument is powered down, you must enable
        the password-protected commands when the instrument is powered up again, if you want to configure or operate
        the instrument.

        When the SCPI password-protected commands and queries are disabled, the instrument generates the following
        error if any of these commands is issued: –203, Command protected.

        Args:
            password (str): Password that is stored in permanent memory on the instrument.
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:PASSword:CENable ${password}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def enable_pwd_protected_cmds(self, password: str) -> None:
        """Enables the use of commands and queries that are password-protected.

        On power-up, all password-protected commands are disabled.  If the instrument is powered down, you must enable
        the password-protected commands when the instrument is powered up again, if you want to configure or operate
        the instrument.

        When the SCPI password-protected commands and queries are disabled, the instrument generates the following
        error if any of these commands is issued: –203, Command protected.

        Args:
            password (str): Password that is stored in permanent memory on the instrument.
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:PASSword:CENable:STATe?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=int_to_bool,
    )
    def is_pwd_protected_cmds_enabled(self) -> bool:
        """Returns whether password-protected commands are enabled.

        Returns:
            True if password-protected commands are enabled; False otherwise.

        Examples:
            In the following example, the state is 1, indicating that password-protected commands are enabled:

                > :SYST:PASS:CEN:STAT?
                < 1
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:PASSword:NEW ${old_password},${new_password}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_pwd(self, old_password: str, new_password: str) -> None:
        """Changes the existing password to a new password.

        The new password becomes effective immediately.  The instrument does not need to be re-booted.  The new password
        is reflected in the LAN configuration webpage for the instrument.

        The new password is enforced when any attempt is made to configure the instrument using SCPI commands, the
        instrument's webpages, or the IVI-COM driver.

        Args:
            old_password (str): Current password.
            new_password (str): New password that will overwrite the current password and be saved in permanent memory
                                on the instrument.
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:VERSion?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_scpi_version(self) -> str:
        """Returns the SCPI version to which the instrument complies.

        Returns:
            <Year of the version.<Revision number for that year>

        Examples:
            In this example, the version is year 1999 and the SCPI revision is 0:

                > :SYST:VERS?
                < 1999.0
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:BOArd?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_num_boards(self) -> int:
        """Returns the number of boards that are installed in the instrument.

        Returns:
             Number of boards installed in the instrument.  This value can range from 0 to 6.

        Examples:
            In this case, 6 boards are installed:

                > :SYST:BOA?
                < 6
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:BOArd:MOdel? ${board_number}",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_board_model(self, board_number: int) -> int:
        """Returns the model of a specific board installed in the instrument.

        The following values are supported:

            - 0 -> DT8871 (thermocouple board),
            - 1 -> DT8871U (thermocouple board),
            - 2 -> DT8873-100V (voltage board with a fixed range of +/- 100V) -> Replaced by DT8873-MULTI,
            - 3 -> DT8873-10V (voltage board with a fixed range of +/- 10V) -> Replaced by DT8873-MULTI,
            - 4 -> DT8873-400V (voltage board with a fixed range of +/- 400V) -> Replaced by DT8873-MULTI,
            - 5 -> DT8872 (RTD board),
            - 7 -> DT8873-MULTI (voltage board that supports programmable voltage ranges of +/-10V and +/-60V).

        Args:
            board_number (int): Board number to query.  This value can range from 1 to 6.

        Returns:
            Model of the specified board in the instrument.

        Examples:
            The following example returns the model of board number 3 in a MEASURpoint instrument.  In this case, the
            model is 5, representing the DT8872 RTD board.

                > :SYST:BOA:MOD? 3
                < 5
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:BOArd:MOdel:NAMe? ${board_number}",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_board_name(self, board_number: int) -> str:
        """Returns the name of a specific board that is installed in the instrument.

        Args:
            board_number (int): Board number to query.  This value can range from 1 to 6.

        Returns:
            Name of the specified board in the instrument.

        Examples:
            The following example returns the name of board number 3 in a MEASURpoint instrument.  In this case, the
            name is "DT8872" (an RTD board).

                > :SYST:BOA:MOD:NAM? 3
                < DT8872
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:BOArd:RANGe? ${board_number}",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_voltage_range(self, board_number: int) -> tuple[float, float]:
        """Returns the minimum and maximum voltages that are supported by a specific board in the instrument.

        Args:
            board_number (int): Board number to query.  This value can range from 1 to 6.

        Returns:
            Tuple of the minimum and maximum voltages supported by the specified board [V].

        Examples:
            The following example returns the minimum and maximum voltages that are supported by a DT8873-MULTI board
            (board 1 in this case):

                > :SYST:BOA:RANG? 1
                < -60.000, 60.000

            This example returns the minimum and maximum voltages that are supported by a DT8872 RTD board (board 1 in
            this case):

                > :SYST:BOA:RANG? 1
                < -1.250, 1.250
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:CHANnel?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_input_channels(self) -> str:
        """Returns a list of all analogue input channels that are supported on the instrument.

        If no analogue input channels are supported on the instrument, an empty list (@) is returned.

        Returns:
            List of all analogue input channels that are supported on the instrument.

        Examples:
            The following example returns the list of supported analogue input channels on an instrument, in this case,
            24 channels (0 to 23):

                > :SYST:CHAN?
                < @0:23
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:CHANnel:RTD?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_rtd_channels(self) -> str:
        """Returns a list of all analogue input channels that support RTDs on the instrument.

        If no channels support RTDs on the instrument, an empty list (@) is returned.

        Returns:
            List of all analogue input channels that support RTDs on the instrument.

        Examples:
            The following example returns the list of analogue input channels on the instrument, as well as the channels
            that support RTDs.  In this case, all 48 channels (0 to 47) support RTDs:

                > :SYST:CHAN?
                < @0:47
                > :SYST:CHAN:RTD?
                < @0:47

            In the following example, only channels 8 to 15 of the available 48 channels support RTDs:

                > :SYST:CHAN?
                < @0:47
                > :SYST:CHAN:RTD?
                < @8:15
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:CHANnel:TCouple?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_thermocouple_channels(self) -> str:
        """Returns a list of all analogue input channels that support thermocouples on the instrument.

        If no channels support thermocouples on the instrument, an empty list (@) is returned.

        Returns:
            List of all analogue input channels that support thermocouples on the instrument.

        Examples:
            The following example returns the list of analogue input channels on the instrument, as well as the channels
            that support thermocouples.  In this case, all 48 channels (0 to 47) support thermocouples:

                > :SYST:CHAN?
                < @0:47
                > :SYST:CHAN:TC?
                < @0:47

            In the following example, only channels 0 to 15 of the available 48 channels support thermocouples:

                > :SYST:CHAN?
                < @0:47
                > :SYST:CHAN:TC?
                < @0:15
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:CHANnel:VOLTage:RANGe?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_voltage_range_channels(self) -> str:
        """Returns a list of analogue input channels that support programmable voltage ranges on the instrument.

        If no channels support programmable voltage ranges on the instrument, an empty list (@) is returned.

        Returns:
            List of all analogue input channels that support programmable voltage ranges on the instrument.

        Examples:
            The following example returns which channels support programmable voltage ranges; in this case, channels 0
            to 7 support thermocouples, while channels 8 to 15 support RTDs, and channels 16 to 23 support programmable
            voltage ranges:
                > *IDN?
                < Data Translation,DT7774-08T-08R-08V,-1,1.8,0.0
                > :SYSTem:CHANnel?
                < (@0:23)
                >:SYSTem:CHANnel:RTD?
                < (@8:15)
                > :SYSTem:CHANnel:TC?
                < (@0:7)
                > :SYSTem:CHANnel:VOLTage:RANGe?
                < (@16:23)
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:DINput?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_num_digital_input_lines(self) -> int:
        """Returns the number of digital input lines that are supported by the instrument.

        Returns:
            Number of digital input lines that are supported by the instrument.

        Examples:
            The following example returns the number of digital input lines supported by the instrument:

                > :SYSTem:DINput?
                < 8
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:DINput?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_num_digital_output_lines(self) -> int:
        """Returns the number of digital output lines that are supported by the instrument.

        Returns:
            Number of digital output lines that are supported by the instrument.

        Examples:
            The following example returns the number of digital output lines supported by the instrument:

                > :SYSTem:DOUTput?
                < 8
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:SCAn:RATe:MAXimum:SEC?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_max_scan_rate(self) -> float:
        """Returns the maximum scan rate in s.

        Returns:
            Maximum scan rate [s].

        Examples:
            The following example returns the maximum scan rate that is supported by the instrument, in seconds:

                > :SYST:SCA:MAX:SEC?
                < 0.10000
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:SCAn:RATe:MAXimum:HZ?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_max_scan_frequency(self) -> float:
        """Returns the maximum frequency rate in Hz.

        Returns:
            Maximum frequency rate [s].

        Examples:
            The following example returns the maximum scan rate that is supported by the instrument, in Hz:

                > :SYST:SCA:MAX:HZ?
                < 10.00000
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:SCAn:RATe:MINimum:SEC?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_min_scan_rate(self) -> float:
        """Returns the minimum scan rate in s.

        Returns:
            Minimum scan rate [s].

        Examples:
            The following example returns the minimum scan rate that is supported by the instrument, in seconds:

                > :SYST:SCA:MIN:SEC?
                < 6553.5
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:SCAn:RATe:MINimum:HZ?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_min_scan_frequency(self) -> float:
        """Returns the minimum frequency rate in Hz.

        Returns:
            Minimum frequency rate [s].

        Examples:
            The following example returns the minimum scan rate that is supported by the instrument, in Hz:

                > :SYST:SCA:MIN:HZ?
                < 1.525e-4
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:TIME?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=format_to_time,
    )
    def get_time(self) -> tuple[int, int, int]:
        """Returns the current time used by the instrument.

        This date is updated automatically by an SNTP server.

        Returns:
            Tuple of (hour, minute, second)

        Examples:
            This response indicates that the current time of the instrument is 15:31:45 (15 is the hour, 31 is the
            number of minutes, and 45 is the number of seconds):

                > :SYST:TIME?
                < 15:31:45
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:TZONe?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_timezone(self) -> tuple[int, int]:
        """Returns the timezone that is currently used by the instrument, as an offset from GMT.

        Returns:
            Tuple of (number of hours offset from GMT, number of minutes offset from GMT) that shows the offset of the
            current time relative to GMT.

        Examples:
            This response indicates that the current timezone of the instrument if four hours and 30 minutes ahead of
            GMT:

                > :SYST:TZON?
                < 4, -45
        """

        # TODO

        pass

    @dynamic_command(
        cmd_string=":SYSTem:TZONe ${hour},${minute}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_timezone(self, hour: int, minute: int = 0) -> None:
        """Sets the timezone currently used by the instrument as an offset from GMT.

        The specified hour and minute are added to the UTC time that is maintained by the instrument.

        This is a password-protected command.

        Args:
            hour (int): Current hour relative to UTC.
            minute (int): Current minute relative to UTC.

        Examples:
            This command sets the current timezone used by the instrument to four hours and 30 minutes ahead of GMT:

                > :SYST:TZON 4,-45
        """

        pass

    # CONFigure Sub-System Commands

    @dynamic_command(
        cmd_string=":CONFigure:RESistance ${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_resistance_channels(self, channels: str = "(@0:47)"):
        """Configures specified channels for resistance measurements.

        This can only be applied to channels that support resistance measurements.  This command affects the
        configuration of the specified channels only.

        The number of channels that you can specify depends on the configuration of your instrument.

        This is a password-protected command.

        Refer to 1999 SCPI Command Reference, Sect. 3.1 and 3.7.2, and 1999 SCPI Syntax & Style, Sect. 8.3.2, for more
        information.

        Args:
            channels (str): List of channels to configure for resistance measurements.

        Examples:
            The following command configures analogue input channels 0, 3 to 7, and 47 on the instrument for resistance
            measurements:

                > :CONF:RES (@0,3:7,47)

            This command configures all analogue input channels on the instrument for resistance measurements:

                > :CONF:RES

            This command configures analogue input channels 1, 2, and 8 to 46 on the instrument for resistance
            measurements:

                > :CONF:RES (@1,2,8:46)
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:TEMPerature:RTD ${rtd_type},${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_rtd_temperature_channels(self, rtd_type: str, channels: str = "(@0:47)"):
        """Configures specified channels on the instrument for RTD temperature measurements.

        Allowed RTD types are:
            - For 2- or 4-wire European RTDs:
                - PT100
                - PT500
                - PT1000
            - For 2- or 4-wire American RTDs:
                - A_PT100
                - A_PT500
                - A_PT1000
            - For 3-wire European RTDs:
                - PT100_3
                - PT500_3
                - PT1000_3
            - For 3-wire American RTDs:
                - A_PT100_3
                - A_PT500_3
                - A_PT1000_3
            - DEFault

        This commands affects the configuration of the specified channels only.

        The number of channels that you can specify depends on the configuration of your instrument.

        This is a password-protected command.

        Args:
            rtd_type (str): RTD type to be used for the temperature measurements.
            channels (str): List of channels to configure for RTD temperature measurements.

        Examples:
            This example configures analogue input channel 8 to use a PT1000 2- or 4-wire European RTF:

                > :CONF:TEMP:RTD PT1000, (@8)
                > *STB?
                < 0

            The following example tries to configure all analogue input channels on the instrument to use a PT100
            2- or 4-wire European RTD.  However, in this example, no channels support RTD input; therefore an
            Execution Error occurs.  If bit 4 (E) of the Standard Event Status Enable register is enable, an
            Execution Error sets but 4 (E) of the Standard Event Status register.  This, in turn, will set bits 2 and 5
            of the Status Byte register:

                > *ESE 189
                > ESR?
                < 0
                > :CONF:TEMP:RTP PT100
                > *STB?
                < 36
                > ESR?
                < 16
                > :SYST;ERR?
                < -200, "Execution error;CONF:TEMP:RTD invalid"
                > *STB?
                < 0
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:TEMPerature:TCouple ${tc_type}, ${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_thermocouple_temperature_channels(self, tc_type: str, channels: str = "(@0:47)"):
        """Configures specified channels on the instrument for thermocouple temperature measurements.

        Allowed thermocouple types are:
            - J (Iron/Constantan)
            - K (Nickel-Chromium / Nickel-Alumel)
            - B (Platinum Rhodium -30% / Platinum Rhodium -6%)
            - E (Nickel-Chromium/Constantan)
            - N (Nicrosil/Nisil)
            - R (Platinum Rhodium -13% / Platinum)
            - S (Platinum Rhodium -10% / Platinum)
            - T (Copper/Constantan)
            - DEFault

        This commands affects the configuration of the specified channels only.

        The number of channels that you can specify depends on the configuration of your instrument.

        This is a password-protected command.

        Args:
            tc_type (str): Thermocouple type to be used for the temperature measurements.
            channels (str): List of channels to configure for thermocouple temperature measurements.

        Examples:
            This example configures analogue input channel 3 to use a K-type thermocouple:

                > :CONF:TEMP:TCouple K, (@3)
                > *STB?
                < 0

            The following example tries to configure the analogue input channels to use an S-type thermocouple.  In
            this example, the instrument does not support thermocouple channels; therefore, an Execution Error occurs.
            If bit 4 (E) of the Standard Event Status Enable register is enable, an Execution Error sets but 4 (E) of
            the Standard Event Status register.  This, in turn, will set bits 2 and 5 of the Status Byte register:

                > *ESE 189
                > ESR?
                < 0
                > :CONF:TEMP:TC S
                > *STB?
                < 36
                > ESR?
                < 16
                > :SYST;ERR?
                < -200, "Execution error;CONF:TEMP:TC invalid"
                > *STB?
                < 0
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:VOLTage ${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_voltage_channels(self, channels: str = "(@0:47)"):
        """Configures specified RTD and thermocouple channels on the instrument for voltage measurements.

        This commands affects the configuration of the specified channels only.

        The number of channels that you can specify depends on the configuration of your instrument.

        This is a password-protected command.

        Args:
            channels (str): List of channels to configure for voltage measurements.

        Examples:
            The following example configures analogue input channels 0, 3 to 7, and 47 for voltage measurements:

                > :CONF:VOLT (@0,3:7,47)

            This example configures all analogue input channels on the instrument for voltage measurements:

                > :CONF:VOLT

            This example configures analogue input channels 1, 2, and 8 to 46 for voltage measurements:

                > :CONF:VOLT (@1,2,8:46)
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:VOLTage:RANGe ${voltage_range},${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_voltage_range_channels(self, voltage_range: str = "DEFault", channels: str = "(@0:47)"):
        """Configures  the voltages range for specified channels on the instrument.

        Allowed voltage ranges are:
            - BIP100MV: Specifies an input voltage range of +/-0.1V,
            - BIP1V: Specifies an input voltage range of +/-1V,
            - BIP10V: Specifies an input voltage range of +/-10V,
            - BIP100V: Specifies an input voltage range of +/-100V,
            - BIP400V: Specifies an input voltage range of +/-400V,
            - BIP60V: Specifies an input voltage range of +/-60V,
            - DEFault: Selects the default voltage range of +/-10V.

        This commands affects the configuration of the specified channels only.

        The number of channels that you can specify depends on the configuration of your instrument.

        This is a password-protected command.

        Args:
            voltage_range (str): Voltage range to be used for the voltage measurements.
            channels (str): List of channels to configure for voltage measurements.

        Examples:
            The following example returns the configuration of all channels on a MEASURpoint instrument;  In this case,
            all channels on the instrument can be programmed for thermocouple measurements:

                > :CONF:?
                < V,J,J,V,J,V,J,J,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V

            This example configures all channels for a type J thermocouple, and then reconfigures channels 0, 3, and 5
            for voltage inputs. In the first query, the configuration of channels 0 and 7 is returned. In the second
            query, the configuration of channels 0 through 7 is returned:

                > :CONF:TEMP:TC J
                > :CONF:VOLT (@0,3,5)
                > :CONF? (@0,7)
                < V,J
                > :CONFigure? (@0:7)
                < V,J,J,V,J,V,J,J

            The following example returns the configuration of all channels on a MEASURpoint instrument; in this case,
            all channels on the instrument can be programmed for thermocouple measurements:

                > :CONF?
                < V,J,J,V,J,V,J,J,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V,V

            This example configures all channels for a type J thermocouple, and then reconfigures channels 0, 3, and 5
            for voltage inputs. In the first query, the configuration of channels 0 and 7 is returned. In the second
            query, the configuration of channels 0 through 7 is returned:

                > :CONF:TEMP:TC J
                > :CONF:VOLT (@0,3,5)
                > :CONF? (@0,7)
                < V,J
                > :CONFigure? (@0:7)
                < V,J,J,V,J,V,J,J

            In this example, the configuration of channels 0 through 7 of a MEASURpoint instrument that supports
            programmable voltage ranges is returned:
                > :CONF? (@0:7)
                < BIP10V,BIP10V,BIP60V,BIP60V,BIP60V,BIP60V,BIP60V,BIP60V
        """

        # TODO Only for VOLTpoint + MEASURpoint
        pass

    @dynamic_command(
        cmd_string=":CONFigure? ${channels}",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_channel_config(self, channels: str = "(@0:47)"):
        """Returns the configuration of the specified channels on the instrument.

        Returns up to 48 fields of comma-separated values. Each field contains the configuration of a channel:
            - For each thermocouple input, one of the following thermocouple value is returned: J, K, R, S, T, B, E, N.
            - For each RTD input, one of the following RTD value is returned: PT100, PT500, PT1000, A_PT100, A_PT500,
              A_PT1000, PT100_3, PT500_3, PT1000_3, A_PT100_3, A_PT500_3, A_PT1000_3.
            - For each voltage input, OHM is returned.

        This is a password-protected command.

        Args:
            channels (str): List of channels to configure for voltage measurements.

        Returns:
            Up to 48 fields of comma-separated values. Each field contains the configuration of a channel.

        Examples:
            The following examples set the filter type and then return the current filter configuration:

                > :CONF:FILT AVG
                > :CONF:FILT?
                < AVG

                >:CONF:FILT RAW
                > :CONF:FILT?
                < RAW
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:FILTer ${filter_type}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_filter_type(self, filter_type: str) -> BaseException:
        """Configures the filter type used for single-value and continuous analogue input operations.

        Allowed filter types are:
            - RAW: No filtering.  Provides fast response times, but the data may be difficult to interpret.  Use when
              you want to filter the data yourself.
            - AVG: Moving average.  Provides a compromise of filter functionality and response time.  Can be used in
              any application.

        Args:
            filter_type (str): Filter type to be used for the analogue input operations.
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:FILTer?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_filter_type(self) -> str:
        """Returns the currently configured filter type for the instrument.

        Allowed filter types are:
            - RAW: No filtering.  Provides fast response times, but the data may be difficult to interpret.  Use when
              you want to filter the data yourself.
            - AVG: Moving average.  Provides a compromise of filter functionality and response time.  Can be used in
              any application.

        This is a password-protected command.

        Returns:
            Currently configured filter type.

        Examples:
            The following examples set the filter type, and then return the current configuration of the filter type:

                > :CONF:FILT AVG
                > :CONF:FILT?
                < AVG

                > :CONF:FILT RAW
                > :CONF:FILT?
                < RAW
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:BUFfer?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_scan_circular_buffer_size(self) -> int:
        """Returns the size of the circular buffer that is used to store the scan data.

        Returns:
            Size of the circular buffer that is used to store the scan data [bytes].

        Examples:
            The following example returns the size of the circular buffer that is used to store scan data on the
            instrument:

                > :CONFigure:SCAn:BUFfer?
                < 1048576
                > :CONFigure:SCAn:BUF:LEN?
                < 1048576
                > :CONFigure:SCAn:BUFfer?
                < 1048576
                > :CONFigure:SCAn:BUF?
                < 1048576
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:CJC ${cjc}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_scan_cjc(self, cjc: str | int) -> None:
        """Enable the capacity of returning CJC data in the analogue input data stream.

        Allowed values are:
            - ON or any non-zero numerical value: Return CJC data in the analogue input stream.
            - OFF, 0, or DEFault: Don't return CJC in the analogue input stream.

        This is a password-protected command.

        Args:
            cjc (str): Enable the capacity of returning CJC data in the analogue input data stream.

        Examples:
            Any of the following commands disables the capability of returning CJC data in the analogue input data
            stream:
                > :CONF:SCAn:CJC;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC OFF;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC DEF;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC 0;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC ON;:CONF:SCAn:CJC?
                < 1
                > :CONF:SCAn:CJC 1;:CONF:SCAn:CJC?
                < 1
                > :CONF:SCAn:CJC 34;:CONF:SCAn:CJC?
                < 1
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:CJC?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_scan_cjc(self) -> int:
        """Returns the currently configured CJC data in the analogue input data stream.

        Allowed values are:
            - 1: Return CJC data in the analogue input stream.
            - 0: Don't return CJC in the analogue input stream.

        Refer to 1999 SCPI Syntax & Style, Sect. 7.3 for more information.

        Returns:
            If the capability of returning CJC data in the analogue input data stream is enabled, a value of 1 is
            returned.  If the capability of returning CJC data in the analogue input data stream is disabled, a value
            of 0 is returned.

        Examples:
            Any of the following commands disables the capability of returning CJC data in the analogue input data
            stream:
                > :CONF:SCAn:CJC;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC OFF;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC DEF;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC 0;:CONF:SCAn:CJC?
                < 0
                > :CONF:SCAn:CJC ON;:CONF:SCAn:CJC?
                < 1
                > :CONF:SCAn:CJC 1;:CONF:SCAn:CJC?
                < 1
                > :CONF:SCAn:CJC 34;:CONF:SCAn:CJC?
                < 1
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:LISt ${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_scan_list(self, channels: str = "(@0:47)") -> None:
        """Enables a list of channels to scan on the instrument.

        This is a password-protected command.

        Refer to 1999 SCPI Syntax & Style, Sect. 8.3.2, for more information.

        Args:
            channels (str): List of channels to scan on the instrument.

        Examples:
            This example enables channels 0, 4, 5, and 7 and then returns the list of enabled channels; note that while
            this command tries to enable channel 5 twice, it is enabled only once:

                > :CONF:SCAn:LISt (@5,4,7,0,5)
                > :CONF:SCAn:LISt?
                < (@0,4:5,7)

            This example disables all channels; the list of enabled channels is empty:
                > :CONF:SCAn:LISt
                > :CONF:SCAn:LISt?
                < (@)
            This command enables channels 0, 4, 5, and 7 and returns the list of enabled channels:
                > :CONF:SCAn:LISt (@5,4,7,0)
                > :CONF:SCAn:LISt?
                < (@0,4:5,7)

            This command enables channels 0, 4, 5, 6, and 7 and returns the list of enabled channels:
                > :CONF:SCAn:LISt (@5,4,7,6,0)
                > :CONF:SCAn:LISt?
                < (@0,4:7)
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:LISt?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_scan_list(self) -> str:
        """Returns the list of channels that are enabled for scanning on the instrument.

        Returns:
            List of channels that are enabled for scanning on the instrument.

        Examples:
            The following example enables channels 0, 4, 5, and 7 and then returns the list of enabled channels; note
            that while this command tries to enable channel 5 twice, it is enabled only once:
                > :CONF:SCAn:LISt (@5,4,7,0,5)
                > :CONF:SCAn:LISt?
                < (@0,4:5,7)

            This example disables all channels; the list of enabled channels is empty:
                > :CONF:SCAn:LISt;:CONF:SCAN:LISt?
                < (@)

            This example enables channels 0, 4, 5, and 7 and then returns the list of enabled channels:
                > :CONF:SCAn:LISt (@5,4,7,0)
                > :CONF:SCAn:LISt?
                < (@0,4:5,7)

            This example enables channels 0, 4, 5, 6, and 7 and then returns the list of enabled channels:
                > :CONF:SCAn:LISt (@5,4,7,6,0)
                > :CONF:SCAn:LISt?
                < (@0,4:7)
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:RATe:SEC ${rate}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_scan_rate(self, rate: float) -> None:
        """Configures the time period of each scan.

        This is a password-protected command.

        Args:
            rate (float): Time period of each scan [s].

        Examples:

        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:RATe:HZ ${frequency}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_scan_frequency(self, frequency: float) -> None:
        """Configures the time period of each scan.

        This is a password-protected command.

        Args:
            frequency (float): Scan frequency [Hz].

        Examples:
            The following command tries to set the scan frequency to 3Hz, but the actual scan frequency is set to 3.3Hz,
            which corresponds to a scan rate of 0.3s:

                > :CONF:SCAn:RATe:HZ 3
                > :CONF:SCAn:RATe:HZ?
                < 3.333333
                > :CONF:SCAN:RATe?
                < 0.300000

            The following command sets the scan frequency to 2Hz, which corresponds to a scan rate of 0.5s; the actual
            scan frequency is set to the same value, since 2 is an exact divisor of 10.0Hz:

                > :CONF:SCAn:RATe 0.5
                > :CONF:SCAn:RATe:HZ?
                < 2.000000
                > :CONF:SCAN:RATe?
                < 0.500000

            In this example, an invalid scan frequency is specified, and an Execution Error occurs. If bit 4 (E) of
            the Standard Event Status Enable register is enabled, an Execution Error sets bit 4 (E) of the Standard
            Event Status register. This, in turn, sets bits 2 and 5 of the Status Byte register:

                > :CONF:SCAn:RATe:HZ 200
                > *STB?
                < 36
                > *ESR?
                < 16
                > *STB?
                < 4
                > :SYST:ERR?
                < -222,"Data out of range; CONF:SCAn:RATe"
                > *STB?
                < 0
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:RATe:SEC?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_scan_rate(self) -> float:
        """Returns the time period of each scan [s]."""
        pass

    @dynamic_command(
        cmd_string=":CONFigure:SCAn:RATe:HZ?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_scan_frequency(self) -> float:
        """Returns the scan frequency [Hz].


        Examples:
            The following command tries to set the scan frequency to 3Hz, but the actual scan frequency is set to 3.3Hz,
            which corresponds to a scan rate of 0.3s:

                > :CONF:SCAn:RATe:HZ 3
                > :CONF:SCAn:RATe:HZ?
                < 3.333333
                > :CONF:SCAN:RATe?
                < 0.300000

            The following command sets the scan frequency to 2 Hz, which corresponds to a scan rate of 0.5 s; the
            actual scan frequency is set to the same value, since 2 is an exact divisor of 10.0 Hz:

                > :CONF:SCAn:RATe 0.5
                > :CONF:SCAn:RATe:HZ?
                < 2.000000
                > :CONF:SCAN:RATe?
                < 0.500000

            In this example, an invalid scan frequency is specified and an Execution Error occurs. If bit 4 (E) of the
            Standard Event Status Enable register is enabled, an Execution Error sets bit 4 (E) of the Standard Event
            Status register. This, in turn, sets bits 2 and 5 of the Status Byte register:

                > :CONF:SCAn:RATe:HZ 200
                > *STB?
                < 36
                > *ESR?
                < 16
                > *STB?
                < 4
                > :SYST:ERR?
                < -222,"Data out of range; CONF:SCAn:RATe"
                > *STB?
                < 0
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:TRIGger:SOURce ${source}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_trigger_source(self, source: str) -> None:
        """Configures the trigger source used to start the analogue input operation.

        This is a password-protected command.

        Allowed sources are:
            - IMMediate or DEFault: Specifies a software trigger.
            - DIN0: Specifies an external, digital trigger on DIN0.

        Args:
            source (str): Trigger used to start the analogue input operation.

        Examples:
            The following command sets the trigger source to the external, digital trigger:

                > :CONF:TRIG DIN0
        """

        pass

    @dynamic_command(
        cmd_string=":CONFigure:TRIGger:SOURce?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
    )
    def get_trigger_source(self) -> str:
        """Returns the currently configured trigger source used to start the analogue input operation.

        Allowed sources are:
            - IMMediate or DEFault: Specifies a software trigger.
            - DIN0: Specifies an external, digital trigger on DIN0.

        Returns:
            Currently configured trigger source used to start the analogue input operation.

        Examples:
            The following returns the currently configured trigger source of the instrument; in this case, an external
            digital trigger is configured:

                > :CONF:TRIG?
                < DIN0
        """

        pass

    # MEASure Sub-System Commands

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEASure:RESistance? ${channels}",
        process_cmd_string=add_lf,
        process_response=parse_single_measurement,
    )
    def get_resistance(self, channels: str = "(@0:47)") -> tuple[float, ...]:
        """Configures and returns the resistance measurement values for the specified channels.

        This is a password-protected command.

        Examples:
            The following example configures analogue input channels 0 for a resistance measurement and reads the
            resistance value from this channel:

                > :MEAS:RES? (@0)
                < 2331344488fe4f0a

            where:
                - 23 = '#' denotes the start of the block response
                - 31 = '1' is the length of the decimal number for the block length
                - 34 = '4' is the block length (that is 4-bytes per channel)
                - 4488fe4f = 1095.947 ohms; this is the resistance measurement value from channel 0
                - 0a = carriage return; this is the standard ASCII terminator

        Args:
            channels (str): List of channels to configure for resistance measurements.

        Returns:
            Data block of up to 48 single-precision, floating point values, where each value corresponds to a channel
            in the given list of channels [Ohm].
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEASure:TEMPerature:RTD? ${rtd_type},${channels}",
        process_cmd_string=add_lf,
        process_response=parse_single_measurement,
    )
    def get_rtd_temperature(self, rtd_type: str, channels: str = "(@0:47)") -> tuple[float, ...]:
        """Configures and returns the RTD temperature measurement values for the specified channels.

        This is a password-protected command.

        Allowed RTD types are:
            - For 2- or 4-wire European RTDs:
                - PT100
                - PT500
                - PT1000
            - For 2- or 4-wire American RTDs:
                - A_PT100
                - A_PT500
                - A_PT1000
            - For 3-wire European RTDs:
                - PT100_3
                - PT500_3
                - PT1000_3
            - For 3-wire American RTDs:
                - A_PT100_3
                - A_PT500_3
                - A_PT1000_3
            - DEFault

        Args:
            rtd_type (str): RTD type to be used for the temperature measurement.
            channels (str): List of channels to configure for RTD temperature measurement.

        Returns:
            Data block of up to 48 single-precision, floating point values, where each value corresponds to a channel
            in the given list of channels [°C].

        Examples:
            The following example configures analogue input channels 0, 1, 7 for the default sensor and transducer type
            for the instrument and then reads the temperature from these channels:

                > :MEAS:TEMP:RTD? DEF,(@0,1,7)
                < 23323132c7ad9c0041bd99b647c34f800a

            where:
                - 23 = '#' denotes the start of the block response
                - 32 = '2' is the length of the decimal number for the block length
                - 3132 = '12' is the block length (that is 4-bytes per channel times 3)
                - c7ad9c00 = –88888° C; this is the measurement value from channel 0, indicating that the value is too
                  low and out of range
                - 41bd99b6 = 27.7° C; this is the measurement value from channel 1
                - 47c34f80 = 99999° C; this is the measurement value from channel 7
                - 0a = carriage return; this is the standard ASCII terminator
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEASure:TEMPerature:TCouple?,${channels}",
        process_cmd_string=add_lf,
        process_response=parse_single_measurement,
    )
    def get_thermocouple_temperature(self, tc_type: str, channels: str = "(@0:47)") -> tuple[float, ...]:
        """Configures and returns the RTD temperature measurement values for the specified channels.

        This is a password-protected command.

        Allowed thermocouple types are:
            - J (Iron/Constantan)
            - K (Nickel-Chromium / Nickel-Alumel)
            - B (Platinum Rhodium -30% / Platinum Rhodium -6%)
            - E (Nickel-Chromium/Constantan)
            - N (Nicrosil/Nisil)
            - R (Platinum Rhodium -13% / Platinum)
            - S (Platinum Rhodium -10% / Platinum)
            - T (Copper/Constantan)
            - DEFault

        Args:
            tc_type (str): Thermocouple type to be used for the temperature measurements.
            channels (str): List of channels to configure for RTD temperature measurement.

        Returns:
            Data block of up to 48 single-precision, floating point values, where each value corresponds to a channel
            in the given list of channels [°C].

        Examples:
            The following example configures analogue input channels 0, 1, 7 for the default sensor and transducer type
            for the instrument and then reads the temperature from these channels:

                > :MEAS:TEMP:TC? DEF,(@0,1,7)
                < 23323132c7ad9c0041bd99b647c34f800a

            where:
                - 23 = '#' denotes the start of the block response
                - 32 = '2' is the length of the decimal number for the block length
                - 3132 = '12' is the block length (that is 4-bytes per channel times 3)
                - c7ad9c00 = –88888° C; this is the measurement value from channel 0, indicating that the value is too
                  low and out of range
                - 41bd99b6 = 27.7° C; this is the measurement value from channel 1
                - 47c34f80 = 99999° C; this is the measurement value from channel 7, indicating that an open
                  thermocouple exists on that channel
                - 0a = carriage return; this is the standard ASCII terminator
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEASure:VOLTage? ${channels}",
        process_cmd_string=add_lf,
        process_response=parse_single_measurement,
    )
    def get_voltage(self, channels: str = "(@0:47)") -> tuple[float, ...]:
        """Configures and returns the voltage measurement values for the specified channels.

        This is a password-protected command.

        Args:
            channels (str): List of channels to configure for RTD temperature measurement.

        Returns:
            Data block of up to 48 single-precision, floating point values, where each value corresponds to a channel
            in the given list of channels [V].

        Examples:
            The following example configures analogue input channels 0, 1, 7 for voltage measurements and then reads
            the values from these channels:

                > :MEAS:VOLT? (@0,1,7)
                < 233231323f0f8aec3edefa51bf2844b80a

            where:
                - 23 = '#' denotes the start of the block response
                - 32 = '2' is the length of the decimal number for the block length
                - 3132 = '12' is the block length (that is 4-bytes per channel times 3)
                - 3f0f8aec = 0.56071 V; this is the measurement value from channel 0
                - 3edefa51 = 0.43550 V; this is the measurement value from channel 1
                - bf2844b8 = –0.65729 V; this is the measurement value from channel 7
                - 0a = carriage return; this is the standard ASCII terminator
        """

    # INITiate Sub-System Command

    @dynamic_command(
        cmd_string=":INITiate",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def init_scan(self) -> None:
        """Initiates a continuous scan operation on an instrument.

        The continuous scan operation uses the configured channels, scan list, scan rate, and trigger source.

        This is a password-protected command.

        Examples:
            The following example configures the instrument to scan channels 0 to 5 at approximately 2Hz when an
            external digital trigger is detected, and queries the Operation Status register to verify that a scan
            operation is not in process:

               > :CONF:SCA:LIS?
               < (@)
               >:CONF:SCA:LIS (@0:5)
               >:CONF:TRIG IMM
               > :CONF:SCA:RAT:HZ 2
               > :CONF:SCA:RAT:HZ?
               < 1.875000
               > :STAT:OPER:COND?
               < 0

           The scan is then initiated, and bit 7 of the Status Byte register and the Operation Status register are
           queried to determine the status of the scan and whether the instrument has detected the trigger:

               > :INIT
               > *STB?
               < 128
               > :STAT:OPER:COND?
               < 48

           In this case, the scan has started, and the instrument is waiting for the trigger. The next query confirms
           that the trigger occurred and the instrument is scanning:

               > *STB?
               < 128
               > :STAT:OPER:COND?
               < 16

           The scan is then stopped and bit 7 of the Status Byte register and the Operation Status register are cleared:

               > :ABOR
               > :STAT:OPER:COND?
               < 0
               > *STB?
               < 0
        """

        pass

    # ABORt Sub-System Command

    @dynamic_command(
        cmd_string=":ABORt",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def abort_scan(self) -> None:
        """Stops a scan operation on the instrument.

        If a scan is in progress, it will be stopped, regardless of whether the specified trigger occurred.

        This is a password-protected command.

        Examples:
            The following example configures the instrument to scan channels 0  to 5 at approximately 2Hz when a
            software trigger is detected and queries the Operation Status register to verify that scans are stopped:

                > :CONF:SCA:LIS?
                < (@)
                > :CONF:SCA:LIS (@0:5)
                > :CONF:TRIG IMM
                > :CONF:SCA:RAT:HZ 2
                > :CONF:SCA:RAT:HZ?
                < 1.875000
                > :STAT:OPER:COND?
                < 0

            The scan is then started, and bit 7 of the Status Byte register the Operation Status register are queried
            to determine the status of the scan:

                > :INIT
                > *STB?
                < 128
                > :STAT:OPER:COND?
                < 16

            The scan is then stopped and bit 7 of the Status Byte register and the Operation Status register are cleared:

                > :ABOR
                > :STAT:OPER:COND?
                < 0
                > *STB?
                < 0
        """

        pass

    # FETCh Sub-System Command

    @dynamic_command(
        cmd_string=":FETCh? ${index}, ${num_scans}",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=parse_scan_records,
    )
    def fetch_data(self, index: int, num_scans: int) -> list[ScanRecord]:
        """Returns time-stamped, sequenced measurements from the circular buffer on the instrument, as scan records.

        This only applies to the scans that were started with the INITiate command (`init_scan`).

        Args:
            index (int): Index of the san record (offset in the circular buffer) from which to retrieve data.  To read the first scan records, specify `1`.
            num_scans (int): Number of scan records to retrieve from the circular buffer.

        Returns:
            A list of scan records, each containing the time-stamped, sequenced measurements.

        Examples:
            The following example returns scan records, starting with index 0, on an instrument that has one channel
            (channel 0) enabled in the scan list:

                > :FETC? 0
                <
                23 ASCII # char that starts the IEEE block
                34 ASCII 4, meaning that the next 4 chars are the length of the IEEE block
                32303430 ASCII character 2040, representing the length of the entire IEEE block

                4a806d65 Scan record time stamp, in seconds
                00000000 Scan record time stamp, in milliseconds
                00000001 Scan record scan number (1)
                00000001 Scan record number of values; 1 floating point value per scan
                3a86c3ff Value of chan 0 in floating-point 6.5565103e-4

                4a806d65 Time stamp of next record, in seconds
                00000064 Time stamp, in milliseconds
                00000002 Scan number (2)
                00000001 Number of values (1)
                3a9a4bff Value of chan 0

                4a806d65 Timestamp of next record, in seconds
                000000c8 Time stamp, in milliseconds
                00000003 Scan number (3)
                00000001 Number of values (1)
                3ac543ff Value of chan 0
                .
                .
                .
                4a806d6c Timestamp of next record, in seconds
                00000064 Time stamp, in milliseconds
                00000048 Scan number (48)
                00000001 Number of values (1)
                3a5ea800 Value of chan 0

            This example returns two scan records (5 and 6) from an instrument that is scanning one channel:

                > STATus:SCAn?
                < 1,1083
                > FETCh? 5, 2 (fetch records 5 and 6)
                23 ASCII # char that starts the IEEE block
                34 ASCII 4, meaning that the next 4 chars are the length of the IEEE block
                30303430 ASCII character 0040, the length of the entire IEEE block (10 4-byte fields)
                4a807ad3 Time stamp, in seconds
                00000190 Time stamp, in milliseconds
                00000005 Scan number (5)
                00000001 Number of values (1)
                3984cfff Value of channel
                4a807ad3 Time stamp of next record, in seconds
                000001f4 Time stamp, in milliseconds
                00000006 Scan number (6)
                00000001 Number of values (1)
                393b7fff Value of channel 6
                0a Carriage Return. This is the standard SCPI Terminator.
        """

        pass

    # Digital INPut Sub-System Command

    @dynamic_command(
        cmd_string=":INPut:STATe?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_digital_input_state(self) -> int:
        """Returns the current state of the digital input port on the instrument.

        Refer to the 1999 SCPI Data Exchange Format, Sect. 3.4.6, for more information on the data format.

        Returns: Weighted bit value of the digital input port, where the value of bit 0 (digital input 0) corresponds
                 to a decimal value of 1 (2**0) if the bit is set, and the value of bit 7 (digital input 7)
                 corresponds to a decimal value of 128 (2**7) if the bit is set.  Values range from 0 to 255.

        Examples:
            This response indicates that digital input lines 1 and 7 (bits 1 and 7) of the digital input port are
            set:

                > :INPut:STATe?
                < 130
        """

        pass

    # Digital OUTPut Sub-System Commands

    @dynamic_command(
        cmd_string=":OUTPut:STATe?",
        cmd_type=CommandType.TRANSACTION,
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_digital_output_state(self):
        """Returns the current state of the digital output port on the instrument.

        Refer to the 1999 SCPI Data Exchange Format, Sect. 3.4.6, for more information on the data format.

        Returns: Weighted bit value of the digital output port, where the value of bit 0 (digital input 0) corresponds
                 to a decimal value of 1 (2**0) if the bit is set, and the value of bit 7 (digital input 7)
                 corresponds to a decimal value of 128 (2**7) if the bit is set.  Values range from 0 to 255.

        Examples:
            This response indicates that digital input lines 1 and 7 (bits 1 and 7) of the digital input port are
            set:

                > :OUTPut:STATe?
                < 130
        """

        pass

    @dynamic_command(
        cmd_string=":OUTPut:STATe ${state}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_digital_output_state(self, state: int):
        """Sets the state of the digital output port on the instrument.

        This is a password-protected command.

        Refer to the 1999 SCPI Data Exchange Format, Sect. 3.4.6, for more information on the data format.

        Args:
            state (int): Weighted bit value of the digital output port, where the value of bit 0 (digital input 0)
                         corresponds to a decimal value of 1 (2**0) if the bit is set, and the value of bit 7
                         (digital input 7) corresponds to a decimal value of 128 (2**7) if the bit is set.  Values
                         range from 0 to 255.

        Examples:
            This command sets digital output lines 0 and 7 (bits 0 and 7) to 1, and all other digital output lines
            (bits) to 0:

                > :OUTPut:STATe 129
        """

        pass


class DigilentController(DigilentInterface, DynamicCommandMixin):
    def __init__(self):
        """Initialisation of a Digilent controller."""

        super().__init__()

        # Define device interface in the sub-class

        self.transport: DigilentEthernetInterface | None = None

    # noinspection PyMethodMayBeStatic
    def is_simulator(self):
        return False

    def is_connected(self):
        """Checks whether the connection to the Digilent MEASURpoint is open.

        Returns:
            True if the connection to the Digilent MEASURpoint is open; False otherwise.
        """

        return self.transport.is_connected()

    def connect(self):
        """Opens the connection to the Digilent MEASURpoint.

        Raises:
            Dt8874Error: When the connection could not be opened.
        """

        self.transport.connect()

    def disconnect(self):
        """Closes the connection to the Digilent MEASURpoint.

        Raises:
            Dt8874Error: When the connection could not be closed.
        """

        self.transport.disconnect()

    def reconnect(self):
        """Re-connects to the Digilent MEASURpoint."""

        self.transport.reconnect()


class DigilentSimulator(DigilentInterface):
    def __init__(self):
        """Initialisation of a Digilent simulator."""

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
