"""
PMAC Interface to Hexapod Hardware Controller from Symétrie.

Some of the code below is based on the dls_pmaclib Python library that was made available
as open source by Diamond Control under the LGPL v3.x. For more info and the original
source code, please go to http://controls.diamond.ac.uk/downloads/python/index.php].

Author: Rik Huygen
"""

import logging
import socket
import struct
import threading
from datetime import datetime
from datetime import timedelta
from typing import List

from egse.hexapod.symetrie.pmac_regex import match_float_response
from egse.hexapod.symetrie.pmac_regex import match_int_response
from egse.hexapod.symetrie.pmac_regex import match_string_response

logger = logging.getLogger(__name__)

# Command set Request

VR_PMAC_SENDLINE = 0xB0
VR_PMAC_GETLINE = 0xB1
VR_PMAC_FLUSH = 0xB3
VR_PMAC_GETMEM = 0xB4
VR_PMAC_SETMEM = 0xB5
VR_PMAC_SETBIT = 0xBA
VR_PMAC_SETBITS = 0xBB
VR_PMAC_PORT = 0xBE
VR_PMAC_GETRESPONSE = 0xBF
VR_PMAC_READREADY = 0xC2
VR_CTRL_RESPONSE = 0xC4
VR_PMAC_GETBUFFER = 0xC5
VR_PMAC_WRITEBUFFER = 0xC6
VR_PMAC_WRITEERROR = 0xC7
VR_FWDOWNLOAD = 0xCB
VR_IPADDRESS = 0xE0

# Request Types

VR_DOWNLOAD = 0x40  # Command send to the device
VR_UPLOAD = 0xC0  # Command send to host

# API Function Error Codes

ERR_DISCONNECTED = -1
ERR_NOT_READY_2_BE_READ = -2
ERR_NO_CMD_MATCHING = -3
ERR_WRITE = -4
ERR_READ = -5
ERR_CONNECTION = -6
ERR_CMD_TIMEOUT = -7

# API Returns

RETURN_SUCCESS = 0
RETURN_IGNORED = -1
RETURN_FAILURE = -2

# The States of Q20 which are checked after the command has executed.

Q20_0: List[int] = []  # no checking of Q20 to be done
Q20_1: List[int] = [RETURN_SUCCESS]  # wait until success
Q20_2: List[int] = [RETURN_SUCCESS, RETURN_IGNORED]
Q20_3: List[int] = [RETURN_SUCCESS, RETURN_IGNORED, RETURN_FAILURE]

# Each command is defined as a dictionary with the following structure:
#
# {
#     'name'    : [string]   Human readable name of the command
#     'cmd'     : [string]   Actual command string for the controller.
#                            Can contain format replacement fields for commands that take input values.
#     'in'      : [int]      Number of input values. This should match up with the number of replacement fields in 'cmd'
#     'out'     : [type]     Number of output variable. The type of the output variables is defined by 'out_type'
#     'return'  : [string]   The command to retreive and check the output.
#     'check'   : [iterable] Iterable containing the output values that are expected.
#     'out_type': [function] A function object that is used to convert the output variables from string to <type func>.
# }
#
#

