"""
This module provides the implementation of the commanding interfaces for the Alpha and Alpha+
controller using the new dynamic commanding scheme. The three main classes are the `AlphaPlusTelnetInterface`,
the `AlphaControllerInterface` and the `AlphaPlusControllerInterface`.

The `AlphaPlusTelnetInterface` directly talks to the device through the telnet protocol on port 23.

The `AlphaControllerInterface` provides an interface with methods that are compatible with both the Alpha controller
and the AlphaPlusController. This interface shall be sub-classed for proxy and controller classes that use the
alpha controller, like the PUNA Hexapod.

The `AlphaPlusControllerInterface` inherits from the `AlphaControllerInterface` and provides additional methods
that are specific for the alpha+ controllers. This class should be sub-classed for proxy and controller classes
that use the alpha+ controller, like the ZONDA hexapod.

"""
from __future__ import annotations

import logging
from functools import partial
from telnetlib import Telnet
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Tuple

from egse.control import Failure
from egse.control import Success
from egse.device import DeviceConnectionError
from egse.device import DeviceConnectionInterface
from egse.device import DeviceInterface
from egse.device import DeviceTransport
from egse.mixin import add_cr_lf
from egse.mixin import dynamic_command
from egse.settings import Settings
from egse.system import Timer
from egse.system import wait_until

LOGGER = logging.getLogger(__name__)
PUNA_PLUS = Settings.load("PUNA Alpha+ Controller")

# The following constants represent the index into the GENERAL_STATE list and are used in the code
# to match the name of a flag in the general_state.

HOME_COMPLETE = 6
IN_POSITION = 3
IN_MOTION = 4

GENERAL_STATE = [
    "Error",
    "System initialized",
    "Control on",
    "In position",
    "Motion task running",
    "Home task running",
    "Home complete",
    "Home virtual",
    "Phase found",
    "Brake on",
    "Motion restricted",
    "Power on encoders",
    "Power on limit switches",
    "Power on drives",
    "Emergency stop",
]


ACTUATOR_STATE = [
    "Error",
    "Control on",
    "In position",
    "Motion task running",
    "Home task running",
    "Home complete",
    "Phase found",
    "Brake on",
    "Home hardware input",
    "Negative hardware limit switch",
    "Positive hardware limit switch",
    "Software limit reached",
    "Following error",
    "Drive fault",
    "Encoder error",
]


ERROR_CODES = {
    1: "An emergency stop has been pressed.",
    2: "A safety input has been triggered. The status of the inputs is given in the DATA field.",
    3: "A temperature sensor has exceeded the limit threshold. Sensor number is given in DATA field.",
    4: "Controller system status error (Sys.Status).",
    5: "Controller ‘abort all’ input has been triggered. (Sys.AbortAll).",
    6: "Controller watchdog error (Sys.WDTFault).",
    7: "Configuration load error.",
    8: "Configuration failed: a wrong hexapod ID has been detected. Detected ID is given in DATA field.",
    9: "Home task has failed.",
    10: "Virtual home write task has failed.",
    11: "The motion program did not start in the defined timeout.",
    12: "The home task did not start in the defined timeout.",
    13: "A kinematic error has occurred. Kinematic error number is given in DATA field.",
    14: "Controller coordinate error status (Coord.ErrorStatus). Error number is given in DATA field.",
    15: "An error has been detected on encoder.",
    16: "Brake should have been engaged as the motor control was off.",
    17: "Controller motor status: Auxiliary fault (AuxFault).",
    18: "Controller motor status: Encoder loss (EncLoss).",
    19: "Controller motor status: Amplifier warning (AmpWarn).",
    20: "Controller motor status: Trigger not found (TriggerNotFound).",
    21: "Controller motor status: Integrated current 'I2T' fault (I2tFault).",
    22: "Controller motor status: Software positive limit reach (SoftPlusLimit).",
    23: "Controller motor status: Software negative limit reach (SoftMinusLimit).",
    24: "Controller motor status: Amplifier fault (AmpFault).",
    25: "Controller motor status: Stopped on hardware limit (LimitStop).",
    26: "Controller motor status: Fatal following error (FeFatal).",
    27: "Controller motor status: Warning following error (FeWarn).",
    28: "Controller motor status: Hardware positive limit reach (PlusLimit).",
    29: "Controller motor status: Hardware negative limit reach (MinusLimit).",
}


