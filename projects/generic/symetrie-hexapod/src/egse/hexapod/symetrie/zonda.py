"""
This module defines the device classes to be used to connect to and control the Hexapod ZONDA from
Symétrie.

"""
import logging
import math
import time
from typing import Dict

from egse.device import DeviceInterface
from egse.hexapod import HexapodError
from egse.hexapod.symetrie.alpha import AlphaPlusControllerInterface
from egse.hexapod.symetrie.zonda_devif import RETURN_CODES
from egse.hexapod.symetrie.zonda_devif import ZondaError
from egse.hexapod.symetrie.zonda_devif import ZondaTelnetInterface
from egse.hexapod.symetrie.zonda_devif import decode_command
from egse.proxy import Proxy
from egse.settings import Settings
from egse.system import Timer
from egse.system import wait_until
from egse.zmq_ser import connect_address
from numpy import loadtxt
from time import sleep

logger = logging.getLogger(__name__)

ZONDA_SETTINGS = Settings.load("ZONDA Controller")
CTRL_SETTINGS = Settings.load("Hexapod ZONDA Control Server")
DEVICE_SETTINGS = Settings.load(filename="zonda.yaml")

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

VALIDATION_LIMITS = [
    "Factory workspace limits",
    "Machine workspace limits",
    "User workspace limits",
    "Actuator limits",
    "Joints limits",
    "Due to backlash compensation",
]


class ZondaInterface(AlphaPlusControllerInterface, DeviceInterface):
    """
    Interface definition for the ZondaController, the ZondaProxy and the ZondaSimulator.
    """