CMD_STOP = {
    "name": "STOP",
    "cmd": "&2 Q20=2",
    "in": 0,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_1,
    "out_type": None,
}
CMD_HOMING = {
    "name": "HOMING",
    "cmd": "&2 Q20=1",
    "in": 0,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_1,
    "out_type": None,
}
CMD_VIRTUAL_HOMING = {
    "name": "HOMINGVIRTUAL",
    "cmd": "&2 Q71={tx} Q72={ty} Q73={tz} Q74={rx} Q75={ry} Q76={rz} Q20=42",
    "in": 6,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_2,
    "out_type": None,
}
CMD_CONTROLON = {
    "name": "CONTROL_ON",
    "cmd": "&2 Q20=3",
    "in": 0,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_3,
    "out_type": None,
}
CMD_CONTROLOFF = {
    "name": "CONTROL_OFF",
    "cmd": "&2 Q20=4",
    "in": 0,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_1,
    "out_type": None,
}
CMD_MOVE = {
    "name": "MOVE",
    "cmd": "&2 Q70={cm} Q71={tx:.6f} Q72={ty:.6f} Q73={tz:.6f} Q74={rx:.6f} Q75={ry:.6f} Q76={rz:.6f} Q20=11",
    "in": 7,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_3,
    "out_type": None,
}
CMD_MAINTENANCE = {
    "name": "MAINTENANCE",
    "cmd": "&2 Q80={axis} Q20=12",
    "in": 1,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_2,
    "out_type": None,
}
CMD_SPECIFICPOS = {
    "name": "SPECIFICPOS",
    "cmd": "&2 Q80={pos} Q20=13",
    "in": 1,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_3,
    "out_type": None,
}
CMD_CLEARERROR = {
    "name": "CLEARERROR",
    "cmd": "&2 Q20=15",
    "in": 0,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_1,
    "out_type": None,
}
CMD_RESETSOFT = {
    "name": "RESETSOFT",
    "cmd": "$$$",
    "in": 0,
    "out": 0,
    "return": None,
    "check": None,
    "out_type": None,
}
CMD_JOG = {
    "name": "JOG",
    "cmd": "&2 Q68={axis} Q69={inc} Q20=41",
    "in": 0,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_2,
    "out_type": None,
}

CMD_CFG_CS = {
    "name": "CFG#CS",
    "cmd": (
        "&2 Q80={tx_u} Q81={ty_u} Q82={tz_u} Q83={rx_u} Q84={ry_u} Q85={rz_u}"
        " Q86={tx_o} Q87={ty_o} Q88={tz_o} Q89={rx_o} Q90={ry_o} Q91={rz_o} Q20=21"
    ),
    "in": 12,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_2,
    "out_type": None,
}
CMD_CFG_SPEED = {
    "name": "CFG#SPEED",
    "cmd": "&2 Q80={vt} Q81={vr} Q20=25",
    "in": 2,
    "out": 0,
    "return": "&2 Q20",
    "check": Q20_2,
    "out_type": None,
}

CMD_Q20_GET = {
    "name": "Q20?",
    "cmd": "&2 Q20",
    "in": 0,
    "out": 0,
    "return": None,
    "check": None,
    "out_type": None,
}
CMD_Q29_GET = {
    "name": "Q29?",
    "cmd": "&2 Q29",
    "in": 0,
    "out": 0,
    "return": None,
    "check": None,
    "out_type": None,
}
CMD_STATE_HEXA_GET = {
    "name": "STATE#HEXA?",
    "cmd": "&2 Q36",
    "in": 0,
    "out": 0,
    "return": None,
    "check": None,
    "out_type": None,
}
CMD_STATE_ERROR_GET = {
    "name": "STATE#ERROR?",
    "cmd": "&2 Q38",
    "in": 0,
    "out": 0,
    "return": None,
    "check": None,
    "out_type": None,
}
CMD_STATE_DEBUG_GET = {
    "name": "STATE#DEBUG?",
    "cmd": "&2 Q26,3,1 Q20",
    "in": 0,
    "out": 4,
    "return": None,
    "check": None,
    "out_type": int,
}
CMD_VERSION_GET = {
    "name": "VERSION?",
    "cmd": "&2 Q20=55",
    "in": 0,
    "out": 4,
    "return": "&2 Q20 Q80,4,1",
    "check": Q20_1,
    "out_type": bytes.decode,
}
CMD_POSUSER_GET = {
    "name": "POSUSER?",
    "cmd": "&2 Q53,6,1",
    "in": 0,
    "out": 6,
    "return": None,
    "check": None,
    "out_type": float,
}
CMD_POSVALID_GET = {
    "name": "POSVALID?",
    "cmd": "&2 Q70={cm} Q71={tx:.6f} Q72={ty:.6f} Q73={tz:.6f} Q74={rx:.6f} Q75={ry:.6f} Q76={rz:.6f} Q20=10",
    "in": 7,
    "out": 1,
    "return": "&2 Q20 Q29",
    "check": Q20_1,
    "out_type": int,
}
CMD_CFG_CS_GET = {
    "name": "CFG#CS?",
    "cmd": "&2 Q20=31",
    "in": 0,
    "out": 12,
    "return": "&2 Q20 Q80,12,1",
    "check": Q20_1,
    "out_type": float,
}
CMD_CFG_SPEED_GET = {
    "name": "CFG#SPEED?",
    "cmd": "&2 Q20=35",
    "in": 0,
    "out": 6,
    "return": "&2 Q20 Q80,6,1",
    "check": Q20_1,
    "out_type": float,
}

