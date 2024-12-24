"""
This module defines the device classes to be used to connect to and control the Hexapod JORAN from
Symétrie.

"""
import logging
import math
import time

from egse.hexapod.symetrie.alpha import AlphaPlusControllerInterface
from egse.hexapod.symetrie.dynalpha import AlphaPlusTelnetInterface
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
