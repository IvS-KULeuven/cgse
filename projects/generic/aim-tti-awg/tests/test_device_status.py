"""Tests for the device section of the TGF4000 control server status report.

The objects are created without calling `__init__`, because the constructors need device settings (hostname, port)
and the control server binds sockets and registers to the service registry.
"""

from types import SimpleNamespace

from egse.arbitrary_wave_generator.aim_tti.tgf4000 import Tgf4000Controller, Tgf4000Simulator
from egse.arbitrary_wave_generator.aim_tti.tgf4000_cs import Tgf4000ControlServer
from egse.arbitrary_wave_generator.aim_tti.tgf4000_devif import Tgf4000EthernetInterface


def test_ethernet_interface_connection_open():
    transport = Tgf4000EthernetInterface.__new__(Tgf4000EthernetInterface)

    transport._is_connection_open = False
    assert transport.is_connection_open() is False

    transport._is_connection_open = True
    assert transport.is_connection_open() is True


def test_controller_connection_open_does_not_query_the_device():
    def no_query():
        raise AssertionError("is_connected() queries the device and shall not be used")

    controller = Tgf4000Controller.__new__(Tgf4000Controller)
    controller.transport = SimpleNamespace(is_connection_open=lambda: True, is_connected=no_query)

    assert controller.is_connection_open() is True


def test_simulator_connection_open():
    simulator = Tgf4000Simulator.__new__(Tgf4000Simulator)

    simulator.disconnect()
    assert simulator.is_connection_open() is False

    simulator.connect()
    assert simulator.is_connection_open() is True


def test_control_server_device_status():
    def make_server(connection_open: bool, simulator: bool):
        tgf4000 = SimpleNamespace(is_connection_open=lambda: connection_open)
        return SimpleNamespace(device_protocol=SimpleNamespace(tgf4000=tgf4000, simulator=simulator))

    status = Tgf4000ControlServer.get_device_status(make_server(connection_open=True, simulator=False))
    assert status == {"connected": True, "sim_mode": False}

    status = Tgf4000ControlServer.get_device_status(make_server(connection_open=False, simulator=True))
    assert status == {"connected": False, "sim_mode": True}