RETURN_CODES = {
    0: "Success.",
    -1: "Undefined error.",
    -10: "Wrong value for parameter at index 0.",
    -11: "Wrong value for parameter at index 1.",
    -12: "Wrong value for parameter at index 2.",
    -13: "Wrong value for parameter at index 3.",
    -14: "Wrong value for parameter at index 4.",
    -15: "Wrong value for parameter at index 5.",
    -16: "Wrong value for parameter at index 6.",
    -17: "Wrong value for parameter at index 7.",
    -18: "Wrong value for parameter at index 8.",
    -19: "Wrong value for parameter at index 9.",
    -20: "Wrong value for parameter at index 10.",
    -21: "Wrong value for parameter at index 11.",
    -22: "Wrong value for parameter at index 12.",
    -23: "Wrong value for parameter at index 13.",
    -24: "Wrong value for parameter at index 14.",
    -25: "Wrong value for parameter at index 15.",
    -26: "Wrong value for parameter at index 16.",
    -27: "Wrong value for parameter at index 17.",
    -28: "Wrong value for parameter at index 18.",
    -29: "Wrong value for parameter at index 19.",
    -30: "Unknown command number.",
    -31: "This configuration command is a 'get' only type.",
    -32: "This configuration command is a 'set' only type.",
    -33: "The axis number do not correspond to an axis defined on the controller.",
    -34: "A stop task is running.",
    -35: "All motors need to be control on.",
    -36: "All motors need to be control off.",
    -37: "Emergency stop is pressed.",
    -38: "A motion task is running.",
    -39: "A home task is running.",
    -40: "Requested move is not feasible.",
    -41: "Power supply of limit switches is off.",
    -42: "Power supply of encoders is off.",
    -43: "A fatal error is present. This type of error needs a controller restart to be removed.",
    -44: "An error is present, error reset is required.",
    -45: "Home is not completed.",
    -46: "Software option not available (can be linked to hardware configuration).",
    -47: "Virtual home: file was created on another controller (different MAC address).",
    -48: "Virtual home: some positions read in file are out of software limits.",
    -49: "Virtual home: file data were stored while hexapod was moving.",
    -50: "Virtual home: no data available.",
    -51: "Command has been rejected because another action is running.",
    -52: "Timeout waiting for home complete status.",
    -53: "Timeout waiting for control on status.",
    -54: "Timeout on motion program start.",
    -55: "Timeout on home task start.",
    -56: "Timeout on virtual home write file task.",
    -57: "Timeout on virtual home delete file task.",
    -58: "Timeout on virtual home read file task.",
    -59: "Timeout on disk access verification task.",
    -60: "Configuration file: save process failed.",
    -61: "Configuration file: loaded file is empty.",
    -62: "Configuration file: loaded data are corrupted.",
    -63: "No access to the memory disk.",
    -64: "File does not exist.",
    -65: "Folder access failed.",
    -66: "Creation of folder tree on the memory disk failed.",
    -67: "Generation or write of the checksum failed.",
    -68: "File read: no data or wrong data size.",
    -69: "File read: no checksum.",
    -70: "File read: incorrect checksum.",
    -71: "File write: failed.",
    -72: "File open: failed.",
    -73: "File delete: failed.",
    -74: "Get MAC address failed.",
    -75: "NaN (Not a Number) or infinite value found.",
    -76: "The coordinate system transformations are not initialized.",
    -77: "A kinematic error is present.",
    -78: "The motor phase process failed (phase search or phase set from position offset).",
    -79: "The motor phase is not found.",
    -80: "Timeout waiting for control off status.",
    -81: "The requested kinematic mode (number) is not defined for the machine.",
    -82: "Timeout waiting for phase found status.",
    -1000: "Internal error: 'RET_Dev_CfS_NaNReturned'.",
    -1001: "Internal error: 'RET_Dev_CfS_FctNotAvailableInKernel'.",
    -1002: "Internal error: 'RET_Dev_CfS_UndefinedCfSType'.",
    -1003: "Internal error: 'RET_Dev_CfS_FIO_UndefinedFioType'.",
    -1004: "Internal error: 'RET_Dev_CfS_FIO_HomeFile_UndefinedAction'.",
    -1005: "Internal error: 'RET_Dev_UndefinedEnumValue'.",
    -1006: "Internal error: 'RET_Dev_LdataCmdStatusIsNegative'.",
    -1007: "Internal error: 'RET_Dev_NumMotorsInCoord_Sup_DEF_aGrQ_SIZE'.",
    -1008: "Internal error: 'RET_Dev_NumMotorsInCoord_WrongNumber'.",
    -1009: "Internal error: 'RET_String_StrCat_DestSizeReached'.",
    -1010: "Internal error: 'RET_String_LengthOverStringSize'.",
    -1011: "Internal error: 'RET_String_AllCharShouldIntBetween_0_255'.",
    -1012: "Internal error: 'RET_String_StrCpy_DestSizeReached'.",
    -1013: "Internal error: 'RET_ErrAction_HomeReset'.",
    -1014: "Internal error: 'RET_Home_StopReceivedWhileRunning'.",
    -1015: "Internal error: 'RET_UndefinedKinAssembly'.",
    -1016: "Internal error: 'RET_WrongPmcConfig'.",
}


VALIDATION_LIMITS = [
    "Factory workspace limits",
    "Machine workspace limits",
    "User workspace limits",
    "Actuator limits",
    "Joints limits",
    "Due to backlash compensation",
]


def process_cmd_string(command: str) -> str:
    """
    Prepares the command string for sending to the controller.
    A carriage return and newline is appended to the command.
    """

    return add_cr_lf(command)


def wait_until_cmd_is_zero(transport: DeviceTransport, timeout: float = 1.0, interval: float = 0.01):
    """
    Waits until the `cmd` register is 0 (zero) and returns successfully if it does.
    When the `cmd` register doesn't turn zero within the given timeout, a Failure is returned.
    """
    rc = 0

    def c_cmd():
        nonlocal rc
        rc_s = transport.query('c_cmd\r\n').decode()
        LOGGER.debug(f"{rc_s = } <- c_cmd in get_pars")
        if not rc_s.startswith('c_cmd'):
            LOGGER.warning(f"{rc_s = }")
            return -1
        rc = int(rc_s.split('\r\n')[1])
        return rc

    if wait_until(lambda: c_cmd() == 0, interval=interval, timeout=timeout):
        try:
            LOGGER.warning(f"Command check timed out: {RETURN_CODES[rc]} [{rc=}]")
            return Failure(f"Command check resulted in the following error: {RETURN_CODES[rc]}")
        except KeyError:
            return Failure(f"Command check resulted in an unknown error code: {rc = }.")

    return Success("Command finished successfully")


