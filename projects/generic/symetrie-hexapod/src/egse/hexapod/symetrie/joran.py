"""
This module defines the device classes to be used to connect to and control the Hexapod JORAN from
Symétrie.

"""

import logging
import math
import random
import time

from egse.device import DeviceInterface
from egse.mixin import DynamicCommandMixin
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.system import Timer, wait_until
from egse.zmq_ser import connect_address

from egse.hexapod.symetrie.alpha import AlphaPlusControllerInterface
from egse.hexapod.symetrie.dynalpha import AlphaPlusTelnetInterface, decode_validation_error
from egse.hexapod.symetrie.hexapod import HexapodSimulator

logger = logging.getLogger(__name__)

JORAN_SETTINGS = Settings.load("Hexapod Controller")["JORAN"]
DEVICE_SETTINGS = Settings.load(filename="joran.yaml")

PROXY_TIMEOUT = 10.0  # don't wait longer than 10s by default


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


class JoranSimulator(HexapodSimulator, DeviceInterface):
    """
    HexapodSimulator simulates the Symétrie Hexapod JORAN. The class is heavily based on the
    ReferenceFrames in the `egse.coordinates` package.

    The simulator implements the same methods as the HexapodController class which acts on the
    real hardware controller in either simulation mode or with a real Hexapod JORAN connected.

    Therefore, the HexapodSimulator can be used instead of the Hexapod class in test harnesses
    and when the hardware is not available.

    This class simulates all the movements and status of the Hexapod.
    """

    def __init__(self, device_id: str):
        super().__init__()
        self._device_id = device_id

    @property
    def device_id(self):
        return self._device_id

    def get_temperature(self) -> list[float]:
        return [random.random() for _ in range(6)]


class JoranProxy(DynamicProxy, JoranInterface):
    """The JoranProxy class is used to connect to the control server and send commands to the
    Hexapod JORAN remotely.

    The control server is discovered from the service registry using ``device_id`` as the
    service type key, which is the same identifier used when the control server was started.

    Args:
        device_id: identifier of the hexapod control server as registered in the service registry
        timeout: how long to wait for a response from the control server before giving up
    """

    def __init__(self, device_id: str, *, timeout: float = PROXY_TIMEOUT):
        self._device_id = device_id
        super().__init__("", timeout=timeout, connect=False)

    @property
    def device_id(self):
        return self._device_id

    def connect_cs(self):
        with RegistryClient() as reg:
            service = reg.discover_service(self._device_id)

        if not service:
            raise ConnectionError(f"No control server registered as '{self._device_id}'.")

        protocol = service.get("protocol", "tcp")
        hostname = service["host"]
        port = service["port"]

        self._endpoint = connect_address(protocol, hostname, port)
        logger.info(f"JoranProxy connecting to {self._device_id!r} at {self._endpoint}")

        super().connect_cs()


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

        if not math.isclose(speed["vt"], 2.0):
            rp(f"[red]{speed['vt']} != 2.0[/red]")
        if not math.isclose(speed["vr"], 1.0):
            rp(f"[red]{speed['vr']} != 1.0[/red]")

        rp(joran.get_actuator_length())

        # rp(joran.machine_limit_enable(0))
        # rp(joran.machine_limit_enable(1))
        # rp(joran.get_limits_state())
        rp(joran.get_coordinates_systems())
        rp(
            joran.configure_coordinates_systems(
                0.033000,
                -0.238000,
                230.205000,
                0.003282,
                0.005671,
                0.013930,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
            )
        )
        rp(joran.get_coordinates_systems())
        rp(joran.get_machine_positions())
        rp(joran.get_user_positions())
        rp(
            joran.configure_coordinates_systems(
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
                0.000000,
            )
        )
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
