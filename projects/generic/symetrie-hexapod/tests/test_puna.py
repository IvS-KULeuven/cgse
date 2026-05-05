from functools import lru_cache

import numpy as np
import pytest
from pytest import approx

from egse.hexapod.symetrie.hexapod import HexapodSimulator
from egse.hexapod.symetrie.puna import PunaProxy
from egse.hexapod.symetrie.puna import PunaSimulator
from egse.hexapod.symetrie.zonda import ZondaProxy, ZondaSimulator
from egse.hexapod.symetrie.joran import JoranProxy, JoranSimulator
from egse.system import wait_until


HEXAPODS = [
    ("PUNA", "PUNA_01"),
    ("ZONDA", "ZONDA_01"),
    ("JORAN", "JORAN_01"),
]

BACKENDS = ["simulator", "proxy"]


# When the 'real' Hexapod controller is connected, the pytest can be run with the
# Hexapod class. However, by default we use the HexapodSimulator class for testing.


@pytest.fixture
@lru_cache
def hexapod(request):
    device, device_id = request.param

    def get_simulator():
        if device == "PUNA":
            return PunaSimulator(device_id)
        elif device == "ZONDA":
            return ZondaSimulator(device_id)
        elif device == "JORAN":
            return JoranSimulator(device_id)

    def get_proxy():
        if device == "PUNA":
            return PunaProxy(device_id)
        elif device == "ZONDA":
            return ZondaProxy(device_id)
        elif device == "JORAN":
            return JoranProxy(device_id)

    return get_simulator(), get_proxy()


def get_device(hexapod, backend):
    sim, dev = hexapod
    if backend == "simulator":
        return sim
    if backend == "proxy":
        return dev
    raise ValueError(f"Unknown backend: {backend}")


def skip_unavailable_proxy(exc: ConnectionError):
    pytest.skip(f"Control server not available — skipping proxy backend: {exc}")


@pytest.mark.parametrize(
    "hexapod",
    HEXAPODS,
    indirect=True,
)
def test_context_manager_proxy_no_control_server(hexapod):
    print()

    dev = get_device(hexapod, "proxy")

    with pytest.raises(ConnectionError) as exc_info:
        with dev:
            print(dev.info())
    assert str(exc_info.value) == f"No control server registered as '{dev._device_id}'."


@pytest.mark.parametrize(
    "hexapod",
    HEXAPODS,
    indirect=True,
)
def test_context_manager_simulator(hexapod):
    print()

    sim = get_device(hexapod, "simulator")

    with sim:
        print(sim.info())


@pytest.mark.parametrize(
    "hexapod",
    HEXAPODS,
    indirect=True,
)
@pytest.mark.parametrize("backend", BACKENDS)
def test_connection_and_homing(hexapod, backend):
    dev = get_device(hexapod, backend)

    try:
        with dev:
            dev.info()

            # FIXME: The controller might be in a bad state due to previous failures.
            #        We need some way to fix & reset the controller at the beginning of the unit tests.

            dev.clear_error()

            if dev.is_simulator():
                dev.reset(wait=False, verbose=False)  # Wait is not needed
            else:
                dev.reset(wait=True, verbose=False)  # Wait is definitely needed

            dev.homing()

            if wait_until(dev.is_homing_done, interval=0.5, timeout=300):
                assert False
            if wait_until(dev.is_in_position, interval=0.5, timeout=300):
                assert False

            assert dev.is_homing_done()
            assert dev.is_in_position()
    except ConnectionError as exc:
        assert not isinstance(dev, HexapodSimulator), (
            f"ConnectionError should only occur for proxies, but got for {type(dev).__name__}: {exc}"
        )
        skip_unavailable_proxy(exc)


@pytest.mark.parametrize(
    "hexapod",
    HEXAPODS,
    indirect=True,
)
def test_hexapod_connect_and_ping(hexapod):
    def check_connect_hexapod(device):
        device.connect_cs()
        assert not device.ping()
        device.disconnect_cs()

    dev = get_device(hexapod, "proxy")

    try:
        check_connect_hexapod(dev)
    except ConnectionError as exc:
        skip_unavailable_proxy(exc)


@pytest.mark.parametrize(
    "hexapod",
    HEXAPODS,
    indirect=True,
)
@pytest.mark.parametrize("backend", BACKENDS)
def test_goto_position(hexapod, backend):
    dev = get_device(hexapod, backend)

    try:
        with dev:
            rc = dev.goto_specific_position(1)
            assert rc in [0, -1, -2]  # FIXME: How can we do proper checking here?

            rc = dev.goto_specific_position(5)
            assert rc in [0, -1, -2]  # FIXME: How can we do proper checking here?
    except ConnectionError as exc:
        assert backend == "proxy"
        skip_unavailable_proxy(exc)