def get_pars(
        transport: DeviceTransport = None, response: bytes = None,
        index: int = 0, count: int = 1, increment: int = 1, timeout: float = 1.0, interval: float = 0.01
) -> bytes | Failure:
    """
    Retrieve the response from a given command from the `c_par` array. The `c_par` array will
    contain the correct values only after the `cmd` register is 0 (zero). So, we will wait until
    `cmd` becomes 0, then retrieve the requested parameters from the `c_par` array and return
    them as a normal response to be processed.

    This function is intended to be used as a `post_cmd` function in the dynamic command decorator.

    Args:
        transport: the transport interface to communicate with the device
        response: the response from the actual command that was sent
        index: starting index for the `c_par` array
        count: the number of c_par values to retrieve
        increment: the increment in the c_par array
        timeout: the timeout period while waiting for the `cmd` to become 0
        interval: the sampling interval for the `cmd`

    Returns:
        The requested values from the `c_par` array as a string. This string can be decoded with
        the `decode_pars()` function.
    """

    if transport is None:
        raise RuntimeError("no device transport was passed into the function!")

    rc = wait_until_cmd_is_zero(transport=transport, interval=interval, timeout=timeout)
    if isinstance(rc, Failure):
        return rc

    # The string 'c_par(0),1,1' is considered illegal.

    if count == 1 and increment == 1:
        query = f"c_par({index})"
    else:
        query = f"c_par({index}),{count},{increment}"

    response = transport.query(f'{query}\r\n')

    LOGGER.debug(f"{response = } <- {query} in get_pars")

    return response


def return_command_status(transport: DeviceTransport = None, response: bytes = None,
                          timeout: float = 1.0, interval: float = 0.01) -> Tuple[int, str] | Failure:
    """
    Check the status of last sent command. When the status is zero (0) the command was successfully executed.
    When the status is not zero before timeout seconds, the status check will be aborted and the function
    will then return the latest status code from the `c_cmd` variable.

    Note: This function shall be used as a `post_cmd` callable in the dynamic_command decorator and the process_response
          shall not be used in conjunction with this command.

    Args:
        transport: the device transport that can be used send additional commands to the device
        response: The response from the command that was sent to the device (ignored by this function)
        timeout: number of seconds before a timeout will occur
        interval: sleep time between checks for the status condition

    Returns:
        The status of the last sent command as a tuple (status code, description).

    Raises:
        A RuntimeError is raised when no device transport is passed into this function.
    """

    # The response argument is ignored in this function as it generates a new response from the
    # command return code.

    if transport is None:
        raise RuntimeError("no device transport was passed into the function!")

    rc = 0

    def c_cmd():
        nonlocal rc
        rc_s = transport.query('c_cmd\r\n').decode()
        LOGGER.debug(f"{rc_s = } <- c_cmd in check_command_status")
        if not rc_s.startswith('c_cmd'):
            LOGGER.warning(f"{rc_s = }")
            return -1
        rc = int(rc_s.split('\r\n')[1])
        return rc

    if wait_until(lambda: c_cmd() == 0, interval=interval, timeout=timeout):
        LOGGER.warning(f"Command check: {RETURN_CODES[rc]} [{rc}]")
    else:
        LOGGER.debug("Success!")
        rc = 0

    return rc, RETURN_CODES[rc]


def check_command_status(transport: DeviceTransport = None, response: bytes = None,
                         timeout: float = 1.0, interval: float = 0.01) -> Any:
    """
    Check the state of last sent command. When the state is zero (0) the command was successfully executed. When the
    status is not zero before timeout seconds, the status check will be aborted and a warning message will be issued.
    This function will then return a Failure containing the latest status code from the `c_cmd` variable.

    The status can take the following values:

    * > 1: a new command has been written but has not yet been interpreted by the communication application
    * = 1: the last written command is currently under execution
    * = 0: the last command was successfully executed
    * < 0: the last command failed. This status code can be used to determine the cause of the error from
      the RETURN_CODES variable in this module.

    Note: This function shall be used as a `post_cmd` callable in the dynamic_command decorator.

    Args:
        transport: the device transport that can be used send additional commands to the device
        response: The response from the command that was sent to the device
        timeout: number of seconds before a timeout will occur
        interval: sleep time between checks for the status condition

    Returns:
        This function passes through the response without change. When the status check timed out
        a Failure will be returned with an associated error message.

    Raises:
        A RuntimeError is raised when no device transport is passed into this function.
    """
    if transport is None:
        raise RuntimeError("no device transport was passed into the function!")

    rc = wait_until_cmd_is_zero(transport=transport, interval=interval, timeout=timeout)
    return rc if isinstance(rc, Failure) else response


def decode_response(response: bytes) -> str | Failure:
    """Decodes the bytes object, strips off the trailing 'CRLF'."""

    LOGGER.debug(f"{response = } <- decode_response")

    return response.decode().rstrip()


def validate_response(response: str, cmd: str = None) -> List[str] | Failure:
    """
    Performs a number of checks on the response string and returns the response as a list of strings.
    The command string (which is the first part of the device response) is removed from the returned list.

    Args:
        response: decoded response from the device
        cmd: the command string that is returned by the device

    Returns:
        A list of strings containing the split response without the first item (which was the command string).
        If the response contains the string 'error #', a Failure will be returned with the error message.
        If the response doesn't start with the given command string (when cmd != None), a Failure is returned.
    """
    if "error #" in response:
        msg = response.split("\r\n")[-1]  # this will strip off the cmd part of the response
        return Failure(msg)

    if cmd is not None and not response.startswith(cmd):
        return Failure(f"Unexpected response from '{cmd}' command: {response}")

    LOGGER.debug(f"{response = } <- validate_response")

    return response.split("\r\n")[1:]


def process_response(response: bytes, cmd: str = None) -> List[str] | Failure:
    """This function is a shortcut for decode_response() and validate_response()."""

    # You might think this shortcut is really useless and doesn't give us anything,
    # the thing is that this function is used in the decorator, which is not possible
    # for each function individually.

    return validate_response(decode_response(response), cmd)


