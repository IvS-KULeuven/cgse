from egse.device import DeviceInterface
from egse.mixin import dynamic_command, CommandType, add_lf


class DigilentInterface(DeviceInterface):

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*CLS",
        process_cmd_string=add_lf,
    )
    def clear_status(self):
        """Clears all event registers summarised in the Status Byte (STB) register.

        All queues that are summarised in the Status Byte (STB) register, except the output queue, are emptied.  The
        device is forced into the operation complete idle state.
        """

        pass

    @dynamic_command(
        cmd_type=CommandType.READ,
        cmd_string="*ESE",
        process_cmd_string=add_lf,
    )
    def std_event_status_enable_register(self, bits: int):
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
        cmd_type=CommandType.READ,
        cmd_string="*ESE?",
        process_cmd_string=add_lf,
    )
    def std_event_status_enable_register_query(self):
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
        cmd_type=CommandType.READ,
        cmd_string="*ESR?",
        process_cmd_string=add_lf,
    )
    def std_event_status_register_query(self):
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
        cmd_type=CommandType.READ,
        cmd_string="*IDN?",
        process_cmd_string=add_lf,
    )
    def get_id(self):
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
    def reset(self):
        """Resets the instrument.

        Clears the Standard Event Status register, message queue, error queue, and Status Byte register, and stops any scans that are in progress.

        This command has no effect on the instrument's password or password enable/disable state.

        Refer to IEE 388.2-1992, Sect. 10.32, for more information.
        """

        pass

    def read_status_byte_query(self):
        """Returns the current value of hte Status Byte register.

        The weighted sum of the bit values of hte Status Byte register is returned, ranging from 0 to 255.  The
        following bits, described in 1999 SCPI Syntax & Stype, Sect. 9, are supported:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 7 | 128 | Summary of device-dependent Operation Status register |
            | 5 | 32 | Event Status Bit Summary (ESB); "1" = ESR is non-zero, "0" otherwise |
            | 4 | 16 | Message Available Queue Summary (MAV); "1" = message queue not empty |
            | 2 | 4 | Error/Event Queue Summary; "1" = error queue not empty |

        Refer to IEE 388.2-1992, Sect. 10.36, for more information.

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
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def operation_condition_query(self):
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def scan_record_status_query(self) -> tuple[int, int]:
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def date_query(self) -> tuple[int, int, int]:
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def error_query(self) -> tuple[int, str]:
        """Reads an error message from the error queue and then removes it from the queue.


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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def error_count_query(self) -> int:
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
    def reset_lan(self):
        """Sets the LAN configuration to its default values.

        The effect of this command is the same as pushing the LAN reset switch on the rear panel of the instrument.
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:COMMunicate:NETwork:IPADdress?",
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def get_ip_address(self) -> str:
        """Returns the static IP address that is currently used by the instrument on the network.

        Returns:
            Static IP address that is currently used by the instrument on the network.
        """

        pass

    @dynamic_command(
        cmd_string=":SYSTem:COMMunicate:NETwork:MASk?",
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def lan_ip_subnet_mask_query(self) -> str:
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_string=":SYSTem:PASSword:NEW ${old_password}, ${new_password}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def set_password(self, old_password: str, new_password: str):
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def get_scpi_version(self) -> float:
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def get_num_boards(self):
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def get_board_model(self, board_number: int) -> int:
        """Returns the model of a specific board installed in the instrument.

        The following values are supported:

            - DT8871 (thermocouple board),
            - DT8871U (thermocouple board),
            - DT8873-100V (voltage board with a fixed range of +/- 100V) -> Replaced by DT8873-MULTI,
            - DT8873-10V (voltage board with a fixed range of +/- 10V) -> Replaced by DT8873-MULTI,
            - DT8873-400V (voltage board with a fixed range of +/- 400V) -> Replaced by DT8873-MULTI,
            - DT8872 (RTD board),
            - DT8873-MULTI (voltage board that supports programmable voltage ranges of +/-10V and +/-60V).

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
        cmd_type=CommandType.READ,
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
        cmd_type=CommandType.READ,
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
        cmd_type=CommandType.READ,
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
        cmd_type=CommandType.READ,
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
        cmd_type=CommandType.READ,
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
        cmd_type=CommandType.READ,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
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
        cmd_type=CommandType.READ,
        process_cmd_string=add_lf,
    )
    def get_timezone(self) -> tuple[int, int]:
        """Returns the timezone that is currently used byt he instrument, as an offset from GMT.

        Returns:
            Tuple of (number of hours offset from GMT, number of minutes offset from GMT) that shows the offset of the
            current time relative to GMT.

        Examples:
            This response indicates that the current timezone of the instrument if four hours and 30 minutes ahead of
            GMT:

                > :SYST:TZON?
                < 4, -45
        """

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
    def config_resistance(self, channels: str = "(@0:47)"):
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
        cmd_string=":CONFigure:TEMPerature:RTD ${rtd_type} ${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def config_rtd_temperature_channels(self, rtd_type: str, channels: str = "(@0:47)"):
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
        cmd_string=":CONFigure:TEMPerature:TCouple ${tc_type} ${channels}",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def config_thermocouple_temperature_channels(self, tc_type: str, channels: str = "(@0:47)"):
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
    def config_voltage_channel(self, channels: str = "(@0:47)"):
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