CMD_STRING_CID = "CID"  # Card ID number
CMD_STRING_VER = "VERSION"  # Firmware Version (Revision Level)
CMD_STRING_CPU = "CPU"
CMD_STRING_TYPE = "TYPE"
CMD_STRING_VID = "VID"  # Vendor ID
CMD_STRING_DATE = "DATE"
CMD_STRING_TIME = "TIME"
CMD_STRING_TODAY = "TODAY"

DEF_TPMAC_CMD_TIMEOUT = timedelta(seconds=5)
DEF_TPMAC_READ_TIMEOUT = timedelta(seconds=2)
DEF_TPMAC_READ_FREQ = timedelta(milliseconds=100)
DEF_TPMAC_STRING_SIZE = 1400

DEF_STRING_SIZE = 256


# #### Pure Python API interface #######################################################################################


class PMACError(Exception):
    pass


# #### Helper functions and classes ####################################################################################


def extractOutput(sourceStr, nr, func=bytes.decode):
    """
    Extract values from the source string argument.

    The output variables all have the same type and are converted using
    the func argument, e.g. int or float.

    :return: an array with the output variables.
    """
    # Remove the acknowledgement from the sourceStr

    sourceStr = sourceStr.rstrip(b"\r\x06")

    # Split the string in it's parts separated by \r

    parts = sourceStr.split(b"\r")

    # extract the values from the part and put them in out

    try:
        out = [func(part) for part in parts]
    except (ValueError, TypeError) as exc:
        raise PMACError(
            f'extractOutput(): Could not parse individual parts of "{sourceStr}" with {func}.'
        ) from exc

    return out


def extractQ20AndOutput(sourceStr, nr, func=bytes.decode):
    """
    Extract values from the source string argument.

    The first value is always the Q20 variable and is of integer type.

    The other output variables all have the same type and are converted using
    the func argument, e.g. int or float.

    Returns a tuple containing the Q20 and an array with the output variables.
    """
    # Remove the acknowledgement from the sourceStr

    sourceStr = sourceStr.rstrip(b"\r\x06")

    # Split the string in it's parts separated by \r

    parts = sourceStr.split(b"\r")

    # First value is always Q20, then the other output values

    try:
        Q20 = int(parts[0])
        out = [func(part) for part in parts[1:]]
    except (ValueError, TypeError) as ex:
        raise PMACError(
            f'extractQ20AndOutput(): Could not parse individual parts of "{sourceStr}" with {func}.'
        ) from ex

    return (Q20, out)


def decode_Q29(value):
    """
    Decode the bitfield variable Q29.

    Each bit in this variable represents a particular error in the validation of a movement.
    Several errors can be combined into the Q29 variable.

    Returns a dictionary with the bit numbers that were (on) and the corresponding error description.
    """

    # This description is taken from the API PUNA Hexapod Controller Manual, version A, section 4.5.4 POSVALID?

    description = [
        "Homing is not done",
        "Coordinate systems definition not realized",
        "Kinematic error",
        "Out of SYMETRIE (factory) workspace",
        "Out of machine workspace",
        "Out of user workspace",
        "Actuator out of limits",
        "Joints out of limits",
        "Out of limits due to backlash compensation",
        '"Abort" input enabled',
        '"Safety Sensor" inputs enabled',
    ]

    error_msgs = {}

    for bit in range(24):
        if value >> bit & 0x01:
            error_msgs[bit] = description[bit] if bit < 11 else "Reserved"

    return error_msgs


def decode_Q30(value):
    """
    Decode the bitfield variable Q30.

    Each bit in this variable represents a particular system setting of the actuator.

    Returns a dictionary with the bit numbers that were (on) and the corresponding error description.
    """

    # This description is taken from the API PUNA Hexapod Controller Manual, version A, section 4.5.5 STATE#ACTUATOR?

    description = [
        "In position",
        "Control loop on servo motors active",
        "Homing done",
        'Input "Home switch"',
        'Input "Positive limit switch"',
        'Input "Negative limit switch"',
        "Brake control output",
        "Following error (warning)",
        "Following error",
        "Actuator out of bounds error",
        "Amplifier error",
        "Encoder error",
        "Phasing error (brushless engine only)",
    ]

    error_msgs = {
        bit: description[bit] if bit < 13 else "Reserved"
        for bit in range(24)
        if value >> bit & 0x01
    }

    states = [int(x) for x in f"{value:024b}"[::-1]]

    return error_msgs, states