def process_validate_ptp(response: bytes) -> Tuple[int, Dict[int, str]] | Failure:
    """
    The response is in this case the value of 'c_par(0)' which is returned by the `post_cmd` function `get_pars`.

    Args:
        response:

    Returns:

    """
    response = process_response(response)

    if isinstance(response, Failure):
        return response

    response = int(response[0])

    if response == 0:
        return 0, {}

    if response > 0:
        description = decode_validation_error(response)
        return response, description

    # When response is negative, the validation failed, and we extract the command return code

    msg = f"{RETURN_CODES.get(response, 'unknown error code')}"

    LOGGER.error(f"Validate position: error code={response} - {msg}")

    return response, {response: msg}


def issue_warning(*, response, msg: str):
    LOGGER.warning(f"{msg} {response}")
    return response


from typing import TypeVar

T = TypeVar('T', float, int)      # Declare type variable


def decode_pars(response: bytes = None, index: int = 0, count: int = 1, func: Callable = float) -> List[T] | Failure:
    response = process_response(response)

    if isinstance(response, Failure):
        return response

    return [func(x) for x in response[index:index+count]]


def decode_info(response: bytes) -> str | Failure:
    response = process_response(response)

    if isinstance(response, Failure):
        return response

    LOGGER.debug(f"{response = } <- decode_info")

    return (
        f"Info about the Hexapod Alpha+ Controller:\n"
        f"  Software version = {response[1]}.{response[2]}.{response[3]}.{response[4]}\n"
        f"  API version = {response[5]}.{response[6]}.{response[7]}.{response[8]}\n"
        f"  System Configuration version = {response[11]}"
    )


def decode_version(response: bytes) -> str | Failure:
    response = validate_response(decode_response(response))

    if isinstance(response, Failure):
        return response

    return f"{response[5]}.{response[6]}.{response[7]}.{response[8]}"


def decode_uto(response: bytes) -> List[float] | Failure:
    response = validate_response(decode_response(response), "s_uto")

    if isinstance(response, Failure):
        return response

    return [float(x) for x in response]


def decode_mtp(response: bytes) -> List[float] | Failure:
    response = validate_response(decode_response(response), "s_mtp")

    if isinstance(response, Failure):
        return response

    return [float(x) for x in response]


def decode_general_state(response: bytes) -> Tuple[Dict, List] | Failure:
    response = validate_response(decode_response(response), "s_hexa")

    if isinstance(response, Failure):
        return response

    response = int(response[0])

    LOGGER.debug(f"{response = } <- decode_general_state")

    s_hexa = [int(x) for x in f'{response:015b}'[::-1]]
    state = dict(zip(GENERAL_STATE, s_hexa))

    return state, list(state.values())


def decode_actuator_state(response: bytes) -> Tuple[Tuple[Dict, List]] | Failure:
    response = validate_response(decode_response(response), "s_ax")

    if isinstance(response, Failure):
        return response

    def decode_state(state: int) -> Tuple[Dict, List]:
        state_bits = [int(x) for x in f'{state:015b}'[::-1]]
        state_dict = dict(zip(ACTUATOR_STATE, state_bits))
        return state_dict, state_bits

    actuator_states = [int(x) for x in response]

    return tuple(decode_state(state) for state in actuator_states)


def decode_validation_error(value) -> Dict:
    """
    Decode the bitfield variable that is returned by the VALID_PTP command.

    Each bit in this variable represents a particular error in the validation of a movement.
    Several errors can be combined into the given variable.

    Returns a dictionary with the bit numbers that were (on) and the corresponding error description.
    """

    return {bit: VALIDATION_LIMITS[bit] for bit in range(6) if value >> bit & 0b01}


class AlphaPlusTelnetInterface(DeviceTransport, DeviceConnectionInterface):
    """
    The Hexapod controller device interface based on the telnet protocol. This class implements the
    DeviceTransport protocol which provides the `read()`, `write()`, `trans()`, and `query()` methods.
    """

    TELNET_TIMEOUT = 1.0

    def __init__(self, hostname: str = 'localhost', port: int = 23):
        """
        Args:
            hostname (str): the IP address or fully qualified hostname of the OGSE hardware
                controller. The default is 'localhost'.
            port (int): the IP port number to connect to. The default is 23.
        """
        super().__init__()
        self.telnet = Telnet()
        self._is_connected = False
        self.hostname = hostname
        self.port = port

    def connect(self) -> None:
        """
        Connects to the Alpha+ Controller using the Telnet protocol. After connection
        the telnet session logs in with the username provided in the Settings file. The password for this login is also
        provided in the Settings under the same group. Make sure their values are only given in
        the local settings file, not the global settings.

        After login, the `gpascii` command is started with the option `-2` as instructed
        in the software manual of the controller. The first command sent then is the
        `echo7` command, which configures the system to return variable numbers only,
        not their variable names.
        """
        try:
            self.telnet.open(self.hostname, self.port)
        except ConnectionRefusedError as exc:
            raise DeviceConnectionError(
                device_name="Alpha+ Controller",
                message=f"Connection refused to {self.hostname} port {self.port}"
            ) from exc

        try:
            rc = self.telnet.read_until(b"login: ", timeout=self.TELNET_TIMEOUT)
            # print(rc.decode(), flush=True, end="")
            self.telnet.write(f"{PUNA_PLUS.user_name}\r\n".encode())
            rc = self.telnet.read_until(b"Password: ", timeout=self.TELNET_TIMEOUT)
            # print(rc.decode(), flush=True, end="")
            self.telnet.write(f"{PUNA_PLUS.password}\r\n".encode())
            rc = self.telnet.read_until(b"ppmac# ", timeout=self.TELNET_TIMEOUT)
            # print(rc.decode(), flush=True, end="")
            self.telnet.write(b"gpascii -2\r\n")
            rc = self.telnet.read_until(b'\x06\r\n', timeout=self.TELNET_TIMEOUT)
            # print(rc.decode(), flush=True, end="")
            self.telnet.write(b"echo7\r\n")
            rc = self.telnet.read_until(b'\x06\r\n', timeout=self.TELNET_TIMEOUT)
            # print(rc.decode(), flush=True, end="")
        except EOFError as exc:
            raise DeviceConnectionError(
                device_name="Alpha+ Controller",
                message=f"Telnet connection closed for {self.hostname} port {self.port}"
            ) from exc

        self._is_connected = True

    def is_connected(self):
        return self._is_connected

    def disconnect(self):
        rc = self.telnet.read_very_eager()
        print(rc.decode(), flush=True, end="")
        self.telnet.close()
        self._is_connected = False

    def reconnect(self):

        if self._is_connected:
            self.disconnect()
        self.connect()

    def trans(self, cmd: str) -> bytes:
        """
        Send a command to the Aplha+ Controller and waits for a response.
        The response is returned after the ACK is stripped off (see `read()` method).

        Args:
            cmd: a valid command string for the Alpha+ Controller

        Returns:
            The response from the controller on the command that was sent.
        """
        self.write(cmd)
        response = self.read()

        LOGGER.debug(f"trans: {response = }")

        return response

    def read(self) -> bytes:
        """
        Reads a response from the controller.

        Note: The acknowledgement `\x06\r\n` is stripped from the response before it is
              returned. If no ACK is present, a warning message will be logged.

        Returns:
            The response from the controller on a previously sent command.
        """

        response = self.telnet.read_until(b'\x06\r\n', timeout=self.TELNET_TIMEOUT)

        LOGGER.debug(f"read: {response = }")

        if not response.endswith(b'\x06\r\n'):
            LOGGER.warning(f"Expected ACK at the end of the response, {response = }")
            return response

        return response[:-3]  # strip off the ACK

    def write(self, cmd: str):
        """
        Sends a command string to the Alpha+ Controller.
        The command string shall not end with a CRLF, that is automatically appended
        by this function.

        Args:
            cmd: a valid command string for the Alpha+ Controller

        Returns:
            Nothing is returned.
        """
        LOGGER.debug(f"Executing: {cmd.rstrip()}")
        self.telnet.write(cmd.encode())


