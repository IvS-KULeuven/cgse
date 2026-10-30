"""Tests for the device section of the TCU control server status report.

The objects are created without calling `__init__` where the constructor would open the serial port, or would bind
sockets and register to the service registry.
"""

from types import SimpleNamespace

from egse.ariel.tcu.tcu import TcuController, TcuSimulator
from egse.ariel.tcu.tcu_cs import TcuControlServer
from egse.ariel.tcu.tcu_devif import TcuDeviceInterface


def test_device_interface_is_connected_only_checks_the_serial_port():
    transport = TcuDeviceInterface.__new__(TcuDeviceInterface)

    transport.arduino = SimpleNamespace(is_open=False)
    assert transport.is_connected() is False

    transport.arduino = SimpleNamespace(is_open=True)
    assert transport.is_connected() is True


def test_controller_is_connected():
    controller = TcuController.__new__(TcuController)
    controller.tcu = SimpleNamespace(is_connected=lambda: True)

    assert controller.is_connected() is True


def test_simulator_is_connected():
    simulator = TcuSimulator()

    simulator.disconnect()
    assert simulator.is_connected() is False

    simulator.connect()
    assert simulator.is_connected() is True


def test_control_server_device_status():
    def make_server(connected: bool, simulator: bool):
        tcu = SimpleNamespace(is_connected=lambda: connected)
        return SimpleNamespace(device_protocol=SimpleNamespace(tcu=tcu, simulator=simulator))

    status = TcuControlServer.get_device_status(make_server(connected=True, simulator=False))
    assert status == {"connected": True, "sim_mode": False}

    status = TcuControlServer.get_device_status(make_server(connected=False, simulator=True))
    assert status == {"connected": False, "sim_mode": True}
