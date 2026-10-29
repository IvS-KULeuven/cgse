"""Tests for the device section of the PMX-A control server status report.

The objects are created without calling `__init__`, because the constructors need device settings (hostname, port)
and the control server binds sockets and registers to the service registry.
"""

from types import SimpleNamespace

from egse.power_supply.kikusui.pmx_a.pmx_a import PmxAController, PmxASimulator
from egse.power_supply.kikusui.pmx_a.pmx_a_cs import PmxAControlServer
from egse.power_supply.kikusui.pmx_devif import PmxEthernetInterface


def test_ethernet_interface_connection_open():
    transport = PmxEthernetInterface.__new__(PmxEthernetInterface)

    transport._is_connection_open = False
    assert transport.is_connection_open() is False

    transport._is_connection_open = True
    assert transport.is_connection_open() is True


def test_controller_connection_open_does_not_query_the_device():
    def no_query():
        raise AssertionError("is_connected() queries the device and shall not be used")

    controller = PmxAController.__new__(PmxAController)
    controller.transport = SimpleNamespace(is_connection_open=lambda: True, is_connected=no_query)

    assert controller.is_connection_open() is True


def test_simulator_connection_open():
    simulator = PmxASimulator.__new__(PmxASimulator)

    simulator.disconnect()
    assert simulator.is_connection_open() is False

    simulator.connect()
    assert simulator.is_connection_open() is True


def test_control_server_device_status():
    def make_server(connection_open: bool, simulator: bool):
        pmx_a = SimpleNamespace(is_connection_open=lambda: connection_open)
        return SimpleNamespace(device_protocol=SimpleNamespace(pmx_a=pmx_a, simulator=simulator))

    status = PmxAControlServer.get_device_status(make_server(connection_open=True, simulator=False))
    assert status == {"connected": True, "sim_mode": False}

    status = PmxAControlServer.get_device_status(make_server(connection_open=False, simulator=True))
    assert status == {"connected": False, "sim_mode": True}


def test_simulator_current_and_voltage():
    simulator = PmxASimulator("PMX-A1")

    assert simulator.get_current() == 0.0
    assert simulator.get_voltage() == 0.0

    simulator.set_current(1.5)
    simulator.set_voltage(12.0)

    assert simulator.get_current() == 1.5
    assert simulator.get_voltage() == 12.0