class AlphaControllerInterface(DeviceInterface):

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cmd=C_STOP",
        process_cmd_string=process_cmd_string,
        process_response=partial(issue_warning, msg="STOP command has been executed."),
        post_cmd=return_command_status,
    )
    def stop(self) -> Tuple[int, str] | Failure:
        """
        Stop the current motion. This command can be sent during a motion of the Hexapod
        and is executed with high priority.

        Returns:
            A tuple (return code, description). Return code = 0 on success.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cmd=C_CONTROLON",
        process_cmd_string=process_cmd_string,
        post_cmd=return_command_status,
    )
    def activate_control_loop(self):
        """
        Activates the control loop on motors.

        It activates the power on the motors and releases the brakes if present.
        The hexapod status 'Control On' will switch to true when the command is successful.

        This command should be used before starting a movement.

        Note: it is possible to activate the control loop on motors even if the home is not complete.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cmd=C_CONTROLOFF",
        process_cmd_string=process_cmd_string,
        post_cmd=return_command_status,
    )
    def deactivate_control_loop(self):
        """
        Disables the control loop on the servo motors.

        It is advisable to disable the servo motors if the system is not used for
        a long period (more than 1 hour for example). However, this recommendation
        depends on the application for which the system is being used.

        This command is performed only if the following conditions are met:
          * there is no motion task running
          * there is no action running
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cmd=C_HOME",
        process_cmd_string=process_cmd_string,
        process_response=process_response,
    )
    def homing(self):
        """
        Starts the homing task on the hexapod.

        Homing needs to be completed before performing any movement. When the hexapod
        is equipped with absolute encoders, this cycle is executed automatically during
        the controller initialization. When the hexapod is not equipped with absolute
        encoders, the homing request movements: homing cycle will search actuators
        reference sensors.

        Homing is required before performing a control movement. Without absolute encoders,
        the homing is performed with a hexapod movement until detecting the reference sensor
        on each of the actuators. The Hexapod will go to a position were the sensors are
        reached that signal a known calibrated position and then returns to the zero position.

        Whenever a homing is performed, the method will return before the actual movement
        is finished.

        The homing cycle takes about two minutes to complete, but the ``homing()`` method
        returns almost immediately. Therefore, to check if the homing is finished, use
        the is_homing_done() method.

        This command is performed only if the following conditions are met:
          * there is no motion task running
          * the emergency stop button is not engaged (not applicable for absolute encoders)

        """
        raise NotImplementedError

    def is_homing_done(self) -> bool | Failure:
        """
        Checks if Homing is done.

        When this variable indicates 'Homing is done' it means the command has been properly
        executed, but it doesn't mean the Hexapod is in position. The hexapod might still be
        moving to its zero position.

        Returns:
            True when the homing is done, False otherwise.
        """
        general_state = self.get_general_state()
        if isinstance(general_state, Failure):
            return general_state

        return bool(general_state[1][HOME_COMPLETE])

    def is_in_position(self) -> bool | Failure:
        """
        Checks if the hexapod is in position.

        Returns:
            True when in position, False otherwise.
        """
        general_state = self.get_general_state()
        if isinstance(general_state, Failure):
            return general_state

        return bool(general_state[1][IN_POSITION]) and not bool(general_state[1][IN_MOTION])

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cmd=C_CLEARERROR",
        process_cmd_string=process_cmd_string,
        post_cmd=return_command_status,
    )
    def clear_error(self) -> Tuple[int, str] | Failure:
        """
        Clear all errors in the controller software.

        This command clears the error list on the controller and automatically removes the error bit of the hexapod
        state. After this command, errors might automatically be regenerated if they are still present. For example,
        if an encoder is disconnected, the encoder error will be re-generated after the command because error reason
        is not corrected.

        Returns:
            The command status is returned as a tuple with (return code, message).
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cfg=1 "
                                           "c_par(0)=${tx_u} c_par(1)=${ty_u} c_par(2)=${tz_u} "
                                           "c_par(3)=${rx_u} c_par(4)=${ry_u} c_par(5)=${rz_u} "
                                           "c_par(6)=${tx_o} c_par(7)=${ty_o} c_par(8)=${tz_o} "
                                           "c_par(9)=${rx_o} c_par(10)=${ry_o} c_par(11)=${rz_o} "
                                           "c_cmd=C_CFG_CS",
        process_cmd_string=process_cmd_string,
        post_cmd=return_command_status,
    )
    def configure_coordinates_systems(
            self, tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o
    ) -> Tuple[int, str] | Failure:
        """
        Change the definition of the User Coordinate System and the Object Coordinate System.

        The parameters tx_u, ty_u, tz_u, rx_u, ry_u, rz_u are used to define the user coordinate
        system relative to the Machine Coordinate System and the parameters tx_o, ty_o, tz_o, rx_o,
        ry_o, rz_o are used to define the Object Coordinate System relative to the Platform
        Coordinate System.

        Args:
            tx_u (float): translation parameter that define the user coordinate system relative
                          to the machine coordinate system [in mm]
            ty_u (float): translation parameter that define the user coordinate system relative
                          to the machine coordinate system [in mm]
            tz_u (float): translation parameter that define the user coordinate system relative
                          to the machine coordinate system [in mm]

            rx_u (float): rotation parameter that define the user coordinate system relative to
                          the machine coordinate system [in deg]
            ry_u (float): rotation parameter that define the user coordinate system relative to
                          the machine coordinate system [in deg]
            rz_u (float): rotation parameter that define the user coordinate system relative to
                          the machine coordinate system [in deg]

            tx_o (float): translation parameter that define the object coordinate system relative
                          to the platform coordinate system [in mm]
            ty_o (float): translation parameter that define the object coordinate system relative
                          to the platform coordinate system [in mm]
            tz_o (float): translation parameter that define the object coordinate system relative
                          to the platform coordinate system [in mm]

            rx_o (float): rotation parameter that define the object coordinate system relative to
                          the platform coordinate system [in deg]
            ry_o (float): rotation parameter that define the object coordinate system relative to
                          the platform coordinate system [in deg]
            rz_o (float): rotation parameter that define the object coordinate system relative to
                          the platform coordinate system [in deg]

        Returns:
            A tuple with the command status return code and a description.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="c_cfg=0 c_cmd=C_CFG_CS",
        process_cmd_string=process_cmd_string,
        process_response=partial(decode_pars, count=12),
        post_cmd=partial(get_pars, count=12),
    )
    def get_coordinates_systems(self):
        """
        Retrieve the definition of the User Coordinate System and the Object Coordinate System.

        Returns:
            tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o where the
            translation parameters are in [mm] and the rotation parameters are in [deg].
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_par(0)=${cm} "
                                           "c_par(1)=${tx} c_par(2)=${ty} c_par(3)=${tz} "
                                           "c_par(4)=${rx} c_par(5)=${ry} c_par(6)=${rz} "
                                           "c_cmd=C_MOVE_PTP",
        process_cmd_string=process_cmd_string,
        post_cmd=return_command_status,
    )
    def move_ptp(self, cm: int,
                 tx: float, ty: float, tz: float, rx: float, ry: float, rz: float) -> Tuple[int, str] | Failure:
        """
        Start the movement as defined by the arguments.

        Args:
            cm: control mode, 0=absolute, 1=object relative, 2=user relative
            tx: position on X-axis [mm]
            ty: position on Y-axis [mm]
            tz: position on Z-axis [mm]
            rx: rotation around the X-axis [deg]
            ry: rotation around the Y-axis [deg]
            rz: rotation around the Z-axis [deg]

        Returns:

        """
        raise NotImplementedError

    def move_absolute(self, tx, ty, tz, rx, ry, rz) -> Tuple[int, str] | Failure:
        return self.move_ptp(0, tx, ty, tz, rx, ry, rz)

    def move_relative_object(self, tx, ty, tz, rx, ry, rz) -> Tuple[int, str] | Failure:
        return self.move_ptp(1, tx, ty, tz, rx, ry, rz)

    def move_relative_user(self, tx, ty, tz, rx, ry, rz) -> Tuple[int, str] | Failure:
        return self.move_ptp(2, tx, ty, tz, rx, ry, rz)

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_par(0)=${pos} c_cmd=C_MOVE_SPECIFICPOS",
        process_cmd_string=process_cmd_string,
        # process_response=process_response,
        post_cmd=return_command_status,
    )
    def goto_specific_position(self, pos: int):
        raise NotImplementedError

    def goto_user_zero_position(self):
        return self.goto_specific_position(pos=1)

    def goto_retracted_position(self):
        return self.goto_specific_position(pos=2)

    def goto_machine_zero_position(self):
        return self.goto_specific_position(pos=3)

    goto_zero_position = goto_user_zero_position

    @dynamic_command(
        cmd_type="transaction", cmd_string="s_uto_tx,6,1",
        process_cmd_string=process_cmd_string,
        process_response=decode_uto,
    )
    def get_user_positions(self):
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="s_mtp_tx,6,1",
        process_cmd_string=process_cmd_string,
        process_response=decode_mtp,
    )
    def get_machine_positions(self) -> List[float] | Failure:
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="c_cmd=C_VERSION",
        process_cmd_string=process_cmd_string,
        process_response=decode_info,
        post_cmd=partial(get_pars, count=12),
    )
    def info(self) -> str:
        """Returns basic information about the hexapod and the controller.

        Returns:
            a multiline response message containing the device info.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="c_cmd=C_VERSION",
        process_cmd_string=process_cmd_string,
        process_response=decode_version,
        post_cmd=partial(get_pars, count=12),
    )
    def version(self) -> str:
        """Returns the version of the firmware running on the hexapod aplha+ controller.

        Returns:
            A version number as a string.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="s_hexa",
        process_cmd_string=process_cmd_string,
        process_response=decode_general_state
    )
    def get_general_state(self) -> Tuple[Dict, List] | Failure:
        """
        Asks the general state of the hexapod on all the motors following the bits definition
        presented below.

        GENERAL_STATE =
            0: "Error",
            1: "System initialized",
            2: "Control on",
            3: "In position",
            4: "Motion task running",
            5: "Home task running",
            6: "Home complete",
            7: "Home virtual",
            8: "Phase found",
            9: "Brake on",
            10:"Motion restricted",
            11:"Power on encoders",
            12:"Power on limit switches",
            13:"Power on drives",
            14:"Emergency stop"

        Returns:
            A dictionary with the bits value of each parameter.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="s_ax_1,6,1",
        process_cmd_string=process_cmd_string,
        process_response=decode_actuator_state,
    )
    def get_actuator_state(self) -> Tuple[Dict, List] | Failure:
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="s_pos_ax_1,6,1",
        process_cmd_string=process_cmd_string,
        process_response=partial(decode_pars, count=6, func=float),
    )
    def get_actuator_length(self):
        """
        Retrieve the current length of the hexapod actuators.

        Returns:
            array: an array of six float values for actuator length L1 to L6 in [mm], and \
            None: when an Exception was raised and logs the error message.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="c_cfg=0 c_cmd=C_CFG_SPEED",
        process_cmd_string=process_cmd_string,
        process_response=partial(decode_pars, count=6),
        post_cmd=partial(get_pars, count=6),
    )
    def get_speed(self) -> List[float]:
        """
        Returns the positional speed of movements.

        Returns a list of floating point numbers [vt, vr, vt-, vr-, vt+, vr+] where vt and vr are the translation and
        angular speed respectively, the '-' and '+' are the minimum and maximum speeds.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cfg=1 c_par(0)=${vt} c_par(1)=${vr} c_cmd=C_CFG_SPEED",
        process_cmd_string=process_cmd_string,
        post_cmd=return_command_status,
    )
    def set_speed(self, vt: float, vr: float):
        """
        Set the positioning speed of movements.

        Args:
            vt: translational speed, unit = mm per second
            vr: angular speed, unit = deg per second
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_par(0)=${vm} c_par(1)=${cm} "
                                           "c_par(2)=${tx} c_par(3)=${ty} c_par(4)=${tz} "
                                           "c_par(5)=${rx} c_par(6)=${ry} c_par(7)=${rz} "
                                           "c_cmd=C_VALID_PTP",
        process_cmd_string=process_cmd_string,
        process_response=process_validate_ptp,
        post_cmd=get_pars,
    )
    def validate_position(self, vm, cm, tx, ty, tz, rx, ry, rz) -> Tuple[int, Dict[int, str]] | Failure:
        """
        Ask the controller if the movement defined by the arguments is feasible.

        Returns a tuple where the first element is an integer that represents the
        bitfield encoding the errors. The second element is a dictionary with the
        bit numbers that were (on) and the corresponding error description as
        defined by VALIDATION_LIMITS.

        Args:
            vm (int): validation mode [only vm=1 is currently implemented by Symétrie]
            cm (int): control mode (0 = absolute, 1 = object relative, 2 = user relative)
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        """
        raise NotImplementedError

    def check_absolute_movement(self, tx, ty, tz, rx, ry, rz) -> Tuple[int, Dict[int, str]] | Failure:
        """
        Check if the requested object movement is valid.

        The absolute movement is expressed in the user coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            tuple: where the first element is an integer that represents the
                bitfield encoding the errors. The second element is a dictionary
                with the bit numbers that were (on) and the corresponding error
                description.
        """
        # Currently only the vm=1 mode is developed by Symétrie
        # Parameter cm = 0 for absolute
        return self.validate_position(1, 0, tx, ty, tz, rx, ry, rz)

    def check_relative_object_movement(self, tx, ty, tz, rx, ry, rz) -> Tuple[int, Dict[int, str]] | Failure:
        """
        Check if the requested object movement is valid.

        The relative motion is expressed in the object coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            tuple: where the first element is an integer that represents the
                bitfield encoding the errors. The second element is a dictionary
                with the bit numbers that were (on) and the corresponding error
                description.
        """
        # Currently only the vm=1 mode is developed by Symétrie
        # Parameter cm = 1 for object relative
        return self.validate_position(1, 1, tx, ty, tz, rx, ry, rz)

    def check_relative_user_movement(self, tx, ty, tz, rx, ry, rz) -> Tuple[int, Dict[int, str]] | Failure:
        """
        Check if the requested object movement is valid.

        The relative motion is expressed in the user coordinate system.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        Returns:
            tuple: where the first element is an integer that represents the
                bitfield encoding the errors. The second element is a dictionary
                with the bit numbers that were (on) and the corresponding error
                description.
        """
        # Currently only the vm=1 mode is developed by Symétrie
        # Parameter cm = 2 for user relative
        return self.validate_position(1, 2, tx, ty, tz, rx, ry, rz)


