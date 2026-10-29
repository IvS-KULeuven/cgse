"""Tests for the device section of the LakeShore336 control server status report.

The objects are created without calling `__init__` where the constructor needs device settings, or would bind sockets
and register to the service registry.
"""

from types import SimpleNamespace

from egse.tempcontrol.lakeshore.lakeshore336 import LakeShore336Controller, LakeShore336Simulator
from egse.tempcontrol.lakeshore.lakeshore336_cs import LakeShore336ControlServer
from egse.tempcontrol.lakeshore.lakeshore336_devif import LakeShore336EthernetInterface


def test_ethernet_interface_connection_open():
    transport = LakeShore336EthernetInterface.__new__(LakeShore336EthernetInterface)

    transport._is_connection_open = False
    assert transport.is_connection_open() is False

    transport._is_connection_open = True
    assert transport.is_connection_open() is True


def test_controller_connection_open_does_not_query_the_device():
    def no_query():
        raise AssertionError("is_connected() queries the device and shall not be used")

    controller = LakeShore336Controller.__new__(LakeShore336Controller)
    controller.lakeshore = SimpleNamespace(is_connection_open=lambda: True, is_connected=no_query)

    assert controller.is_connection_open() is True


def test_simulator_connection_open():
    simulator = LakeShore336Simulator.__new__(LakeShore336Simulator)

    simulator.disconnect()
    assert simulator.is_connection_open() is False

    simulator.connect()
    assert simulator.is_connection_open() is True


def test_control_server_device_status():
    def make_server(connection_open: bool, simulator: bool):
        lakeshore = SimpleNamespace(is_connection_open=lambda: connection_open)
        return SimpleNamespace(device_protocol=SimpleNamespace(lakeshore=lakeshore, simulator=simulator))

    status = LakeShore336ControlServer.get_device_status(make_server(connection_open=True, simulator=False))
    assert status == {"connected": True, "sim_mode": False}

    status = LakeShore336ControlServer.get_device_status(make_server(connection_open=False, simulator=True))
    assert status == {"connected": False, "sim_mode": True}
