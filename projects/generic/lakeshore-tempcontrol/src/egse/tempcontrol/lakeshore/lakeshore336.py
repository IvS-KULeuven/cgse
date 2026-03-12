from enum import IntEnum

from egse.device import DeviceInterface
from egse.mixin import dynamic_command, CommandType, add_lf
from egse.proxy import Proxy
from egse.randomwalk import RandomWalk
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.tempcontrol.lakeshore.lakeshore336_devif import LakeShore336EthernetInterface
from egse.zmq_ser import connect_address

CTRL_SETTINGS = Settings.load("LakeShore336 Control Server")


def split_response(response) -> list[float]:
    return response.split(",")


class SelfTestResult(IntEnum):
    """Possible results of the selftest."""

    NO_ERRORS_FOUND = 0
    ERRORS_FOUND = 1


class AutotuneMode(IntEnum):
    """Possible autotune modes."""

    PROPORTIONAL = P = 0  # P only
    PROPORTIONAL_INTEGRAL = PI = 1  # P and I
    PROPORTIONAL_INTEGRAL_DERIVATIVE = PID = 2  # P, I, and D


class HeaterQuantity(IntEnum):
    """Possible heater quantities."""

    CURRENT = 1
    POWER = 2


class HeaterRange(IntEnum):
    """Possible heater ranges."""

    OFF = 0  # Output 1 - 4
    LOW = 1  # Output 1 & 2
    MEDIUM = 2  # Output 1 & 2
    HIGH = 3  # Output 1 & 2

    ON = 1  # Output 3 & 4


class Mode(IntEnum):
    """Possible operating modes."""

    LOCAL = 0
    REMOTE = 1
    REMOTE_WITH_LOCAL_LOCKOUT = 2


class DisplayMode(IntEnum):
    """Possible display modes."""

    INPUT_A = 0
    INPUT_B = 1
    INPUT_C = 2
    INPUT_D = 3
    CUSTOM = 4
    FOUR_LOOP = 5
    ALL_INPUTS = 6


class SensorType(IntEnum):
    """Possible sensor types."""

    DISABLED = 0
    DIODE = 1  # 3062 option only
    PTC_RTD = 2
    NTC_RTD = 3
    THERMOCOUPLE = 4  # 3060 option only
    CAPACITANCE = 5  # 3060 option only


class InputSimulator:
    def __init__(self, input: str) -> None:
        self.input = input
        self.name = None
        self.type = None
        self.temperature_limit = None
        self.min_temperature = None
        self.max_temperature = None

        self.randomwalk = RandomWalk(start=15, boundary=(-100, 25), scale=0.01, count=0)

    def get_temperature(self):
        return next(self.randomwalk)


class OutputSimulator:
    def __init__(self, output: int) -> None:
        self.output = output
        self.resistance_setting = None
        self.max_current_setting = None
        self.max_user_current = None
        self.heater_quantity = None

        self.proportional = self.p = None
        self.integral = self.i = None
        self.derivative = self.d = None

        self.temperature_setpoint = None
        self.heater_range = None

    def set_pid_parameters(self, p, i, d):
        self.p = p
        self.i = i
        self.d = d

    def get_pid_parameters(self):
        return self.p, self.i, self.d