class AlphaPlusControllerInterface(AlphaControllerInterface):
    @dynamic_command(
        cmd_type="query", cmd_string="${name}",
        process_cmd_string=process_cmd_string,
        process_response=process_response,
    )
    def query_variable(self, name: str) -> str:
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="${name},${count},${increment}",
        process_cmd_string=process_cmd_string,
        process_response=process_response,
    )
    def query_variables(self, name: str, count: int, increment: int = 1):
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="${name}(${idx})",
        process_cmd_string=process_cmd_string,
        process_response=process_response,
    )
    def query_array(self, name: str, idx: int):
        raise NotImplementedError

    @dynamic_command(
        cmd_type="query", cmd_string="${name}(${idx}),${count},${increment}",
        process_cmd_string=process_cmd_string,
        process_response=process_response,
    )
    def query_array_values(self, name: str, idx: int, count: int, increment: int = 1):
        raise NotImplementedError

    @dynamic_command(
        cmd_type="transaction", cmd_string="c_cfg=0 c_par(0)=${lim} c_cmd=C_CFG_LIMIT",
        process_cmd_string=process_cmd_string,
        process_response=partial(decode_pars, index=1, count=12),
        post_cmd=partial(get_pars, count=13),
    )
    def get_limits_value(self, lim):
        """
        Three different and independent operational workspace limits are defined on the controller:

            * Factory limits: are expressed in machine coordinate system limits. Those parameters cannot be modified.
            * Machine coordinate system limits: they are expressed in the Machine coordinate system. It can be used to
              secure the hexapod (and/or object) from its environment.
            * User coordinate system limits: they are expressed in the User coordinate system. It can be used to limits
              the movements of the object mounted on hexapod.

        Remark: operational workspace limits must be understood as limits in terms of amplitude of movement. Those
        limits are defined for each operational axis with a negative and positive value and are used in the validation
        process. Position on each operational axis must be within those two values.

        Args:
            lim (int): 0 = factory (GET only), 1 = machine cs limit, 2 = user cs limit

        Returns:
            A list of 12 float values: tx-, ty-, tz-, rx-, ry-, rz-, tx+, ty+, tz+, rx+, ry+, rz+
            The first six values are the negative limits for translation and rotation, the last six numbers are the
            positive limits for translation and rotation.

        """
        raise NotImplementedError


