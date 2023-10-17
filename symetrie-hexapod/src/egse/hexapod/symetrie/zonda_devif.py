import logging
import socket
import threading
import time
from telnetlib import Telnet
from time import sleep
from typing import List

import paramiko

from egse.decorators import timer
from egse.device import DeviceTransport
from egse.settings import Settings
from egse.system import wait_until

logger = logging.getLogger(__name__)
ctrl_settings = Settings.load("ZONDA Controller")

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


class ZondaError(Exception):
    pass


class ZondaSSHInterface(object):
    def __init__(self):
        self.client = None
        self.gpascii_client = None
        self.connected = False
        self.ssh_output = None
        self.ssh_error = None
        self.verbose = False
        self.ip = ctrl_settings.IP

        self.semaphore = threading.Semaphore()

        self.CommandReturns = RETURN_CODES

    # Etablish the SSH connection with the controller and open gpascii
    def connect(self, ip):
        try:
            # Paramiko.SSHClient can be used to make connections to the remote server and
            # transfer files
            logger.info("Establishing ssh connection with {}...".format(ip))
            self.client = paramiko.SSHClient()
            # Parsing an instance of the AutoAddPolicy to set_missing_host_key_policy() changes
            # it to allow any host.
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(hostname=ip, port=22, username="root", password="deltatau",
                                timeout=5,
                                allow_agent=False, look_for_keys=False)
            logger.warning("Connected to the server: {}".format(ip))
            self.connected = True
        except paramiko.AuthenticationException:
            logger.warning("Authentication failed, please verify your credentials.")
            return False
        except paramiko.SSHException as sshException:
            logger.warning("Could not establish SSH connection: %s" % sshException)
            return False
        except socket.timeout as e:
            logger.warning("Connection timed out.")
            return False
        except Exception as e:
            logger.warning("Exception in connecting to the server.")
            logger.warning("Python says:", e)
            self.client.close()
            return False

        self.gpascii_client = self.client.invoke_shell(term="vt100")
        self.sendcommand("gpascii -2", 0.5)
        self.sendcommand("echo7")

    def is_connected(self):
        return self.connected

    # send a command through gpascii
    def sendcommand(self, command, wait=0):
        self.gpascii_client.send(command + "\r\n")
        if self.verbose == True:
            pass  # print("Command send: {}".format(command))

        if wait > 0:
            sleep(wait)

        # wait for response from gpascii
        step = 0.1
        time = 0

        while True:
            if self.gpascii_client.recv_ready():
                break
            if time > 2.0:
                logger.warning("Command response timed out!")
                return ""
            sleep(step)
            time += step

        # get and clean response
        response = self.gpascii_client.recv(2048)
        response = response.decode()
        response = response.replace(command, "")
        response = response.replace("\r", "")
        # response = response.replace("\n"," ")
        response = response.replace("\x06", "")

        # remove empty elements
        cleaned = ""
        lines = response.split("\n")
        for line in lines:
            if line == "" or line == " ":
                lines.remove(line)
            else:
                cleaned += line + "\n"

        # if self.verbose is True:
        # print("Command rcv: {}".format(cleaned))
        return cleaned

    def cmd_decode(self, name, arguments=list()):
        command = ""

        if "JOG" in name:
            command += "c_ax={} ".format(arguments[0])
            arguments.pop(0)

        # set cfg part
        cfg = 1
        if "?" in name:
            cfg = 0
            name = name.replace("?", "")
        if "CFG_" in name:
            command += "c_cfg={} ".format(cfg)

        # create the parameters part of a command using the given arguments
        for index in range(0, len(arguments)):
            command += "c_par({})={} ".format(index, arguments[index])

        # finish command line
        command += "c_cmd=C_{}".format(name)

        # logger.debug("command sent: ", command)
        return command

    def cmd_check(self):
        # sends "c_cmd" and returns the state of the command that has been previously sent.
        Timer = 0
        last = time.process_time()

        # For a maximum of 5 sec
        while Timer < 5:

            # wait and count
            time.sleep(0.1)
            Timer += time.process_time() - last
            last = time.process_time()

            # ask for command state
            response = self.sendcommand("c_cmd")
            response.replace("\n", "")

            if "=" in response:
                # get value
                elements = response.split("=", 1)
                element = elements[1]

                # exit if command is completed
                if int(element) <= 0:
                    response = element

            code = int(response)

            if code < 0:
                message = self.CommandReturns[code]
                logger.warning("Command Error return: {} : {}".format(code, message))
            elif code == 0:
                message = "Command successful: 0, execution time {} sec".format(Timer)
                # logger.info(message)
            return [code, message]
        logger.warning("Error: Order timed out !")
        return [-1, "Error: Order timed out !"]

    def p_check(self, number=20):
        # ask the value of the command parameters
        command = "c_par(0)"
        if number > 1:
            command += ",{},1".format(number)

        answer = self.sendcommand(command)
        return answer

    def disconnect(self):
        try:
            logger.info("Closing ssh connection with {}...")
            self.client.close()
            self.gpascii_client.close()
            self.connected = False
            logger.warning("...disconnected from ssh".format(self.ip))
        except Exception as e_exc:
            raise ZondaError(f"Could not close socket to ") from e_exc


