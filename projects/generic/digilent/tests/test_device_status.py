"""Tests for the device section of the DT8874 control server status report.

The objects are created without calling `__init__` where the constructor needs device settings or would bind sockets
and register to the service registry.
"""

from types import SimpleNamespace

from egse.digilent.digilent import DigilentController, DigilentSimulator
from egse.digilent.measurpoint.digilent_devif import DigilentEthernetInterface
from egse.digilent.measurpoint.dt8874.dt8874 import Dt8874Simulator
from egse.digilent.measurpoint.dt8874.dt8874_cs import Dt8874ControlServer


def test_ethernet_interface_connection_open():
    transport = DigilentEthernetInterface.__new__(DigilentEthernetInterface)

    transport._is_connection_open = False
    assert transport.is_connection_open() is False

    transport._is_connection_open = True
    assert transport.is_connection_open() is True


def test_controller_connection_open_does_not_query_the_device():
    def no_query():
        raise AssertionError("is_connected() queries the device and shall not be used")

    controller = DigilentController.__new__(DigilentController)
    controller.transport = SimpleNamespace(is_connection_open=lambda: True, is_connected=no_query)

    assert controller.is_connection_open() is True


def test_simulators_connection_open():
    for simulator in (DigilentSimulator(), Dt8874Simulator()):
        simulator.disconnect()
        assert simulator.is_connection_open() is False

        simulator.connect()
        assert simulator.is_connection_open() is True


def test_control_server_device_status():
    def make_server(connection_open: bool, simulator: bool):
        dt8874 = SimpleNamespace(is_connection_open=lambda: connection_open)
        return SimpleNamespace(device_protocol=SimpleNamespace(dt8874=dt8874, simulator=simulator))

    status = Dt8874ControlServer.get_device_status(make_server(connection_open=True, simulator=False))
    assert status == {"connected": True, "sim_mode": False}

    status = Dt8874ControlServer.get_device_status(make_server(connection_open=False, simulator=True))
    assert status == {"connected": False, "sim_mode": True}