if __name__ == "__main__":

    from rich import print as rp

    from egse.hexapod.symetrie.punaplus import PunaPlusController

    # Thie IP address for the emulator running in VirtualBox is 192.168.56.10
    # When you run the emulator in Parallels, the IP address is 10.37.129.10

    puna = PunaPlusController(hostname="10.37.129.10", port=23)
    puna.connect()

    with Timer("PunaPlusController"):
        rp(puna.info())
        rp(puna.version())
        rp(puna.is_homing_done())
        rp(puna.homing())
        if wait_until(puna.is_homing_done, interval=1, timeout=300):
            rp("[red]Task puna.is_homing_done() timed out after 30s.[/red]")
        rp(puna.is_homing_done())
        rp(puna.is_in_position())
        rp(puna.activate_control_loop())
        rp(puna.get_general_state())
        rp(puna.get_actuator_state())
        rp(puna.deactivate_control_loop())
        rp(puna.get_general_state())
        rp(puna.get_actuator_state())
        rp(puna.stop())
        rp(puna.get_limits_value(0))
        rp(puna.get_limits_value(1))
        rp(puna.check_absolute_movement(1, 1, 1, 1, 1, 1))
        rp(puna.check_absolute_movement(51, 51, 51, 1, 1, 1))
        rp(puna.get_speed())
        rp(puna.set_speed(2.0, 1.0))
        rp(speed := puna.get_speed())

        if speed[:2] != [2.0, 1.0]:
            rp(f"[red]Expected {speed[:2]} == [2.0, 1.0][/red")

        input("Check speed parameters in GUI")

        rp(puna.set_speed(1.2, 1.1))

        rp(speed := puna.get_speed())

        if speed[:2] != [1.2, 1.1]:
            rp(f"[red]Expected {speed[:2]} == [1.2, 1.1][/red")

        rp(puna.get_actuator_length())

        # rp(puna.machine_limit_enable(0))
        # rp(puna.machine_limit_enable(1))
        # rp(puna.get_limits_state())
        rp(puna.get_coordinates_systems())
        rp(puna.configure_coordinates_systems(
                0.033000, -0.238000, 230.205000, 0.003282, 0.005671, 0.013930,
                0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000))
        rp(puna.get_coordinates_systems())
        rp(puna.get_machine_positions())
        rp(puna.get_user_positions())

        input("Check configuration in GUI")

        rp(puna.configure_coordinates_systems(
                0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
                0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000))

        rp(puna.validate_position(1, 0, 0, 0, 0, 0, 0, 0))
        rp(puna.validate_position(1, 0, 0, 0, 50, 0, 0, 0))

        rp(puna.goto_zero_position())
        rp(puna.is_in_position())
        if wait_until(puna.is_in_position, interval=1, timeout=300):
            rp("[red]Task puna.is_in_position() timed out after 30s.[/red]")
        rp(puna.is_in_position())

        rp(puna.get_machine_positions())
        rp(puna.get_user_positions())

        rp(puna.move_absolute(0, 0, 12, 0, 0, 10))

        rp(puna.is_in_position())
        if wait_until(puna.is_in_position, interval=1, timeout=300):
            rp("[red]Task puna.is_in_position() timed out after 30s.[/red]")
        rp(puna.is_in_position())

        rp(puna.get_machine_positions())
        rp(puna.get_user_positions())

        rp(puna.move_absolute(0, 0, 0, 0, 0, 0))

        rp(puna.is_in_position())
        if wait_until(puna.is_in_position, interval=1, timeout=300):
            rp("[red]Task puna.is_in_position() timed out after 30s.[/red]")
        rp(puna.is_in_position())

        rp(puna.get_machine_positions())
        rp(puna.get_user_positions())

        # # puna.reset()
        puna.disconnect()

        # rp(0, decode_validation_error(0))
        # rp(11, decode_validation_error(11))
        # rp(8, decode_validation_error(8))
        # rp(24, decode_validation_error(24))
