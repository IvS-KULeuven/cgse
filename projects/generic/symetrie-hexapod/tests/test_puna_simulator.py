import time
import pytest
import numpy as np
import logging

from egse.hexapod import HexapodError
from egse.hexapod.symetrie.puna import PunaSimulator as Hexapod

_LOGGER = logging.getLogger(__name__)


def wait_until(condition, interval=0.1, timeout=1, *args):
    start = time.time()
    while not condition(*args):
        if time.time() - start > timeout:
            _LOGGER.warning(f"Timeout after {timeout} sec, condition{args} not met.")
            break
        time.sleep(interval)


def test_goto_zero_position():
    hexapod = Hexapod()

    try:
        rc = hexapod.goto_zero_position()

        assert rc == 0

        out = hexapod.get_user_positions()
        check_positions(out, (0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        out = hexapod.get_machine_positions()
        check_positions(out, (0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

    except HexapodError:
        assert False
    finally:
        hexapod.disconnect()


def test_position_after_homing():
    hexapod = Hexapod()

    try:
        hexapod.move_absolute(5, 0, 0, 0, 0, 0)

        out = hexapod.get_user_positions()
        check_positions(out, (5.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        out = hexapod.get_machine_positions()
        check_positions(out, (5.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        hexapod.move_absolute(5, 2, 0, 0, 0, 0)

        out = hexapod.get_user_positions()
        check_positions(out, (5.00000, 2.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        out = hexapod.get_machine_positions()
        check_positions(out, (5.00000, 2.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        rc = hexapod.homing()
        assert rc == 0

        out = hexapod.get_user_positions()
        check_positions(out, (0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        out = hexapod.get_machine_positions()
        check_positions(out, (0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

    except HexapodError:
        assert False
    finally:
        hexapod.disconnect()


def test_construction():
    hexapod = Hexapod()
    assert hexapod.is_simulator()
    assert not hexapod.is_homing_done()


def test_absolute_movement2():
    """
    This test originated from a problem with the values of Machine positions after a simple rotation.
    """
    hexapod = Hexapod()

    try:
        tx, ty, tz = [0, 10, 0]
        rx, ry, rz = [0, 0, 0]

        rc = hexapod.move_absolute(tx, ty, tz, rx, ry, rz)
        assert rc == 0

        out = hexapod.get_user_positions()
        check_positions(out, (0.00000, 10.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        out = hexapod.get_machine_positions()
        check_positions(out, (0.00000, 10.00000, 0.00000, 0.00000, 0.00000, 0.00000))

    except HexapodError:
        assert False
    finally:
        hexapod.disconnect()


def test_absolute_movement1():
    hexapod = Hexapod()

    try:
        tx, ty, tz = [1, 3, 4]
        rx, ry, rz = [35, 25, 10]

        rc = hexapod.move_absolute(tx, ty, tz, rx, ry, rz)
        assert rc == 0

        out = hexapod.get_user_positions()
        check_positions(out, (1.00000, 3.00000, 4.00000, 35.00000, 25.00000, 10.00000))

    except HexapodError:
        assert False
    finally:
        hexapod.disconnect()


def test_absolute_movement():
    hexapod = Hexapod()

    try:
        tx_u, ty_u, tz_u = -2, -2, -2
        rx_u, ry_u, rz_u = -3, -4, -5

        tx_o, ty_o, tz_o = 0, 0, 3
        rx_o, ry_o, rz_o = np.rad2deg(np.pi / 6.0), np.rad2deg(np.pi / 6.0), 0

        hexapod.configure_coordinates_systems(tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o)

        out = hexapod.get_user_positions()
        check_positions(out, (2.162431533, 1.9093265385, 4.967732082, 34.01008683, 33.65884585, 7.22137656))

        out = hexapod.get_machine_positions()
        check_positions(out, (0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

        tx, ty, tz = [1, 3, 4]
        rx, ry, rz = [35, 25, 10]

        rc = hexapod.move_absolute(tx, ty, tz, rx, ry, rz)
        assert rc == 0

        wait_until(hexapod.is_in_position, 1, 300)

        out = hexapod.get_user_positions()
        check_positions(out, (1.00000, 3.00000, 4.00000, 35.00000, 25.00000, 10.00000))

        out = hexapod.get_machine_positions()
        check_positions(out, (-0.5550577685, 1.2043056694, -1.0689145898, 1.0195290202, -8.466485292, 2.79932335))

        # Test the move relative object

        tx, ty, tz = -1, -1, -1
        rx, ry, rz = 1, 7, -1

        hexapod.move_relative_object(tx, ty, tz, rx, ry, rz)

        wait_until(hexapod.is_in_position, 1, 300)

        out = hexapod.get_user_positions()
        check_positions(out, (-0.4295447122, 2.49856887, 3.160383195, 37.82597474, 31.25750377, 13.736721917))

        out = hexapod.get_machine_positions()
        check_positions(out, (-2.317005597, 0.8737649564, -2.006061295, 3.052233715, -1.9466592653, 4.741402017))

        # Test the move relative user

        tx, ty, tz = -2, -2, -2
        rx, ry, rz = 1, 7, -1

        hexapod.move_relative_user(tx, ty, tz, rx, ry, rz)

        wait_until(hexapod.is_in_position, 1, 300)

        out = hexapod.get_user_positions()
        check_positions(out, (-2.429542106, 0.4985648, 1.1603886537, 41.37225134, 37.32309944, 18.14008525))

        out = hexapod.get_machine_positions()
        check_positions(out, (-4.710341626, -0.97799175, -4.017462423, 5.310002306, 4.496313461, 6.918574645))

    except HexapodError:
        assert False
    finally:
        hexapod.disconnect()


def test_coordinates_systems():
    hexapod = Hexapod()

    try:
        rc = hexapod.configure_coordinates_systems(1.2, 2.1, 1.3, 0.4, 0.3, 0.2, 1.3, 2.2, 1.2, 0.1, 0.2, 0.3)

        assert rc >= 0

        out = hexapod.get_coordinates_systems()

        check_positions(out[:6], (1.2, 2.1, 1.3, 0.4, 0.3, 0.2))
        check_positions(out[6:], (1.3, 2.2, 1.2, 0.1, 0.2, 0.3))

    except HexapodError:
        assert False
    finally:
        hexapod.disconnect()


def check_positions(out, expected, precision=0.00001):
    assert len(out) == len(expected)

    for idx, element in enumerate(out):
        assert element == pytest.approx(expected[idx], precision)
