"""Tests for the device section of the PUNA, ZONDA, and JORAN control server status reports.

The objects are created without calling `__init__` where the constructor needs device settings or the hardware, or
would bind sockets and register to the service registry.
"""

from types import SimpleNamespace

from egse.hexapod.symetrie.dynalpha import AlphaPlusTelnetInterface
from egse.hexapod.symetrie.hexapod import HexapodSimulator
from egse.hexapod.symetrie.joran_cs import JoranControlServer
from egse.hexapod.symetrie.puna import PunaController
from egse.hexapod.symetrie.puna_cs import PunaControlServer
from egse.hexapod.symetrie.punaplus import PunaPlusController
from egse.hexapod.symetrie.zonda_cs import ZondaControlServer
from egse.hexapod.symetrie.zonda_devif import ZondaTelnetInterface


def no_query():
    raise AssertionError("this method queries the device and shall not be used")


def test_puna_pmac_controller_connection_open_does_not_query_the_device():
    controller = PunaController.__new__(PunaController)
    controller.pmac = SimpleNamespace(isConnectionOpen=True, isConnected=no_query)

    assert controller.is_connection_open() is True

    controller.pmac.isConnectionOpen = False
    assert controller.is_connection_open() is False


def test_puna_plus_controller_connection_open():
    telnet = AlphaPlusTelnetInterface.__new__(AlphaPlusTelnetInterface)
    controller = PunaPlusController.__new__(PunaPlusController)
    controller.device = telnet

    telnet._is_connected = False
    assert controller.is_connection_open() is False

    telnet._is_connected = True
    assert controller.is_connection_open() is True


def test_telnet_interfaces_is_connected_is_a_flag():
    for interface_class in (AlphaPlusTelnetInterface, ZondaTelnetInterface):
        interface = interface_class.__new__(interface_class)
        interface.telnet = SimpleNamespace(write=no_query, read_until=no_query, read_very_eager=no_query)

        interface._is_connected = False
        assert interface.is_connected() is False

        interface._is_connected = True
        assert interface.is_connected() is True


def test_simulator_connection_open():
    simulator = HexapodSimulator.__new__(HexapodSimulator)

    assert simulator.is_connected() is True
    assert simulator.is_connection_open() is True


def make_server(simulator: bool, connected: bool):
    hexapod = SimpleNamespace(is_connection_open=lambda: connected, is_connected=lambda: connected)
    return SimpleNamespace(device_protocol=SimpleNamespace(hexapod=hexapod, simulator=simulator))


def test_control_servers_device_status():
    for control_server_class in (PunaControlServer, ZondaControlServer, JoranControlServer):
        status = control_server_class.get_device_status(make_server(simulator=False, connected=True))
        assert status == {"connected": True, "sim_mode": False}

        status = control_server_class.get_device_status(make_server(simulator=True, connected=False))
        assert status == {"connected": False, "sim_mode": True}
