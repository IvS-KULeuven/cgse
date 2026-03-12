from enum import IntEnum, Enum

from egse.device import DeviceInterface
from egse.mixin import dynamic_command, CommandType, add_lf


def parse_psu_instrument_id(response: str) -> tuple[str, ...]:
    """Parse the given device response to PSU instrument identification.

    Args:
        response (str): Response string to convert.

    Returns:
        - Manufacturer.
        - Model.
        - Serial number.
        - IFC version and build number.
        - IOC version and build number
    """

    response = response.split(",")

    return tuple(response[:3]) + tuple(response[3].split(" "))


def split_result_on_comma(response: str) -> tuple[str, ...]:
    """Splits the given response string on commas.

    Args:
        response (str): Response string to split.

    Returns:
        Tuple of strings split on commas.
    """

    return tuple(response.split(","))


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


def split_on_comma_to_float(response: str) -> tuple[float, ...]:
    """Splits the given response string on commas.

    Args:
        response (str): Response string to split.

    Returns:
         Tuple of integers split on commas.
    """

    response = split_result_on_comma(response)

    return tuple(float(x) for x in response)


def parse_error(response: str) -> tuple[int, str]:
    """Converts the given response string of a tuple of an error code and the corresponding error message.

    Args:
        response (str): Response string to convert

    Returns:
        Tuple of an error code and the corresponding error message.
    """

    code, description = split_result_on_comma(response)

    return int(code), description


class IntSwitch(IntEnum):
    """Enumeration of statuses."""

    ON = 1
    OFF = 0


class Memory(str, Enum):
    """Enumeration of the PSU memory.

    Possible values are:
        - A: memory A;
        - B: memory B;
        - C: memory C.
    """


class PriorityMode(str, Enum):
    """Enumeration for the PSU operation mode to be prioritised.

    Possible values are:

        - CONSTANT_CURRENT: Constant current is prioritised;
        - CONSTANT_VOLTAGE: Constant voltage is prioritised.
    """

    CONSTANT_CURRENT = "CC"  # Constant current is prioritised
    CONSTANT_VOLTAGE = "CV"  # Constant voltage is prioritised