class LakeShore336Interface(DeviceInterface):
    """Interface for the LakeShore336 Controller, Simulator, and Proxy."""

    def __init__(self, device_id: str):
        """Initialisation of a LakeShore336 interface.

        Args:
            device_id (str): Device identifier
        """

        super().__init__()

        self.device_id = device_id

    @dynamic_command(cmd_type=CommandType.READ, cmd_string="*IDN?", process_cmd_string=add_lf)
    def info(self) -> (str, str, str, float):
        """Identification query.

        Returns basic information about the device.

        Returns: Tuple with the following information:
            - Manufacturer identifier (e.g. "LSCI");
            - Instrument model number (e.g. "MODEL336");
            - Instrument serial number / Option card serial number (e.g. "1234567/1234567");
            - Instrument firmware version (e.g. 1.0)
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="*CLS", process_cmd_string=add_lf)
    def clear_interface(self):
        """Clear interface command.

        Clears the bits in the status byte register, standard event status register, and operation event register, and
        terminates all pending operations.  Clears the interface but not the controller.  The related controller
        command is `reset_instrument`."""

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="*RST", process_cmd_string=add_lf)
    def reset_instrument(self):
        """Reset instrument command.

        Sets the controller parameters to power-up settings.
        """

        raise NotImplementedError

    # # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="*ESE", process_cmd_string=add_lf)
    #
    # # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="*ESE?", process_cmd_string=add_lf)
    #
    # # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="*ESR?", process_cmd_string=add_lf)

    @dynamic_command(cmd_type=CommandType.READ, cmd_string="TST?", process_cmd_string=add_lf)
    def get_selftest_result(self) -> int:
        """Selftest query.

        Reports status based on test done at power-up.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="ATUNE ${output_channel}, ${mode}")
    def autotune(self, output_channel: int, mode: AutotuneMode):
        """Autotune command.

        Configures autotune parameters.

        Args:
            output_channel (int): Output associated with the loop to be autotuned (1 - 4)
            mode (int): Autotune mode to start using:
                - 0 (AutotuneMode.PROPORTIONAL / AutotuneMode.P): Autotune in proportional mode;
                - 1 (AutotuneMode.PROPORTIONAL_INTEGRAL / AutotuneMode.PI): Autotune in proportional and integral mode;
                - 2 (AutotuneMode.PROPORTIONAL_INTEGRAL_DERIVATIVE / AutotuneMode.PID): Autotune in proportional,
                  integral, and derivative mode.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.READ, cmd_string="TUNEST?", process_cmd_string=add_lf)
    def get_tuning_status(self):
        """Control tuning status query.

        Returns:
            Tuning status (int):
                - 0: No active tuning
                - 1: Active tuning
            Heater output (int) of the control loop being tuned (when tuning)
                - 1: Heater output 1
                - 2: Heater output 2
            Error status (int):
                - 0: No tuning error
                - 1: Tuning error
            Current stage in the autotuning process that failed, if any (when tuning)

        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.READ, cmd_string="CRDG? {input_channel}", process_cmd_string=add_lf)
    def get_temperature(self, input_channel: str):
        """Celsius reading query.

        Args:
            input_channel (str): Input channel for which to return the current temperature

        Returns the current temperature reading for the specified input channel.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.READ, cmd_string="HTR? ${output_channel}", process_cmd_string=add_lf)
    def get_heater_output(self, output_channel: int):
        """Heater output query.

        Returns the heater output.

        Args:
            output_channel (int): Heater output to query (1 or 2)

        Returns: Heater output in percentage.
        """

        raise NotImplementedError

    #
    # # @dynamic_command(cmd_type=CommandType.READ, cmd_string="HTRSET?", process_cmd_string=add_lf)
    # # def get_heater_setup(self, output: int) -> (int, int, float, int):
    # #     """ Returns the heater setup.
    # #
    # #     Args:
    # #         output (int): Specifies heater output to query (1 or 2)
    # #
    # #     Returns: Heater setup:
    # #         - Heater resistance setting (int):
    # #             - 1: 25 Ohm;
    # #             - 2: 50 Ohm.
    # #         - Maximum heater output setting (int):
    # #             - 0: user-specified;
    # #             - 1: 0.707A;
    # #             - 2: 1A;
    # #             - 3: 1.141A;
    # #             - 4: 2A.
    # #         - Maximum user current (float)
    # #         - Heater quantity, specifying whether the heater output should be displayed in current
    # #           (HeaterQuantity.CURRENT / 1) or in power (HeaterQuantity.POWER / 2)
    # #
    # #     """
    # #
    # #     raise NotImplementedError
    # #
    # # @dynamic_command(cmd_type=CommandType.READ, cmd_string="HTRST?", process_cmd_string=add_lf)
    # # def get_heater_status(self, output: int) -> int:
    # #     """ Returns the heater status for the given output.
    # #
    # #     The error condition is cleared upon querying the heater status, which will also clear the error message on the
    # #     front panel.
    # #
    # #     Args:
    # #         output (int): Specifies heater output to query (1 or 2)
    # #
    # #     Returns: Heater status for the given output:
    # #         - 0: No error;
    # #         - 1: Heater open load;
    # #         - 2: Heater short.
    # #     """
    # #
    # #     raise NotImplementedError
    # # # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="*SRE", process_cmd_string=add_lf())
    # #
    # # # @dynamic_command(cmd_type=CommandType.READ, cmd_string="*SRE?", process_cmd_string=add_lf())
    # #
    # # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="MODE ${mode}", process_cmd_string=add_lf)
    # # def set_mode(self, mode: Mode):
    # #     """ Places the controller in the given mode.
    # #
    # #     Args:
    # #         mode (Mode): Interface mode:
    # #             - 0 (Mode.LOCAL): Local mode;
    # #             - 1 (Mode.REMOTE): Remote mode;
    # #             - 2 (Mode.REMOTE_WITH_LOCAL_LOCKOUT): Remote mode with local lockout.
    # #     """
    # #
    # #     raise NotImplementedError
    # #
    # # @dynamic_command(cmd_type=CommandType.READ, cmd_string="MODE?", process_cmd_string=add_lf)
    # # def get_mode(self) -> int:
    # #     """ Returns the mode of the controller.
    # #
    # #     Returns: Mode of the controller:
    # #         - 0 (Mode.LOCAL): Local mode;
    # #         - 1 (Mode.REMOTE): Remote mode;
    # #         - 2 (Mode.REMOTE_WITH_LOCAL_LOCKOUT): Remote mode with local lockout.
    # #     """
    # #
    # #     raise NotImplementedError
    # #
    # # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="MOUT ${output}, ${value}", process_cmd_string=add_lf)
    # # def set_manual_output(self, output: int, value: float):
    # #     """ Sets the output value for the given output.
    # #
    # #     Args:
    # #         output (int): Specifies heater output
    # #         value (float): New value for the given heater output.
    # #     """
    # #
    # #     raise NotImplementedError
    # #
    # # @dynamic_command(cmd_type=CommandType.READ, cmd_string="MOUT?", process_cmd_string=add_lf)
    # # def get_manual_output(self, output: int):
    # #     """ Returns the output value for the given output.
    # #
    # #     Args:
    # #         output (int): Specifies heater output
    # #
    # #     Returns: Output value for the given output.
    # #    """
    # #
    # #     raise NotImplementedError
    # #
    # # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="DISPLAY ${mode}, ${num_fields}, ${output_source}", process_cmd_string=add_lf)
    # # def set_display_setup(self, mode: DisplayMode, num_fields: int, output_source: int):
    # #     """ Specifies the display mode.
    # #
    # #     Args:
    # #         mode (DisplayMode): Display mode:
    # #             - 0 (DisplayMode.INPUT_A);
    # #             - 1 (DisplayMode.INPUT_B);
    # #             - 2 (DisplayMode.INPUT_C);
    # #             - 3 (DisplayMode.INPUT_D);
    # #             - 4 (DisplayMode.CUSTOM);
    # #             - 5 (DisplayMode.FOUR_LOOP);
    # #             - 6 (DisplayMode.ALL_INPUTS)
    # #         num_fields (int): When `mode` is set to DisplayMode.CUSTOM, specifies the number of fields (display
    # #                           locations) to display:
    # #                                 - 0: 2 large;
    # #                                 - 1: 4 large;
    # #                                 - 2: 8 small.
    # #                           When `mode` is set to DisplayMode.All_INPUTS, specifies the size of hte readings:
    # #                                 - 0: Small with input names;
    # #                                 - 1: Large without input names.
    # #                           Ignored in all display modes (`mode`) except DisplayMode.CUSTOM.
    # #
    # #         output_source (int): Specifies which output and associated loop information to display in the bottom half
    # #                              of the custom display screen:
    # #                                 - 1: Output 1;
    # #                                 - 2: Output 2;
    # #                                 - 3: Output 3;
    # #                                 - 4: Output 4.
    # #                              Ignored in all display modes (`mode`) except DisplayMode.CUSTOM.
    # #     """
    # #
    # #     raise NotImplementedError
    # #
    # # @dynamic_command(cmd_type=CommandType.READ, cmd_string="DISPLAY?", process_cmd_string=add_lf)
    # # def get_display_setup(self):
    # #     """ Returns the display setup.
    # #
    # #
    # #     """
    # #
    # #     raise NotImplementedError
    #
    # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="TLIMIT ${input}, ${limit}", process_cmd_string=add_lf)
    # def set_temperature_limit(self, input: str, limit: float):
    #     """ Sets temperature limit for the given input.
    #
    #     Args:
    #         input (str): Specifies which input to configure
    #         limit (float): Temperature limit [K] for which to shut down all control units when exceeded.  A temperature
    #                        limit of zero turns the temperature limit feature off for the given sensor input.
    #
    #     """
    #
    #     raise NotImplementedError
    #
    # @dynamic_command(cmd_type=CommandType.READ, cmd_string="TLIMIT? ${input}", process_cmd_string=add_lf)
    # def get_temperature_limit(self, input: str):
    #     """ Returns the temperature limit for the given input.
    #
    #     Args:
    #         input (str): Specifies for which input to return the temperature
    #
    #     Returns: Temperature limit for the given input [K]
    #     """
    #
    #     raise NotImplementedError
    #
    #
    # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="INNAME ${input}, ${name}", process_cmd_string=add_lf)
    # def set_input_name(self, input: str, name: str):
    #
    #     raise NotImplementedError
    #
    # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="INNAME? ${input}", process_cmd_string=add_lf)
    # def get_input_name(self, input: str):
    #
    #     raise NotImplementedError
    #
    #
    # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="HTRSET ${output}, ${resistance_setting}, ${max_current_setting}, ${max_user_current}, ${heater_quantity}", process_cmd_string=add_lf)
    # def set_heater_setup(self, output: int, resistance_setting: int, max_current_setting: float, max_user_current: float, heater_quantity: HeaterQuantity):
    #     """ Sets the heater setpoint.
    #
    #     Args:
    #         output (int): Heater output to configure (1 or 2)
    #         resistance_setting (int): Heater resistance setting
    #             - 1: 25 Ohm;
    #             - 2: 50 Ohm.
    #         max_current_setting (int): Specifies the maximum heater output current:
    #             - 0: user-specified;
    #             - 1: 0.707A;
    #             - 2: 1A;
    #             - 3: 1.141A;
    #             - 4: 2A.
    #         max_user_current (float): Maximum heater output if `max_current_setting` is set to 0 (user-specified)
    #         heater_quantity (HeaterQuantity): Specifies whether the heater output should be displayed in current
    #                                           (HeaterQuantity.CURRENT / 1) or in power (HeaterQuantity.POWER / 2)
    #     """
    #
    #     raise NotImplementedError

    # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="PID ${output}, ${proportional}, ${integral}, ${derivative}", process_cmd_string=add_lf)
    # def set_pid_parameters(self, output: int, proportional: float, integral: float, derivative: float):
    #     """ Control loop PID values query.
    #
    #
    #     """
    #
    #     raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.READ,
        cmd_string="PID? ${output_channel}",
        process_cmd_string=add_lf,
        post_cmd=split_response,
    )
    def get_pid_parameters(self, output_channel: int):
        """Control loop PID values query.

        Args:
            output_channel (int): Output channel for which to return the control loop PID parameters

        Returns: Control loop PID values for the given output channel.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.READ,
        cmd_string="SETP? {output_channel}",
        process_cmd_string=add_lf,
        post_cmd=split_response,
    )
    def get_temperature_setpoint(self, output_channel: int):
        """Control setpoint query.

        Args:
            output_channel (int): Output channel for which to return the control setpoint (1 - 4)

        Returns: Temperature setpoint for the given output channel [°C]
        """

    def quit(self):
        """Cleans up and stops threads that were started by the process."""

        pass

    # @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="SETP ${output}, ${temperature}")
    # def set_temperature_setpoint(self, output: int, temperature: float):
    #
    #     raise NotImplementedError
    #
    # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="RANGE ${output}, ${range}", process_cmd_string=add_lf)
    # def set_heater_range(self, output: int, range: int):
    #
    #     raise NotImplementedError
    #
    # @dynamic_command(cmd_type=CommandType.READ, cmd_string="RANGE? ${output}", process_cmd_string=add_lf)
    # def get_heater_range(self, output: int):
    #
    #     raise NotImplementedError


class LakeShore336Controller(LakeShore336Interface):
    def __init__(self, device_id: str):
        super().__init__(device_id)

        self.lakeshore = self.transport = LakeShore336EthernetInterface(device_id)

    def is_simulator(self) -> bool:
        return False

    def is_connected(self) -> bool:
        return self.lakeshore.is_connected()

    def connect(self):
        self.lakeshore.connect()

    def disconnect(self):
        self.lakeshore.disconnect()

    def reconnect(self):
        self.lakeshore.reconnect()

    def quit(self):
        # self.synoptics.disconnect_cs()

        pass


class LakeShore336Simulator(LakeShore336Interface):
    def __init__(self, device_id: str):
        super().__init__(device_id)

        self._is_connected = True

        self.manufacturer = "LakeShore"
        self.model = "LSCI336"
        self.instrument_serial_number = 1234567
        self.option_card_serial_number = 1234567
        self.firmware_version = 1.0

        self.input = {}
        for i in range(ord("A"), ord("D") + 1):
            self.input[chr(i)] = InputSimulator(chr(i))

        self.output = [None, OutputSimulator(1), OutputSimulator(2)]

    def is_simulator(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self):
        self._is_connected = True

    def disconnect(self):
        self._is_connected = False

    def reconnect(self):
        self._is_connected = True

    def info(self) -> (str, str, str, float):
        return (
            self.manufacturer,
            self.model,
            f"{self.instrument_serial_number}/{self.option_card_serial_number}",
            self.firmware_version,
        )

    def clear_interface(self):
        pass

    def reset_instrument(self):
        pass

    def get_selftest_result(self):
        # No errors found

        return SelfTestResult.NO_ERRORS_FOUND.value

    def autotune(self, output_channel: int, mode: AutotuneMode):
        pass

    def get_tuning_status(self):
        # TODO
        pass

    # def get_selftest_result(self):
    #
    #     return SelfTestResult.NO_ERRORS_FOUND
    #
    #
    # def set_input_name(self, input: str, name: str):
    #
    #     self.input[input].name = name
    #
    # def get_input_name(self, input: str):
    #
    #     return self.input[input].name
    #
    # def set_temperature_limit(self, input: str, limit: float):
    #
    #     self.input[input].temperature_limit = limit
    #
    # def get_temperature_limit(self, input: str):
    #
    #     return self.input[input].temperature_limit
    #
    # def set_heater_setup(self, output: int, resistance_setting: int, max_current_setting: float, max_user_current: float, heater_quantity: HeaterQuantity):
    #
    #     self.output[output].resistance_setting = resistance_setting
    #     self.output[output].max_current_setting = max_current_setting
    #     self.output[output].max_user_current = max_user_current
    #     self.output[output].heater_quantity = heater_quantity
    #
    # def set_pid_parameters(self, output: int, proportional: float, integral: float, derivative: float):
    #
    #     self.output[output].set_pid_parameters(proportional, integral, derivative)

    def set_pid_parameters(self, output: int, p: float, i: float, d: float):
        self.output[output].set_pid_parameters(p, i, d)

    def get_pid_parameters(self, output: int):
        return self.output[output].get_pid_parameters()

    # def set_temperature_setpoint(self, output: int, temperature: float):
    #
    #     self.output[output].temperature_setpoint = temperature

    def get_temperature_setpoint(self, output_channel: int):
        return self.output[output_channel].temperature_setpoint

    #
    # def set_heater_range(self, output: int, range: int):
    #
    #     self.output[output].heater_range = range
    #
    # def get_heater_range(self, output: int):
    #
    #     return self.output[output].heater_range

    def set_heater_output(self, output_channel: int, heater_output: float):
        self.output[output_channel].output = heater_output

    def get_heater_output(self, output_channel: int):
        return self.output[output_channel].output

    def get_temperature(self, input_channel: str):
        return self.input[input_channel].get_temperature()


class LakeShore336Proxy(Proxy, LakeShore336Interface):
    """Proxy to connect to a LakeShore 336 Control Server"""

    def __init__(self, device_id: str):
        """Proxy to connect to the LakeShore 336 with the given device identifier

        Args:
            device_id (str): Device identifier
        """

        with RegistryClient() as reg:
            service = reg.discover_service(device_id)

            if service:
                protocol = service.get("protocol", "tcp")
                hostname = service["host"]
                port = service["port"]
            else:
                raise RuntimeError(f"No service registered as {CTRL_SETTINGS.SERVICE_TYPE}")

        super().__init__(connect_address(protocol, hostname, port))
