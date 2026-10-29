"""Tests for the device section of the RS-D3305P control server status report.

The objects are created without calling `__init__` where the constructor needs the hardware (serial port lookup by
serial number), or would bind sockets and register to the service registry.
"""

from types import SimpleNamespace

from egse.power_supply.rs_pro.rsd3305p import Rsd3305pController, Rsd3305pSimulator
from egse.power_supply.rs_pro.rsd3305p_cs import Rsd3305pControlServer
from egse.power_supply.rs_pro.rsd3305p_devif import Rsd3305pUsbInterface


def test_usb_interface_connection_open():
    transport = Rsd3305pUsbInterface.__new__(Rsd3305pUsbInterface)

    transport.psu = SimpleNamespace(is_open=False)
    assert transport.is_connection_open() is False

    transport.psu = SimpleNamespace(is_open=True)
    assert transport.is_connection_open() is True


def test_controller_connection_open_does_not_query_the_device():
    def no_query():
        raise AssertionError("is_connected() queries the device and shall not be used")

    controller = Rsd3305pController.__new__(Rsd3305pController)
    controller.transport = SimpleNamespace(is_connection_open=lambda: True, is_connected=no_query)

    assert controller.is_connection_open() is True


def test_simulator_connection_open():
    assert Rsd3305pSimulator("RSD1").is_connection_open() is True


def test_control_server_device_status():
    def make_server(connection_open: bool, simulator: bool):
        rsd3305p = SimpleNamespace(is_connection_open=lambda: connection_open)
        return SimpleNamespace(device_protocol=SimpleNamespace(rsd3305p=rsd3305p, simulator=simulator))

    status = Rsd3305pControlServer.get_device_status(make_server(connection_open=True, simulator=False))
    assert status == {"connected": True, "sim_mode": False}

    status = Rsd3305pControlServer.get_device_status(make_server(connection_open=False, simulator=True))
    assert status == {"connected": False, "sim_mode": True}
