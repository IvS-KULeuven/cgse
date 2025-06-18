from functools import lru_cache

import numpy as np
import pytest
from pytest import approx

from egse.hexapod import HexapodError
from egse.hexapod.symetrie.puna import PunaController
from egse.hexapod.symetrie.puna import PunaSimulator
from egse.system import wait_until


# When the 'real' Hexapod controller is connected, the pytest can be run with the
# Hexapod class. However, by default we use the HexapodSimulator class for testing.


@pytest.fixture
@lru_cache
def hexapod():
    # hexapod = PunaController("127.0.0.1", 1025)  # Use the correct IP address here
    hexapod = PunaSimulator()
    return hexapod


def test_context_manager(hexapod):
    print()

    with hexapod:
        print(hexapod.info())


def test_connection(hexapod):
    with hexapod:
        hexapod.connect()
        hexapod.info()

        # FIXME: The controller might be in a bad state due to previous failures.
        #        We need some way to fix & reset the controller at the beginning of the unit tests.

        hexapod.clear_error()

        if hexapod.is_simulator():
            hexapod.reset(wait=False, verbose=False)  # Wait is not needed
        else:
            hexapod.reset(wait=True, verbose=False)  # Wait is definitely needed

        hexapod.homing()

        if wait_until(hexapod.is_homing_done, interval=0.5, timeout=300):
            assert False
        if wait_until(hexapod.is_in_position, interval=0.5, timeout=300):
            assert False

        assert hexapod.is_homing_done()


def test_goto_position(hexapod):
    with hexapod:
        hexapod.connect()
        rc = hexapod.goto_specific_position(1)

        assert rc in [0, -1, -2]  # FIXME: How can we do proper checking here?

        rc = hexapod.goto_specific_position(5)

        assert rc in [0, -1, -2]  # FIXME: How can we do proper checking here?


def test_absolute_movement(hexapod):
    with hexapod:
        hexapod.connect()

        tx_u, ty_u, tz_u = 0, 0, 0
        rx_u, ry_u, rz_u = 0, 0, 0
        tx_o, ty_o, tz_o = 0, 0, 0
        rx_o, ry_o, rz_o = 0, 0, 0

        hexapod.configure_coordinates_systems(tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o)
        hexapod.homing()

        if wait_until(hexapod.is_homing_done, interval=0.5, timeout=300):
            assert False
        if wait_until(hexapod.is_in_position, interval=1, timeout=300):
            assert False

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

        if wait_until(hexapod.is_in_position, interval=1, timeout=300):
            assert False

        out = hexapod.get_user_positions()
        check_positions(out, (1.00000, 3.00000, 4.00000, 35.00000, 25.00000, 10.00000))

        out = hexapod.get_machine_positions()
        check_positions(out, (-0.5550577685, 1.2043056694, -1.0689145898, 1.0195290202, -8.466485292, 2.79932335))

        # Test the move relative object

        tx, ty, tz = -1, -1, -1
        rx, ry, rz = 1, 7, -1

        hexapod.move_relative_object(tx, ty, tz, rx, ry, rz)

        if wait_until(hexapod.is_in_position, interval=1, timeout=300):
            assert False

        out = hexapod.get_user_positions()
        check_positions(out, (-0.4295447122, 2.49856887, 3.160383195, 37.82597474, 31.25750377, 13.736721917))

        out = hexapod.get_machine_positions()
        check_positions(out, (-2.317005597, 0.8737649564, -2.006061295, 3.052233715, -1.9466592653, 4.741402017))

        # Test the move relative user

        tx, ty, tz = -2, -2, -2
        rx, ry, rz = 1, 7, -1

        hexapod.move_relative_user(tx, ty, tz, rx, ry, rz)

        if wait_until(hexapod.is_in_position, interval=1, timeout=300):
            assert False

        out = hexapod.get_user_positions()
        check_positions(out, (-2.429542106, 0.4985648, 1.1603886537, 41.37225134, 37.32309944, 18.14008525))

        out = hexapod.get_machine_positions()
        check_positions(out, (-4.710341626, -0.97799175, -4.017462423, 5.310002306, 4.496313461, 6.918574645))


def test_coordinates_systems(hexapod):
    with hexapod:
        hexapod.connect()

        rc = hexapod.configure_coordinates_systems(1.2, 2.1, 1.3, 0.4, 0.3, 0.2, 1.3, 2.2, 1.2, 0.1, 0.2, 0.3)

        assert rc >= 0

        out = hexapod.get_coordinates_systems()

        check_positions(out[:6], (1.2, 2.1, 1.3, 0.4, 0.3, 0.2))
        check_positions(out[6:], (1.3, 2.2, 1.2, 0.1, 0.2, 0.3))


def check_positions(out, expected, rel=0.0001, abs=0.0001):
    assert len(out) == len(expected)

    for idx, element in enumerate(out):
        assert element == approx(expected[idx], rel=rel, abs=abs)
