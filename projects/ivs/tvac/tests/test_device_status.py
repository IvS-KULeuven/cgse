"""Tests for the device section of the ThermalVac control server status report."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncua import Client

from egse.ivs.tvac.tvac_acs import ThermalVacControlServer, ThermalVacDaq
from egse.ivs.tvac.tvac_devif import ThermalVacOpcUaInterface


@pytest.fixture
def interface():
    client = MagicMock(spec=Client)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get_root_node = MagicMock()
    client.get_root_node.return_value.read_browse_name = AsyncMock()
    with patch("egse.ivs.tvac.tvac_devif.Client", return_value=client):
        yield ThermalVacOpcUaInterface(hostname="localhost", port=4840)


@pytest.mark.asyncio
async def test_interface_connection_open_does_not_query_the_device(interface):
    assert interface.is_connection_open is False

    await interface.connect()
    interface.client.get_root_node.reset_mock()

    assert interface.is_connection_open is True
    interface.client.get_root_node.assert_not_called()

    await interface.disconnect()
    assert interface.is_connection_open is False


def test_daq_connection_open():
    daq = ThermalVacDaq.__new__(ThermalVacDaq)

    daq.opcua_interface = SimpleNamespace(is_connection_open=True)
    assert daq.is_connection_open is True

    daq.opcua_interface = SimpleNamespace(is_connection_open=False)
    assert daq.is_connection_open is False


def test_control_server_device_status():
    def make_server(connection_open: bool):
        return SimpleNamespace(controller=SimpleNamespace(daq=SimpleNamespace(is_connection_open=connection_open)))

    # Called on a stand-in, so no control server is started or registered.
    assert ThermalVacControlServer.get_device_status(make_server(True)) == {"connected": True, "sim_mode": None}
    assert ThermalVacControlServer.get_device_status(make_server(False)) == {"connected": False, "sim_mode": None}