class ZondaController(ZondaInterface):
    def __init__(self):

        super().__init__()

        logger.info(f"Initializing ZondaController with hostname={ZONDA_SETTINGS.IP} on port={ZONDA_SETTINGS.PORT}")

        self.v_pos = None

        self.cm = ["absolute", "object relative", "user relative"]

        self.speed = {"vt": 0,
                      "vr": 0,
                      "vtmin": 0,
                      "vrmin": 0,
                      "vtmax": 0,
                      "vrmax": 0}

        try:
            self.hexapod = ZondaTelnetInterface()

        except ZondaError as exc:
            logger.warning(
                f"HexapodError: Couldn't establish connection with the Hexapod ZONDA Hardware "
                f"Controller: ({exc})"
            )

    def is_simulator(self):
        return False

    def is_connected(self):
        return self.hexapod.is_connected()

    def connect(self):
        try:
            self.hexapod.connect(ZONDA_SETTINGS.IP)
        except ZondaError as exc:
            logger.warning(f"ZondaError caught: Couldn't establish connection ({exc})")
            raise HexapodError("Couldn't establish a connection with the Hexapod.") from exc

    def disconnect(self):
        try:
            self.hexapod.disconnect()
        except ZondaError as exc:
            raise HexapodError("Couldn't disconnect from Hexapod.") from exc

    def reconnect(self):
        if self.is_connected():
            self.disconnect()
        self.connect()

    def info(self):
        try:
            _version = self.hexapod.trans("VERS")
            msg = "Info about the Hexapod ZONDA:\n"
            msg += f"version = {_version}\n"
        except ZondaError as exc:
            raise HexapodError(
                "Couldn't retrieve information from Hexapod ZONDA Hardware Controller."
            ) from exc

        return msg

    def get_general_state(self):
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
        try:
            rc = self.hexapod.trans("s_hexa")
            rc = int(rc[0])

            # from int to bit list of 15 elements corresponding to the hexapod state bits
            # the bit list must be reversed to get lsb

            s_hexa = [int(x) for x in f'{rc:015b}'[::-1]]
            state = {k: v for k, v in zip(GENERAL_STATE, s_hexa)}
        except ZondaError as exc:
            raise HexapodError("Couldn't retrieve the state from Hexapod.") from exc

        return [state, list(state.values())]

    def stop(self):
        try:
            self.hexapod.trans("c_cmd=C_STOP")
            sc = self.hexapod.check_command_status()
            logger.warning(f"Stop command has been executed: {sc}")
        except ZondaError as exc:
            raise HexapodError("Couldn't disconnect from Hexapod.") from exc
        return sc

    def clear_error(self):
        try:
            print("Cleaning errors from buffer")
            sc = self.hexapod.trans("c_cmd=C_CLEARERROR")
            number = self.hexapod.trans('s_err_nr')
            number = int(number[0])

            if number == 0:
                logger.info("All the errors have been cleared.")
            else:
                logger.warning("Couldn't clear all errors from Hexapod.")

        except ZondaError as exc:
            raise HexapodError("Couldn't clear all the errors from Hexapod.") from exc
        return sc

    def reset(self, wait=True):
        try:
            print("Resetting the Hexapod Controller")
            print("STOP and CONTROLOFF commands are sent to the controller before resetting...")
            self.stop()
            print("Hexapod is stopped")
            self.deactivate_control_loop()
            print("Hexapod control loop has been deactivated")

            print("Rebooting the controller: will take 2 min to initialize")

            # FIXME: you might want to rethink this, because the reboot will close the Ethernet
            #     connection and therefore we need to reconnect after a two minutes waiting time.
            #     During the waiting time, the GUI should have all functions disabled and the
            #     connection icon should show a disconnected icon. Don't use `time.sleep()` as
            #     that will block the GUI, run a timer in a QThread signaling a reconnect when
            #     the sleep time is over.
            self.hexapod.trans("system reboot")

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return None

    def jog(self, axis: int, inc: float):
        try:
            self.hexapod.trans("c_ax={} c_par(0)={} c_cmd=C_JOG")
            sc = self.hexapod.check_command_status()

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return sc

    def perform_maintenance(self, axis):
        try:
            if axis == 10:
                self.hexapod.trans("c_par(0)=3 c_cmd=C_MAINTENANCE")
            else:
                self.hexapod.trans("c_par(0)=2 c_par(1)={} c_cmd=C_MAINTENANCE".format(str(axis)))

            sc = self.hexapod.check_command_status()
        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return sc

    def set_default(self):
        try:
            print("Resetting the hexapod to the factory default parameters...:")
            self.hexapod.trans("c_cfg=1 c_cmd=C_CFG_DEFAULT")
            sc = self.hexapod.check_command_status()

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return sc

    def homing(self):
        try:
            print("Executing homing command")
            self.hexapod.trans("c_cmd=C_HOME")
            sc = self.hexapod.check_command_status()

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return sc

    def goto_specific_position(self, pos):
        try:
            sc = self.hexapod.trans("c_par(0)={} c_cmd=C_MOVE_SPECIFICPOS".format(str(pos)))
            print(sc)

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return sc

    def goto_zero_position(self):
        try:
            sc = self.hexapod.trans("c_par(0)=1 c_cmd=C_MOVE_SPECIFICPOS")
            print(sc)

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return sc

    def goto_retracted_position(self):
        try:
            sc = self.hexapod.trans("c_par(0)=2 c_cmd=C_MOVE_SPECIFICPOS")
            print(sc)

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return sc

    def is_homing_done(self):
        try:
            sc = self.get_general_state()
            homing = sc[1][HOME_COMPLETE]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return homing

    def is_in_position(self):
        try:
            sc = self.get_general_state()
            in_position = sc[1][IN_POSITION]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return in_position

    def activate_control_loop(self):
        try:
            self.hexapod.trans("c_cmd=C_CONTROLON")
            print("Executing activate_control_loop command")
            sc = self.hexapod.check_command_status()
        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return sc

    def deactivate_control_loop(self):
        try:
            self.hexapod.trans("c_cmd=C_CONTROLOFF")
            print("Executing deactivate_control_loop")
            sc = self.hexapod.check_command_status()
        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return sc

    def machine_limit_enable(self, state: int):
        try:
            command = decode_command("CFG_LIMITENABLE", 1, state)
            print(f"Executing machine_limit_enable command to state {state}. ")
            self.hexapod.trans(command)
            rc = self.hexapod.check_command_status()
        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return rc

    def machine_limit_set(
            self, tx_n, ty_n, tz_n, rx_n, ry_n, rz_n, tx_p, ty_p, tz_p, rx_p, ry_p, rz_p):
        try:
            name = "CFG_LIMIT"
            arguments = [1, tx_n, ty_n, tz_n, rx_n, ry_n, rz_n, tx_p, ty_p, tz_p, rx_p, ry_p, rz_p]

            cmd = decode_command(name, *arguments)

            print("Executing machine_limit_set command {}...: ".format(cmd), end="")
            self.hexapod.trans(cmd)
            self.hexapod.check_command_status()

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

    def user_limit_enable(self, state: int):
        try:
            command = decode_command("CFG_LIMITENABLE", 2, state)
            print(f"Executing user_limit_enable command to state {state}...: ")
            self.hexapod.trans(command)
            self.hexapod.check_command_status()
        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return None

    def user_limit_set(
            self, tx_n, ty_n, tz_n, rx_n, ry_n, rz_n, tx_p, ty_p, tz_p, rx_p, ry_p, rz_p):
        try:
            name = "CFG_LIMIT"
            arguments = [2, tx_n, ty_n, tz_n, rx_n, ry_n, rz_n, tx_p, ty_p, tz_p, rx_p, ry_p, rz_p]

            cmd = decode_command(name, *arguments)

            print(f"Executing user_limit_set command {cmd}...: ")
            self.hexapod.trans(cmd)
            rc = self.hexapod.check_command_status()

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return rc

    def __move(self, cm, tx, ty, tz, rx, ry, rz):
        """
        Ask the controller to perform the movement defined by the arguments and the command MOVE_PTP.

        For all control modes cm, the rotation centre coincides with the Object
        Coordinates System origin and the movements are controlled with translation
        components at first (Tx, Ty, tZ) and then the rotation components (Rx, Ry, Rz).

        Control mode cm:
            * 0 = absolute control, object coordinate system position and orientation
                    expressed in the invariant user coordinate system
            * 1 = object relative, motion expressed in the Object Coordinate System
            * 2 = user relative, motion expressed in the User Coordinate System

        Args:
            cm (int): control mode
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]
        """

        name = "MOVE_PTP"
        arguments = [cm, tx, ty, tz, rx, ry, rz]

        command = decode_command(name, *arguments)
        print(f"Executing move_ptp command in {self.cm[cm]} mode ... {command}")
        self.hexapod.trans(command)
        return self.hexapod.check_command_status()

    def validate_position(self, vm, cm, tx, ty, tz, rx, ry, rz):
        # Currently only the vm=1 mode is developed by Symétrie
        """
        Ask the controller if the movement defined by the arguments is feasible.

        Returns a tuple where the first element is an integer that represents the
        bitfield encoding the errors. The second element is a dictionary with the
        bit numbers that were (on) and the corresponding error description as
        defined by VALIDATION_LIMITS.

        Args:
            tx (float): position on the X-axis [mm]
            ty (float): position on the Y-axis [mm]
            tz (float): position on the Z-axis [mm]
            rx (float): rotation around the X-axis [deg]
            ry (float): rotation around the Y-axis [deg]
            rz (float): rotation around the Z-axis [deg]

        """
        name = "VALID_PTP"
        arguments = [vm, cm, tx, ty, tz, rx, ry, rz]

        command = decode_command(name, *arguments)

        #print(f"Executing validate_position command: {command}")

        self.hexapod.trans(command)
        rc = self.hexapod.check_command_status()
        pc = self.hexapod.get_pars(0)
        pc = int(pc[0])

        if pc == 0:
            return 0, {}

        if pc > 0:
            d = decode_validation_error(pc)
            return pc, d

        # When coming here the command returned an error

        msg = f"{RETURN_CODES.get(pc, 'unknown error code')}"
        logger.error(f"Validate position: error code={pc} - {msg}")

        return pc, {pc: msg}

    def move_absolute(self, tx, ty, tz, rx, ry, rz):
        try:
            rc = self.__move(0, tx, ty, tz, rx, ry, rz)

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return rc

    def move_relative_object(self, tx, ty, tz, rx, ry, rz):
        try:
            rc = self.__move(1, tx, ty, tz, rx, ry, rz)

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return rc

    def move_relative_user(self, tx, ty, tz, rx, ry, rz):
        try:
            rc = self.__move(2, tx, ty, tz, rx, ry, rz)

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return rc

    def check_absolute_movement(self, tx, ty, tz, rx, ry, rz):
        # Currently only the vm=1 mode is developed by Symétrie
        # Parameter cm = 0
        return self.validate_position(1, 0, tx, ty, tz, rx, ry, rz)

    def check_relative_object_movement(self, tx, ty, tz, rx, ry, rz):
        # Currently only the vm=1 mode is developed by Symétrie
        # Parameter cm = 1 for object
        return self.validate_position(1, 1, tx, ty, tz, rx, ry, rz)

    def check_relative_user_movement(self, tx, ty, tz, rx, ry, rz):
        # Currently only the vm=1 mode is developed by Symétrie
        # Parameter cm = 2 for user relative
        return self.validate_position(1, 2, tx, ty, tz, rx, ry, rz)

    def get_temperature(self):
        #TODO: to be tested with the real Hexapod (the emulator does not implement this and only returns zeros)
        try:
            temp = self.hexapod.trans("s_ai_1,6,1")
            temp = [float(x) for x in temp]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return temp

    def get_user_positions(self):
        try:
            uto = self.hexapod.trans("s_uto_tx,6,1")
            uto = [float(x) for x in uto]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return uto

    def get_machine_positions(self):
        try:
            mtp = self.hexapod.trans("s_mtp_tx,6,1")
            mtp = [float(x) for x in mtp]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return mtp

    def get_actuator_length(self):
        try:
            pos = self.hexapod.trans("s_pos_ax_1,6,1")
            pos = [float(x) for x in pos]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return pos

    def get_actuator_state(self):

        response = []
        try:
            actuator_states = self.hexapod.trans("s_ax_1,6,1")
            actuator_states = [int(x) for x in actuator_states]

            for idx, state in enumerate(actuator_states):
                state_bits = [int(x) for x in f'{state:015b}'[::-1]]
                state_dict = {k: v for k, v in zip(ACTUATOR_STATE, state_bits)}
                response.append([state_dict, state_bits])

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return response

    def get_coordinates_systems(self):
        try:
            command = decode_command("CFG_CS?")
            print(f"Executing get_coordinate_system command: {command}")
            self.hexapod.trans(command)
            sc = self.hexapod.check_command_status()
            cs = self.hexapod.get_pars(12)
            cs = [float(x) for x in cs]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return cs

    def configure_coordinates_systems(
        self, tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o
    ):
        try:
            name = "CFG_CS"
            arguments = [tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o]
            command = decode_command(name, *arguments)
            print(f"Executing configure_coordinates_systems: {command}")
            self.hexapod.trans(command)
            rc = self.hexapod.check_command_status()

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return rc

    def get_limits_value(self, lim):
        # Not implemented in Puna
        # lim: int | 0 = Factory, 1 = machine cs limits, 2 = user cs limits
        try:
            cmd = decode_command("CFG_LIMIT?", lim)
            print(f"Executing get_limits_value command: {cmd=}")
            self.hexapod.trans(cmd)
            self.hexapod.check_command_status()

            pc = self.hexapod.get_pars(13)
            pc = [float(x) for x in pc[1:]]

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return pc

    def get_limits_state(self):
        # not implemented in Puna
        try:
            command = decode_command("CFG_LIMITENABLE?")
            print(f"Executing get_limits_state command: {command=}")
            self.hexapod.trans(command)
            sc = self.hexapod.check_command_status()

            if sc[0] == 0:
                pc = self.hexapod.get_pars(3)
                pc = [int(i) for i in pc]
            else:
                pc = ["nan", "nan", "nan"]

            keys = VALIDATION_LIMITS[:3]
            ls = {k: v for k, v in zip(keys, pc)}

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc

        return ls

    def get_speed(self):
        try:
            command = decode_command("CFG_SPEED?")
            print(f"Executing get_speed command: {command}")
            self.hexapod.trans(command)
            sc = self.hexapod.check_command_status()
            speed = self.hexapod.get_pars(6)
            speed = [float(x) for x in speed]
            keys = list(self.speed.keys())

            s = {k: v for k, v in zip(keys, speed)}

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return s

    def set_speed(self, vt, vr):
        try:
            name = "CFG_SPEED"
            arguments = [vt, vr]
            command = decode_command(name, *arguments)
            # The parameters are automatically limited by the controller between the factory
            # configured min/max speeds
            self.hexapod.trans(command)

        except ZondaError as exc:
            raise HexapodError("Couldn't Execute command on Hexapod.") from exc
        return

    def sequence(self, file_path: str, time_sleep: float):
        file = file_path + ".txt"
        SEQUENCE = loadtxt(file)
        for step in SEQUENCE:
            state = self.check_absolute_movement(step[0], step[1], step[2], step[3], step[4], step[5])
            if state[0] != 0:
                print('Error: Out of bounds! One point is out of the workspace!')
                return
        print("OK! The entire trajectory is reachable in the defined workspace.")
        step_number = 0
        for step in SEQUENCE:
            step_number += 1
            print("\nExecuting step number ", step_number, "over ", len(SEQUENCE), ": ", step)
            self.move_absolute(step[0], step[1], step[2], step[3], step[4], step[5])
            in_pos = self.get_general_state()[1][3]
            while not(in_pos):
                in_pos = self.get_general_state()[1][3]
            print("Step ", step_number, "done.\nWaiting for ", time_sleep, "seconds.")
            sleep(time_sleep)
        print('Sequence "' + file_path + '" done with success!')