def decode_Q36(value):
    """
    Decode the bitfield variable Q36.

    Each bit in this variable represents the status of a particular system setting of the hexapod.

    Returns an array with the value (True/False) of the individual bits.
    """

    # This description is taken from the API PUNA Hexapod Controller Manual, version A, section 4.5.6 STATE#HEXA?

    description = [  # noqa: F841
        "Error (OR)",
        "System Initialized",
        "In position",
        "Control loop on servo motors active",
        "Homing done",
        "Brake control output",
        "Emergency stop button engaged",
        "Following error (warning)",
        "Following error",
        "Actuator out of bounds error",
        "Amplifier Error",
        "Encoder error",
        "Phasing error (brushless motors only)",
        "Homing error",
        "Kinematic error",
        '"Abort" input error',
        "R/W flash memory error",
        "Temperature error on one or several motors",
        "Home done (virtual)",
        "Encoders power off",
        "Limit switches power off",
        "Reserved",
        "Reserved",
        "Reserved",
    ]

    bit_values = [False for x in range(24)]

    for bit in range(24):
        bit_values[bit] = True if value >> bit & 0x01 else False

    return bit_values


class EthernetCommand:
    def __init__(self, requestType, request, value, index):
        self.requestType = requestType  # type is byte
        self.request = request  # type is byte
        self.value = value  # type is word (= 2 bytes), content request specific
        self.index = index  # type is word
        self.length = None  # type is word, length of the data part
        self.data = []  # type is byte, max length = 1492 bytes

    def getCommandPacket(self, command=None):
        """
        Pack and return the header and the command in a bytes packet.
        """
        if command is None:
            command = ""

        assert type(command) == str

        headerStr = struct.pack(
            ">BBHHH", self.requestType, self.request, self.value, self.index, len(command)
        )
        wrappedCommand = headerStr + command.encode()

        logger.flash_flood(f"Command Packet generated: {wrappedCommand}")

        return wrappedCommand


