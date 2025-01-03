"""
This module defines the device classes to be used to connect to and control the Hexapod JORAN from
Symétrie.

"""
import logging
import math
import time

from egse.hexapod.symetrie.alpha import AlphaPlusControllerInterface
from egse.hexapod.symetrie.dynalpha import AlphaPlusTelnetInterface, decode_validation_error
from egse.mixin import DynamicCommandMixin
from egse.proxy import DynamicProxy
from egse.settings import Settings
from egse.system import Timer
from egse.system import wait_until
from egse.zmq_ser import connect_address

logger = logging.getLogger(__name__)

JORAN_SETTINGS = Settings.load("JORAN Controller")
CTRL_SETTINGS = Settings.load("Hexapod JORAN Control Server")
DEVICE_SETTINGS = Settings.load(filename="joran.yaml")


class JoranInterface(AlphaPlusControllerInterface):
    """
    Interface definition for the JoranController, the JoranProxy, and the JoranSimulator.
    """


class JoranController(JoranInterface, DynamicCommandMixin):

    def __init__(self):

        self.hostname = {JORAN_SETTINGS.IP}
        self.port = {JORAN_SETTINGS.PORT}
        self.transport = self.hexapod = AlphaPlusTelnetInterface(self.hostname, self.port)

        super.__init__()

    def is_simulator(self):
        return False

    def is_connected(self):
        return self.hexapod.is_connected()

    def connect(self):
        self.hexapod.connect()

    def disconnect(self):
        self.hexapod.disconnect()

    def reconnect(self):
        if self.is_connected():
            self.disconnect()
        self.connect()

    def reset(self, wait=True):
        raise NotImplementedError

    # def sequence(self):
    #     raise NotImplementedError

    def set_virtual_homing(self, tx, ty, tz, rx, ry, rz):
        raise NotImplementedError

    def get_debug_info(self):
        raise NotImplementedError

    def jog(self, axis: int, inc: float) -> int:
        raise NotImplementedError

    def get_temperature(self):
        raise NotImplementedError

    def get_limits_state(self):
        raise NotImplementedError

    def machine_limit_enable(self, state):
        raise NotImplementedError

    def user_limit_set(self, *par):
        raise NotImplementedError

    def set_default(self):
        raise NotImplementedError


class JoranSimulator(JoranInterface):
    """
    HexapodSimulator simulates the Symétrie Hexapod JORAN. The class is heavily based on the
    ReferenceFrames in the `egse.coordinates` package.

    The simulator implements the same methods as the HexapodController class which acts on the
    real hardware controller in either simulation mode or with a real Hexapod JORAN connected.

    Therefore, the HexapodSimulator can be used instead of the Hexapod class in test harnesses
    and when the hardware is not available.

    This class simulates all the movements and status of the Hexapod.
    """
    def __init__(self):

        super().__init__()

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
        #   do I have to keep state via a persistence mechanism?
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


class JoranProxy(DynamicProxy, JoranInterface):
    """The JoranProxy class is used to connect to the control server and send commands to the
    Hexapod JORAN remotely."""

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


if __name__ == "__main__":

    from rich import print as rp

    joran = JoranController()
    joran.connect()

    with Timer("JoranController"):

        rp(joran.info())
        rp(joran.is_homing_done())
        rp(joran.is_in_position())
        rp(joran.activate_control_loop())
        rp(joran.get_general_state())
        rp(joran.get_actuator_state())
        rp(joran.deactivate_control_loop())
        rp(joran.get_general_state())
        rp(joran.get_actuator_state())
        rp(joran.stop())
        rp(joran.get_limits_value(0))
        rp(joran.get_limits_value(1))
        rp(joran.check_absolute_movement(1, 1, 1, 1, 1, 1))
        rp(joran.check_absolute_movement(51, 51, 51, 1, 1, 1))
        rp(joran.get_speed())
        rp(joran.set_speed(2.0, 1.0))
        time.sleep(0.5)  # if we do not sleep, the get_speed() will get the old values
        speed = joran.get_speed()

        if not math.isclose(speed['vt'], 2.0):
            rp(f"[red]{speed['vt']} != 2.0[/red]")
        if not math.isclose(speed['vr'], 1.0):
            rp(f"[red]{speed['vr']} != 1.0[/red]")

        rp(joran.get_actuator_length())

        # rp(joran.machine_limit_enable(0))
        # rp(joran.machine_limit_enable(1))
        # rp(joran.get_limits_state())
        rp(joran.get_coordinates_systems())
        rp(joran.configure_coordinates_systems(
            0.033000, -0.238000, 230.205000, 0.003282, 0.005671, 0.013930,
            0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000))
        rp(joran.get_coordinates_systems())
        rp(joran.get_machine_positions())
        rp(joran.get_user_positions())
        rp(joran.configure_coordinates_systems(
            0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
            0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000))
        rp(joran.validate_position(1, 0, 0, 0, 0, 0, 0, 0))
        rp(joran.validate_position(1, 0, 0, 0, 50, 0, 0, 0))

        rp(joran.goto_zero_position())
        rp(joran.is_in_position())
        if wait_until(joran.is_in_position, interval=1, timeout=300):
            rp("[red]Task joran.is_in_position() timed out after 30s.[/red]")
        rp(joran.is_in_position())

        rp(joran.get_machine_positions())
        rp(joran.get_user_positions())

        rp(joran.move_absolute(0, 0, 12, 0, 0, 10))

        rp(joran.is_in_position())
        if wait_until(joran.is_in_position, interval=1, timeout=300):
            rp("[red]Task joran.is_in_position() timed out after 30s.[/red]")
        rp(joran.is_in_position())

        rp(joran.get_machine_positions())
        rp(joran.get_user_positions())

        rp(joran.move_absolute(0, 0, 0, 0, 0, 0))

        rp(joran.is_in_position())
        if wait_until(joran.is_in_position, interval=1, timeout=300):
            rp("[red]Task joran.is_in_position() timed out after 30s.[/red]")
        rp(joran.is_in_position())

        rp(joran.get_machine_positions())
        rp(joran.get_user_positions())

        # joran.reset()
        joran.disconnect()

        rp(0, decode_validation_error(0))
        rp(11, decode_validation_error(11))
        rp(8, decode_validation_error(8))
        rp(24, decode_validation_error(24))