class PmxInterface(DeviceInterface):
    """Base class for KIKUSUI PMX power supply units."""

    def __init__(self, device_id: str):
        """


        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__()

        self.device_id = device_id

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*IDN?",
        process_cmd_string=add_lf,
        process_response=parse_psu_instrument_id,
    )
    def get_id(self):
        """Returns the instrument identification of the PMX.

        Returns:
            Manufacturer, model, serial number, IFC version and build number, and the IOC version and build number.

        Examples:
            PMX-A:
                For a PMX18-5 with serial number AB123456, IFC version 1.00, IFC build number 0016, IOC version 1.00,
                and IOC build number 0015, this returns:
                    KIKUSUI,PMX18-5,AB123456,IFC01.00.0016 IOC01.00.0015

            PMX-Multi:
                For a PMX32-3DU with serial number AB123456, version 1.00, and build number 0001, this returns:
                    KIKUSUI,PMX32-3DU,AB123456,VER01.00 BLD0001
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_string="*RST",
        cmd_type=CommandType.WRITE,
        process_cmd_string=add_lf,
    )
    def reset(self) -> None:
        """Resets the PMX settings.

        Resets the panel settings, clear alarms, abort the trigger sub-system operation, clear the OPC bit (bit 0) of
        the status event register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*TST?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def selftest(self) -> int:
        """Executes a self-test.

        Returns:
            Result of the self-test.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SYST:ERR?",
        process_cmd_string=add_lf,
        process_response=parse_error,
    )
    def get_error_info(self) -> tuple[int, str]:
        """Reads the oldest error information the error queue.

        The error queue can store up to 16 errors. Use the clear_psu command to clear the error queue.

        Returns:
            Identifier and description of the oldest error in the error queue.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*CLS",
        process_cmd_string=add_lf,
    )
    def clear_status(self) -> None:
        """Clear all event registers.

        This includes the status byte, event status, and error queue.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="INST ${channel}",
        process_cmd_string=add_lf,
    )
    def set_channel(self, channel: int) -> None:
        """Specifies the channel to configure.

        If parallel or series operation is in use, you cannot specify CH1.

        Args:
            channel (int): Channel to configure.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="INST?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_channel(self) -> int:
        """Returns the channel to configure.

        On the PMX-A, +1 is always returned.

        Returns:
            Channel to configure.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="INST:CAT?",
        process_cmd_string=add_lf,
        process_response=split_on_comma_to_int,
    )
    def get_channel_list(self) -> tuple[int, ...]:
        """Returns the list of channels that can be configured with the sset_channels command.

        Returns the channels that can be configured in NR1[,NR1...] format. On the PMX-A, +1 is always returned.

        Returns:
            List of channels that can be configured with the sset_channels command.

        Examples:
            If parallel or series operation is being performed on a PMR-QU model, +2,+3,+4 is returned.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="INST:INFO?",
        process_cmd_string=add_lf,
        process_response=split_on_comma_to_float,
    )
    def get_channel_info(self) -> tuple[float, float]:
        """Returns the information of the channel currently being controlled.

        Returns:
            Maximum and minimum voltage of the channel [V].

        Examples:
            If the maximum voltage is 32 V and the maximum current is 2 Aon the channel under control, sending
            INST:INFO? returns
                +3.2000E+01, +2.0000E+00
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEAS:CURR?",
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_current(self) -> float:
        """Returns the measured value of the current [A].

        Returns:
            Measured value of the current [A].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEAS:VOLT?",
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_voltage(self) -> float:
        """Returns the measured value of the voltage [V].

        Returns:
            Measured value of the voltage [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MEM:REC ${memory}",
        process_cmd_string=add_lf,
    )
    def recall_memory(self, memory: Memory) -> None:
        """Recalls the settings stored in the given pre-set memory.

        Recalls the settings (current, voltage, OCP (Over-Current Protection), and OVP (Over-Voltage Protection))
        stored in the pre-set memory (1 for memory A, 2 for memory B, 3 for memory C).  When recalling a pre-set memory
        when the output is turned on, the setting stored in the memory will be applied immediately.

        Args:
            memory (Memory): Pre-set memory identifier (1 or Memory.A for memory A, 2 or Memory.B for memory B, 3 or
                             Memory.C for memory C).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MEM:REC:CONF ${conf}",
        process_cmd_string=add_lf,
    )
    def conf_settings(self, conf: IntSwitch) -> None:
        """Confirms (or not) the settings.

        Sets whether to check the content saved in the pre-set memory (current, voltage, OCP (Over-Current Protection),
        and OVP (Over-Voltage Protection)), when re-calling it from the control panel (1 to confirm the settings, 0 to
        reject the settings).  When recalling the memory with the recall_psu_memory command, the settings stored in the
        pre-set memory will be recalled immediately.

        Args:
            conf (IntSwitch): Indicates whether to check the content saved in the pre-set memory (current, voltage,
                              OCC (Over-Current Protection), and OVP (Over-Voltage Protection)), when re-calling it
                              from the control panel.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEM:REC:CONF?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_memory_config(self) -> IntSwitch:
        """Returns whether to check the content saved in the pre-set memory when recalling them from the control panel.

        Returns whether o check the content (current, voltage, OCP (Over-Current Protection), and OVP Over-Voltage
        Protection)) saved in the pre-set memory when recalling them from the control panel.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MEM:REC:PREV? ${memory}",
        process_cmd_string=add_lf,
        process_response=split_on_comma_to_float,
    )
    def get_memory_setting(self, memory: Memory) -> tuple[float, float, float, float]:
        """Returns the settings stored in the given pre-set memory.

        Args:
            memory: Pre-set memory identifier (1 for memory A, 2 for memory B, 3 for memory C).

        Returns:
            - Current [A] as stored in memory.
            - Voltage [V] as stored in memory.
            - Over-Current Protection (OCP) [A] as stored in memory.
            - Over-Voltage Protection (OCP) [V] as stored in memory.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MEM:SAVE ${memory}",
        process_cmd_string=add_lf,
    )
    def save_memory(self, memory: Memory) -> None:
        """Saves to the pre-set memory.

        The current, voltage, OCP (Over-Current Protection), and OVP (Over-Voltage Protection) are saved in the pre-set
        memory.

        Args:
            memory (Memory): Pre-set memory identifier (1 or Memory.A for memory A, 2 or Memory.B for memory B, 3 or
                             Memory.C for memory C).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="OUTP ${output_status}",
        process_cmd_string=add_lf,
    )
    def set_output_status(self, output_status: IntSwitch) -> None:
        """Sets the output status and type (0/1).

        Sets the output status and type (0/1).  This command is invalid when a protection function is activated.  The
        settings are reset to default with the reset_psu command.

        Args:
            output_status (IntSwitch): Indicates whether the output should be switched on.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="OUTP?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def get_output_status(self) -> IntSwitch:
        """Returns the output status.

        Returns:
            1 if the output is enabled, 0 otherwise.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="CURR ${current}",
        process_cmd_string=add_lf,
    )
    def set_current(self, current: float) -> None:
        """Sets the current to the given value [A].

        This is invalid when the PMX is configured such that constant current is controlled externally.  The settings
        are set to the default values with the reset command.

        Args:
            current (float): Current to configure [A].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CURR?",
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_current_config(self) -> float:
        """Returns the actual current configuration [A].

        Returns:
            Actual current configuration [A].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="CURR:PROT ${ocp}",
        process_cmd_string=add_lf,
    )
    def set_ocp(self, ocp: float) -> None:
        """Sets the Over-Current Protection (OCP) value [A].

        Args:
            ocp (float): Over-Current Protection (OCP) [A] to configure.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CURR:PROT?",
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_ocp(self) -> float:
        """Returns the Over-Current Protection (OCP) value [A].

        Returns:
            Actual Over-Current Protection configuration [A].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="VOLT ${voltage}",
        process_cmd_string=add_lf,
    )
    def set_voltage(self, voltage: float) -> None:
        """Sets the voltage to the given value [V].

        This is invalid when the PMX is configured such that constant voltage is controlled externally.  The settings
        are set to the default values with the reset command.

        Args:
            voltage (float): Voltage to configure [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="VOLT?",
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_voltage_config(self) -> float:
        """Returns the actual voltage configuration [V].

        Returns:
            Actual voltage configuration [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="VOLT:PROT ${ovp}",
        process_cmd_string=add_lf,
    )
    def set_ovp(self, ovp: float) -> None:
        """Sets the Over-Voltage Protection (OVP) value [V].

        Args:
            ovp (float): Over-Voltage Protection (OVP) [V] to configure.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="VOLT:PROT?",
        process_cmd_string=add_lf,
        process_response=to_float,
    )
    def get_ovp(self) -> float:
        """Returns the Over-Voltage Protection (OVP) value [V].

        Returns:
            Actual Over-Voltage Protection configuration [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SYST:CONF:STAR:PRI ${priority_mode}",
        process_cmd_string=add_lf,
    )
    def set_priority_mode(self, priority_mode: PriorityMode) -> None:
        """Sets the operation mode to be prioritised when the output is turned on.

        Args:
            priority_mode (PriorityMode): Priority mode to configure.  Should be "CC" or PriorityMode.CONSTANT_CURRENT
                                          for Constant Current, "CV" or PriorityMode.CONSTANT_VOLTAGE for Constant
                                          Voltage.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SYST:CONF:STAR:PRI?",
        process_cmd_string=add_lf,
        # process_response=parse_strings,
    )
    def get_priority_mode(self) -> PriorityMode:
        """Returns the operation mode to be prioritised when the output is turned on.

        Possible values are:
            - "CC" (PriorityMode.CONSTANT_CURRENT): to prioritise constant current;
            - "CV" (PriorityMode.CONSTANT_VOLTAGE): to prioritise constant voltage.

        Returns:
            Configured priority mode.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="OUTP:PROT:CLE",
        process_cmd_string=add_lf,
    )
    def clear_alarms(self) -> None:
        """Clears all alarms."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type="query",
        cmd_string="STAT:QUES:COND?",
        process_cmd_string=add_lf,
        process_response=to_int,
    )
    def questionable_status_register(self) -> int:
        """Queries the status of the questionable status register.

        A query does not clear the content of the register.  This command is useful to get the events and status during
        PMX operation (e.g. when the PSU detects and OVP or OCP).

        Returns:
            Questionable events and status register.  The questionable status register is a 16-bit register that
            stores information related to the questionable events and status:
                - bit 0: Over-Voltage Protection (OVP) has been activated;
                - bit 1: Over-Current Protection (OCP) has been activated;
                - bit 2: AC power failure or power interruption;
                - bit 3: Not used;
                - bit 4: Over-Temperature Protection has been activated;
                - bit 5..15: Not used.
        """

        raise NotImplementedError