class PmacEthernetInterface(object):
    """
    This class provides an interface to connect to a remote PMAC over an Ethernet interface.
    It provides methods to connect to the PMAC, to disconnect, and to issue commands.
    """

    def __init__(self, numAxes=None):
        """
        Initialize the PMAC Ethernet interface.
        """
        self.modelName = None  # Will be initialized by the getPmacModel() call

        # Basic connection settings

        self.hostname = ""
        self.port = None

        # Access-to-the-connection semaphore.
        # Use this to lock/unlock I/O access to the connection (whatever type it is) in child classes.

        self.semaphore = threading.Semaphore()

        self.isConnectionOpen = False

        # Use the getter self.getNumberOfAxes() to access this. The value is None if uninitialised.

        if numAxes is not None:
            self._numAxes = int(numAxes)
        else:
            self._numAxes = None

        # Define a number of often used commands

        self.getResponseCommand = EthernetCommand(VR_DOWNLOAD, VR_PMAC_GETRESPONSE, 0, 0)
        self.getBufferCommand = EthernetCommand(VR_UPLOAD, VR_PMAC_GETBUFFER, 0, 0)

    def setConnectionParameters(self, host="localhost", port=None):
        self.hostname = str(host)
        if port is not None:
            self.port = int(str(port))

    # Attempts to open a connection to a remote PMAC.
    # Returns None on success, or an error message string on failure.

    def connect(self):

        # Sanity checks

        if self.isConnectionOpen:
            raise PMACError("Socket is already open")
        if self.hostname in (None, ""):
            raise PMACError("ERROR: hostname not initialized")
        if self.port in (None, 0):
            raise PMACError("ERROR: port number not initialized")

        # Create a new socket instance

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setblocking(1)
            self.sock.settimeout(3)
        except socket.error as e_socket:
            raise PMACError("ERROR: Failed to create socket.") from e_socket

        # Attempt to establish a connection to the remote host

        try:
            logger.debug(f'Connecting a socket to host "{self.hostname}" using port {self.port}')
            self.sock.connect((self.hostname, self.port))
        except ConnectionRefusedError as e_cr:
            raise PMACError(f"ERROR: Connection refused to {self.hostname}") from e_cr
        except socket.gaierror as e_gai:
            raise PMACError(f"ERROR: socket address info error for {self.hostname}") from e_gai
        except socket.herror as e_h:
            raise PMACError(f"ERROR: socket host address error for {self.hostname}") from e_h
        except socket.timeout as e_timeout:
            raise PMACError(f"ERROR: socket timeout error for {self.hostname}") from e_timeout
        except OSError as ose:
            raise PMACError(f"ERROR: OSError caught ({ose}).") from ose

        self.isConnectionOpen = True

        # Check that we are connected to a pmac by issuing the "VERSION" command -- expecting the 1.947 in return.
        # If we don't get the right response, then disconnect automatically

        if not self.isConnected():
            raise PMACError("Device is not connected, check logging messages for the cause.")

    def disconnect(self):
        """
        Disconnect from the Ethernet connection.

        Raises a PMACError on failure.
        """
        try:
            if self.isConnectionOpen:
                logger.debug(f"Disconnecting from {self.hostname}")
                self.semaphore.acquire()
                self.sock.close()
                self.semaphore.release()
                self.isConnectionOpen = False
        except Exception as e_exc:
            raise PMACError(f"Could not close socket to {self.hostname}") from e_exc

    def isConnected(self):
        """
        Check if the PMAC Ethernet connection is open. This will send a 'version' command to the
        PMAC interface and try to parse the return value. If no connection was established or
        no version could be parsed from the return value, False is returned.
        """
        if not self.isConnectionOpen:
            return False

        try:
            response = self.getResponse(CMD_STRING_VER)
        except PMACError as e_pmac:
            if len(e_pmac.args) >= 2 and e_pmac.args[1] == ERR_CONNECTION:
                logger.error(
                    f"While trying to talk to the device the following exception occurred, exception={e_pmac}"
                )
                logger.error("Most probably the client connection was closed. Disconnecting...")
                self.disconnect()
                return False
            else:
                logger.error(
                    f"While trying to talk to the device the following exception occured, exception={e_pmac}"
                )
                self.disconnect()
                return False
        finally:
            pass

        version = match_float_response(response)

        if not version:
            # if the response was not matching the regex then we're not talking to a PMAC!
            logger.error(
                f'Device did not respond correctly to a "VERSION" command, response={response}. Disconnecting...'
            )
            self.disconnect()
            return False

        return True

    def getBuffer(self, shouldWait=True):
        """"""

        if not self.isConnectionOpen:
            raise PMACError("Device is not connected, reconnect or check logging messages.")

        try:
            if shouldWait:
                self.semaphore.acquire()

            # Attempt to send the complete command to PMAC

            self.sock.sendall(self.getBufferCommand.getCommandPacket())
            logger.debug("Sent out get buffer request to PMAC")

            # wait for, read and return the response from PMAC (will be at most 1400 chars)

            returnStr = self.sock.recv(2048)
            logger.debug(f"Received from PMAC: {returnStr}")

            return returnStr

        except socket.timeout as e_timeout:
            raise PMACError("Socket timeout error", ERR_CMD_TIMEOUT) from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as an I/O error
            raise PMACError("Socket communication error.", ERR_CONNECTION) from e_socket
        except OSError as e_os:
            raise PMACError(f"OS Error: {e_os}") from e_os
        finally:
            if shouldWait:
                self.semaphore.release()

    def getResponse(self, command, shouldWait=True):
        """
        Send a single command to the controller and block until a response from the controller.

        Args:
            command (str): is the command to be sent

            shouldWait (bool, optional, default True): whether to wait on the semaphore.

                This should normally be left default. If we have acquired the semaphore manually,
                then specify shouldWait = False (and don't forget to release the semaphore eventually).

        Returns:
            response (str): is either a string returned by the PMAC (on success), or an error message (on failure)

        Raises:
            PMACError when there was an I/O problem during comm with the PMAC or the response does not have
            recognised terminators.

            Note that PMAC may still return an "ERRxxx" code; this function will still consider that
            a successful transmission.

        """

        if not self.isConnectionOpen:
            raise PMACError("Device is not connected, reconnect or check logging messages.")

        command = str(command)

        try:
            if shouldWait:
                self.semaphore.acquire()

            # Attempt to send the complete command to PMAC

            logger.flash_flood(f"Sending out to PMAC: {command}")
            self.sock.sendall(self.getResponseCommand.getCommandPacket(command))

            # wait for, read and return the response from PMAC (will be at most 1400 chars)

            returnStr = self.sock.recv(2048)
            logger.flash_flood( f"Received from PMAC: {returnStr}")

            return returnStr

        except OSError as e_os:
            raise PMACError(f"OS Error: {e_os}") from e_os
        except socket.timeout as e_timeout:
            raise PMACError("Socket timeout error", ERR_CMD_TIMEOUT) from e_timeout
        except socket.error as e_socket:
            # Interpret any socket-related error as an I/O error
            raise PMACError("Socket communication error.", ERR_CONNECTION) from e_socket
        finally:
            if shouldWait:
                self.semaphore.release()

    def waitFor(self, cmd, values):
        start = datetime.now()
        count = 0

        assert isinstance(values, list), "Expected list argument"

        while datetime.now() - start < DEF_TPMAC_CMD_TIMEOUT:

            # Only read every DEF_TPMAC_READ_FREQ

            if datetime.now() - start > count * DEF_TPMAC_READ_FREQ:
                count += 1
                retStr = self.getResponse(cmd)
                key = match_int_response(retStr)
                if key in values:
                    return key

        raise PMACError(f"Timeout while waiting for {cmd} to be {values}")

    def waitForOutput(self, cmd, values, nr, func):
        start = datetime.now()
        count = 0

        assert isinstance(values, list), "Expected list argument"

        while datetime.now() - start < DEF_TPMAC_CMD_TIMEOUT:

            # Only read every DEF_TPMAC_READ_FREQ

            if datetime.now() - start > count * DEF_TPMAC_READ_FREQ:
                count += 1
                retStr = self.getResponse(cmd)
                Q20, out = extractQ20AndOutput(retStr, nr, func)
                if Q20 not in values:
                    continue
                return out

        raise PMACError(f"Timeout while waiting for {cmd} to be {values}")

    def getQVars(self, base, offsets, func=bytes.decode):
        """
        Get a list of values of Qxx variables, where xx = base + offset (for each offset).

        Throws a PMACError when no response received from Hexapod Hardware Controller.
        """
        qVars = map(lambda x: base + x, offsets)
        cmd = ""
        for qVar in qVars:
            cmd += f"Q{qVar:02} "
        retStr = self.getResponse(cmd)
        logger.flash_flood(f"retStr={retStr} of type {type(retStr)}")

        if retStr == b"\x00":
            raise PMACError(f"No response received for {cmd}, return value is {retStr}")

        # Remove the acknowledgement from the sourceStr

        retStr = retStr.rstrip(b"\r\x06")

        # Split the string in it's parts separated by \r

        qVarsResult = [func(x) for x in retStr.split(b"\r")]

        return qVarsResult

    def getMVars(self, base, offsets, func=bytes.decode):
        """
        Get a list of values of Mxx variables, where xx = base + offset (for each offset).

        The 'M' variables are Symétrie internal variables.
        The following M-Vars are known:

        * M5282 - check if a motion program is running, return 1 when it is running, 0 if no motion program is running

        Throws a PMACError when no response received from Hexapod Hardware Controller.
        """
        mVars = map(lambda x: base + x, offsets)
        cmd = ""
        for mVar in mVars:
            cmd += f"M{mVar:02} "
        retStr = self.getResponse(cmd)
        logger.debug(f"retStr={retStr} of type {type(retStr)}")

        if retStr == b"\x00":
            raise PMACError(f"No response received for {cmd}, return value is {retStr}")

        # Remove the acknowledgement from the sourceStr

        retStr = retStr.rstrip(b"\r\x06")

        # Split the string in it's parts separated by \r

        mVarsResult = [func(x) for x in retStr.split(b"\r")]

        return mVarsResult

    def getIVars(self, base, offsets, func=bytes.decode):
        """
        Get a list of values of Ixxxx variables, where xxxx = base + offset (for each offset).
        """
        iVars = map(lambda x: base + x, offsets)
        cmd = ""
        for iVar in iVars:
            cmd += "i%d " % iVar
        retStr = self.getResponse(cmd)
        logger.debug(f"retStr={retStr} of type {type(retStr)}")

        # Remove the acknowledgement from the sourceStr

        retStr = retStr.rstrip(b"\r\x06")

        # Split the string in it's parts separated by \r

        iVarsResult = [func(x) for x in retStr.split(b"\r")]

        return iVarsResult

    def getPmacModel(self):
        """
        Return a string designating which PMAC model this is.

        Raise a PMACError if the model is unknown.
        """

        if self.modelName:
            return self.modelName

        # Ask for pmac model, returns an integer

        modelCode = self.getCID()

        # Return a model designation based on model code

        modelNamesByCode = {602413: "Turbo PMAC2-VME", 603382: "Geo Brick (3U Turbo PMAC2)"}
        try:
            modelName = modelNamesByCode[modelCode]
        except KeyError as e_key:
            raise PMACError(f"Unsupported PMAC model: modelCode={modelCode}") from e_key

        self.modelName = modelName

        return modelName

    def getCID(self):
        retStr = self.getResponse(CMD_STRING_CID)
        return match_int_response(retStr)

    def getVersion(self):
        retStr = self.getResponse(CMD_STRING_VER)
        return match_float_response(retStr)

    def getCPU(self):
        retStr = self.getResponse(CMD_STRING_CPU)
        return match_string_response(retStr)

    def getType(self):
        retStr = self.getResponse(CMD_STRING_TYPE)
        return match_string_response(retStr)

    def getVID(self):
        retStr = self.getResponse(CMD_STRING_VID)
        return match_string_response(retStr)

    def getDate(self):
        retStr = self.getResponse(CMD_STRING_DATE)
        return match_string_response(retStr)

    def getTime(self):
        retStr = self.getResponse(CMD_STRING_TIME)
        return match_string_response(retStr)

    def getToday(self):
        retStr = self.getResponse(CMD_STRING_TODAY)
        return match_string_response(retStr)

    def sendCommand(self, cmd, **kwargs):
        """
        Sends a command string to the TPMAC.

        Once the acknowledgment is received, it interrogates the TPMAC Q20 variable
        each DEF_TPMAC_READ_FREQ microseconds until Q20 = 0 or -1 or -2.

        Throws a PMACError:
            * when the arguments do not match up
            * when there is a Time-Out
            * when there is a socket communication error

        Returns the Q20 value as an integer.
        """

        # When we expect input parameters, make sure the number of **kwargs matches the cmd['in']
        # and format the command with the given keyword arguments.raise

        if cmd["in"] > 0:
            if len(kwargs) == cmd["in"]:
                fullCommand = cmd["cmd"].format(**kwargs)
            else:
                raise PMACError(
                    f"Expected {cmd['in']} keyword arguments to cmd['name'], got {len(kwargs)}"
                )
        else:
            fullCommand = cmd["cmd"]

        logger.flash_flood(f'Sending the {cmd["name"]} command.')

        retStr = self.getResponse(fullCommand)

        logger.flash_flood(f'Command \'{cmd["name"]}\' returned "{retStr}"')

        # Check the return code (usually Q20)

        if cmd["out"] == 0 and cmd["return"] is not None:

            # The following method can throw a PMACError on Timeout

            rc = self.waitFor(cmd["return"], cmd["check"])
            logger.debug(f"waitFor returned {rc}")

            return rc

        # Get and return the output parameters

        if cmd["out"] > 0 and cmd["return"] is not None:

            # The following method can throw a PMACError on Timeout

            out = self.waitForOutput(cmd["return"], cmd["check"], cmd["out"], cmd["out_type"])
            logger.debug(f"waitForAndOutput returned {out}")

            return out

        # Get the output parameters out of the retStr

        if cmd["out"] > 0 and cmd["return"] is None:
            out = extractOutput(retStr, cmd["out"], cmd["out_type"])

            return out
        #
        return None


if __name__ == "__main__":
    pass