class ZondaSimulator(ZondaInterface):
    """
    HexapodSimulator simulates the Symétrie Hexapod ZONDA. The class is heavily based on the
    ReferenceFrames in the `egse.coordinates` package.

    The simulator implements the same methods as the HexapodController class which acts on the
    real hardware controller in either simulation mode or with a real Hexapod ZONDA connected.

    Therefore, the HexapodSimulator can be used instead of the Hexapod class in test harnesses
    and when the hardware is not available.

    This class simulates all the movements and status of the Hexapod.
    """
    def __init__(self):
        # Keep a record if the homing() command has been executed.

        self.homing_done = False
        self.control_loop = False
        self._virtual_homing = False
        self._virtual_homing_position = None

    def is_simulator(self):
        return True

    def connect(self):
        pass

    def reconnect(self):
        pass

    def disconnect(self):
        # TODO:
        #   Should I keep state in this class to check if it has been disconnected?
        #
        # TODO:
        #   What happens when I re-connect to this Simulator? Shall it be in Homing position or
        #   do I have to keep state via a persistency mechanism?
        pass

    def is_connected(self):
        return True

    def clear_error(self):
        return 0

    def homing(self):
        self.goto_zero_position()
        self.homing_done = True
        self._virtual_homing = False
        self._virtual_homing_position = None
        return 0

    def is_homing_done(self):
        return self.homing_done

    def activate_control_loop(self):
        self.control_loop = True
        return self.control_loop

    def deactivate_control_loop(self):
        self.control_loop = False
        return self.control_loop

    pass