@pytest.mark.parametrize(
    "hexapod",
    HEXAPODS,
    indirect=True,
)
@pytest.mark.parametrize("backend", BACKENDS)
def test_absolute_movement(hexapod, backend):
    dev = get_device(hexapod, backend)

    try:
        with dev:
            tx_u, ty_u, tz_u = 0, 0, 0
            rx_u, ry_u, rz_u = 0, 0, 0
            tx_o, ty_o, tz_o = 0, 0, 0
            rx_o, ry_o, rz_o = 0, 0, 0

            dev.configure_coordinates_systems(tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o)
            dev.homing()

            if wait_until(dev.is_homing_done, interval=0.5, timeout=300):
                assert False
            if wait_until(dev.is_in_position, interval=1, timeout=300):
                assert False

            tx_u, ty_u, tz_u = -2, -2, -2
            rx_u, ry_u, rz_u = -3, -4, -5

            tx_o, ty_o, tz_o = 0, 0, 3
            rx_o, ry_o, rz_o = np.rad2deg(np.pi / 6.0), np.rad2deg(np.pi / 6.0), 0

            dev.configure_coordinates_systems(tx_u, ty_u, tz_u, rx_u, ry_u, rz_u, tx_o, ty_o, tz_o, rx_o, ry_o, rz_o)

            out = dev.get_user_positions()
            check_positions(out, (2.162431533, 1.9093265385, 4.967732082, 34.01008683, 33.65884585, 7.22137656))

            out = dev.get_machine_positions()
            check_positions(out, (0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000))

            tx, ty, tz = [1, 3, 4]
            rx, ry, rz = [35, 25, 10]

            rc = dev.move_absolute(tx, ty, tz, rx, ry, rz)
            assert rc == 0

            if wait_until(dev.is_in_position, interval=1, timeout=300):
                assert False

            out = dev.get_user_positions()
            check_positions(out, (1.00000, 3.00000, 4.00000, 35.00000, 25.00000, 10.00000))

            out = dev.get_machine_positions()
            check_positions(out, (-0.5550577685, 1.2043056694, -1.0689145898, 1.0195290202, -8.466485292, 2.79932335))

            # Test the move relative object

            tx, ty, tz = -1, -1, -1
            rx, ry, rz = 1, 7, -1

            dev.move_relative_object(tx, ty, tz, rx, ry, rz)

            if wait_until(dev.is_in_position, interval=1, timeout=300):
                assert False

            out = dev.get_user_positions()
            check_positions(out, (-0.4295447122, 2.49856887, 3.160383195, 37.82597474, 31.25750377, 13.736721917))

            out = dev.get_machine_positions()
            check_positions(out, (-2.317005597, 0.8737649564, -2.006061295, 3.052233715, -1.9466592653, 4.741402017))

            # Test the move relative user

            tx, ty, tz = -2, -2, -2
            rx, ry, rz = 1, 7, -1

            dev.move_relative_user(tx, ty, tz, rx, ry, rz)

            if wait_until(dev.is_in_position, interval=1, timeout=300):
                assert False

            out = dev.get_user_positions()
            check_positions(out, (-2.429542106, 0.4985648, 1.1603886537, 41.37225134, 37.32309944, 18.14008525))

            out = dev.get_machine_positions()
            check_positions(out, (-4.710341626, -0.97799175, -4.017462423, 5.310002306, 4.496313461, 6.918574645))

    except ConnectionError as exc:
        assert backend == "proxy"
        skip_unavailable_proxy(exc)


@pytest.mark.parametrize(
    "hexapod",
    HEXAPODS,
    indirect=True,
)
@pytest.mark.parametrize("backend", BACKENDS)
def test_coordinates_systems(hexapod, backend):
    dev = get_device(hexapod, backend)

    try:
        with dev:
            rc = dev.configure_coordinates_systems(1.2, 2.1, 1.3, 0.4, 0.3, 0.2, 1.3, 2.2, 1.2, 0.1, 0.2, 0.3)

            assert rc >= 0

            out = dev.get_coordinates_systems()

            check_positions(out[:6], (1.2, 2.1, 1.3, 0.4, 0.3, 0.2))
            check_positions(out[6:], (1.3, 2.2, 1.2, 0.1, 0.2, 0.3))

    except ConnectionError as exc:
        assert backend == "proxy"
        skip_unavailable_proxy(exc)


def check_positions(out, expected, rel=0.0001, abs=0.0001):
    assert len(out) == len(expected)

    for idx, element in enumerate(out):
        assert element == approx(expected[idx], rel=rel, abs=abs)