class ZondaTelnetInterface(DeviceTransport):
    """
    The ZONDA Hexapod device interface based on the telnet protocol.
    """

    TELNET_TIMEOUT = 0.5

    def __init__(self):
        self.telnet = Telnet()
        self._is_connected = False

    def connect(self, hostname: str):
        self.telnet.open(hostname, 23)
        self.telnet.read_until(b"login: ", timeout=self.TELNET_TIMEOUT)
        self.telnet.write(b"root\r\n")
        self.telnet.read_until(b"Password: ", timeout=self.TELNET_TIMEOUT)
        self.telnet.write(b"deltatau\r\n")
        self.telnet.read_until(b"ppmac# ", timeout=self.TELNET_TIMEOUT)
        self.telnet.write(b"gpascii -2\r\n")
        self.telnet.write(b"echo7\r\n")
        self.telnet.read_until(b'\x06', timeout=self.TELNET_TIMEOUT)
        self.telnet.read_very_eager()
        self._is_connected = True

    def is_connected(self):
        return self._is_connected

    def disconnect(self):
        self.telnet.read_very_eager()
        self.telnet.close()
        self._is_connected = False

    def check_command_status(self):

        if wait_until(lambda: self.trans('c_cmd')[0] == '0', interval=0.01):
            rc = int(self.trans('c_cmd')[0])
            logger.warning(f"Command check: {RETURN_CODES[rc]} [{rc}]")
        else:
            rc = 0

        return rc, RETURN_CODES[rc]

    def get_pars(self, count: int = 20):
        # ask the value of the command parameters
        command = "c_par(0)"
        if count > 1:
            command += f",{count},1"

        return self.trans(command)

    def trans(self, cmd: str) -> List:
        self.write(cmd)
        response = self.read()
        if response and response[0] == cmd:
            return response[1:]
        else:
            return response

    def read(self) -> List:
        response = self.telnet.read_until(b'\x06\r\n', timeout=self.TELNET_TIMEOUT)
        response = response.decode()
        parts = response.split("\r\n")
        if len(parts) == 1:
            return []
        if parts[-2] == '\x06':
            return parts[:-2]
        logger.warning("Expected ACK at the end of the response")
        return parts

    def write(self, cmd: str):
        self.telnet.write(cmd.encode() + b"\r\n")


def decode_command(cmd_name: str, *args):

    args = list(args)
    cmd_name = cmd_name.upper()

    full_command = ""

    if "JOG" in cmd_name:
        arg = args.pop(0)
        full_command += f"c_ax={arg} "

    # set cfg part

    if "?" in cmd_name:
        cmd_name = cmd_name.replace("?", "")
        cfg = 0
    else:
        cfg = 1

    if "CFG_" in cmd_name:
        full_command += f"c_cfg={cfg} "

    # create the parameters part of a full_command using the given arguments

    for index, arg in enumerate(args):
        full_command += f"c_par({index})={arg} "

    # finish full_command line

    full_command += f"c_cmd=C_{cmd_name}"

    return full_command


if __name__ == "__main__":
    import rich

    zonda = ZondaTelnetInterface()
    zonda.connect("192.168.56.10")
    rich.print(zonda.trans("s_hexa,50,1"))
    rich.print(zonda.trans("s_ax_1,6,1"))
    rich.print(zonda.trans("s_pos_ax_1,6,1"))
    rich.print(zonda.read())
    zonda.disconnect()

    print(decode_command("CFG_LIMIT?", 0))
    print(decode_command("CFG_LIMIT", 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12))