class ZondaProxy(Proxy, ZondaInterface):
    """The ZondaProxy class is used to connect to the control server and send commands to the
    Hexapod ZONDA remotely."""

    def __init__(
            self,
            protocol=CTRL_SETTINGS.PROTOCOL,
            hostname=CTRL_SETTINGS.HOSTNAME,
            port=CTRL_SETTINGS.COMMANDING_PORT,
    ):
        """
        Args:
            protocol: the transport protocol [default is taken from settings file]
            hostname: location of the control server (IP address) [default is taken from settings
            file]
            port: TCP port on which the control server is listening for commands [default is
            taken from settings file]
        """
        super().__init__(connect_address(protocol, hostname, port))


def decode_validation_error(value) -> Dict:
    """
    Decode the bitfield variable that is returned by the VALID_PTP command.

    Each bit in this variable represents a particular error in the validation of a movement.
    Several errors can be combined into the given variable.

    Returns a dictionary with the bit numbers that were (on) and the corresponding error description.
    """

    return {bit: VALIDATION_LIMITS[bit] for bit in range(6) if value >> bit & 0b01}


if __name__ == "__main__":

    from rich import print as rp

    zonda = ZondaController()
    zonda.connect()

    with Timer("ZondaController"):

        rp(zonda.info())
        rp(zonda.is_homing_done())
        rp(zonda.is_in_position())
        rp(zonda.activate_control_loop())
        rp(zonda.get_general_state())
        rp(zonda.get_actuator_state())
        rp(zonda.deactivate_control_loop())
        rp(zonda.get_general_state())
        rp(zonda.get_actuator_state())
        rp(zonda.stop())
        rp(zonda.get_limits_value(0))
        rp(zonda.get_limits_value(1))
        rp(zonda.check_absolute_movement(1, 1, 1, 1, 1, 1))
        rp(zonda.check_absolute_movement(51, 51, 51, 1, 1, 1))
        rp(zonda.get_speed())
        rp(zonda.set_speed(2.0, 1.0))
        time.sleep(0.5)  # if we do not sleep, the get_speed() will get the old values
        speed = zonda.get_speed()

        if not math.isclose(speed['vt'], 2.0):
            rp(f"[red]{speed['vt']} != 2.0[/red]")
        if not math.isclose(speed['vr'], 1.0):
            rp(f"[red]{speed['vr']} != 1.0[/red]")

        rp(zonda.get_actuator_length())

        # rp(zonda.machine_limit_enable(0))
        # rp(zonda.machine_limit_enable(1))
        # rp(zonda.get_limits_state())
        rp(zonda.get_coordinates_systems())
        rp(zonda.configure_coordinates_systems(
            0.033000, -0.238000, 230.205000, 0.003282, 0.005671, 0.013930,
            0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000))
        rp(zonda.get_coordinates_systems())
        rp(zonda.get_machine_positions())
        rp(zonda.get_user_positions())
        rp(zonda.configure_coordinates_systems(
            0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
            0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000))
        rp(zonda.validate_position(1, 0, 0, 0, 0, 0, 0, 0))
        rp(zonda.validate_position(1, 0, 0, 0, 50, 0, 0, 0))

        rp(zonda.goto_zero_position())
        rp(zonda.is_in_position())
        if wait_until(zonda.is_in_position, interval=1, timeout=300):
            rp("[red]Task zonda.is_in_position() timed out after 30s.[/red]")
        rp(zonda.is_in_position())

        rp(zonda.get_machine_positions())
        rp(zonda.get_user_positions())

        rp(zonda.move_absolute(0, 0, 12, 0, 0, 10))

        rp(zonda.is_in_position())
        if wait_until(zonda.is_in_position, interval=1, timeout=300):
            rp("[red]Task zonda.is_in_position() timed out after 30s.[/red]")
        rp(zonda.is_in_position())

        rp(zonda.get_machine_positions())
        rp(zonda.get_user_positions())

        rp(zonda.move_absolute(0, 0, 0, 0, 0, 0))

        rp(zonda.is_in_position())
        if wait_until(zonda.is_in_position, interval=1, timeout=300):
            rp("[red]Task zonda.is_in_position() timed out after 30s.[/red]")
        rp(zonda.is_in_position())

        rp(zonda.get_machine_positions())
        rp(zonda.get_user_positions())

        # zonda.reset()
        zonda.disconnect()

        # rp(0, decode_validation_error(0))
        # rp(11, decode_validation_error(11))
        # rp(8, decode_validation_error(8))
        # rp(24, decode_validation_error(24))
