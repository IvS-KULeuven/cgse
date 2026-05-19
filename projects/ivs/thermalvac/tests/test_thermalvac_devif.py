"""Unit tests for ThermalVacOpcUaInterface."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncua import Client, ua

from egse.device import DeviceConnectionError
from egse.ivs.thermalvac.thermalvac_devif import ThermalVacOpcUaInterface


@pytest.fixture
def default_hostname():
    return "localhost"


@pytest.fixture
def default_port():
    return 4840


@pytest.fixture
def mock_client():
    client = MagicMock(spec=Client)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.get_root_node = MagicMock()
    client.get_node = MagicMock()
    return client


@pytest.fixture
def thermalvac_interface(default_hostname, default_port, mock_client):
    """Create ThermalVacOpcUaInterface instance with mocked client."""
    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        interface = ThermalVacOpcUaInterface(hostname=default_hostname, port=default_port)
    return interface


@pytest.mark.asyncio
async def test_successful_connection(thermalvac_interface, mock_client):
    """Test successful connection to device."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    await thermalvac_interface.connect()

    assert thermalvac_interface._is_connection_open is True
    mock_client.connect.assert_called_once()


@pytest.mark.asyncio
async def test_connection_raises_error_when_hostname_missing(default_port, mock_client):
    """Test connection fails when hostname is not initialized."""
    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        interface = ThermalVacOpcUaInterface(hostname=None, port=default_port)
        interface.hostname = None

    with pytest.raises(ValueError, match="hostname is not initialised"):
        await interface.connect()

    assert interface._is_connection_open is False


@pytest.mark.asyncio
async def test_connection_raises_error_when_port_missing(default_hostname, mock_client):
    """Test connection fails when port is not initialized."""
    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        interface = ThermalVacOpcUaInterface(hostname=default_hostname, port=None)
        interface.port = None

    with pytest.raises(ValueError, match="port number is not initialised"):
        await interface.connect()

    assert interface._is_connection_open is False


@pytest.mark.asyncio
async def test_connection_raises_error_when_device_unresponsive(thermalvac_interface, mock_client):
    """Test connection raises error when device is not responsive."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock(side_effect=Exception("Connection failed"))
    mock_client.get_root_node.return_value = mock_root

    with pytest.raises(DeviceConnectionError, match="Device is not connected"):
        await thermalvac_interface.connect()

    assert thermalvac_interface._is_connection_open is False


@pytest.mark.asyncio
async def test_connection_warning_when_already_connected(thermalvac_interface, mock_client, caplog):
    """Test connection logs warning when already connected."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    await thermalvac_interface.connect()
    mock_client.reset_mock()
    await thermalvac_interface.connect()

    assert "already connected" in caplog.text
    mock_client.connect.assert_not_called()


@pytest.mark.asyncio
async def test_successful_disconnection(thermalvac_interface, mock_client):
    """Test successful disconnection from device."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    await thermalvac_interface.connect()
    assert thermalvac_interface._is_connection_open is True

    await thermalvac_interface.disconnect()

    assert thermalvac_interface._is_connection_open is False
    mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_disconnection_when_not_connected(thermalvac_interface, mock_client):
    """Test disconnection when device is not connected."""
    await thermalvac_interface.disconnect()

    assert thermalvac_interface._is_connection_open is False
    mock_client.disconnect.assert_not_called()


@pytest.mark.asyncio
async def test_reconnection_sequence(thermalvac_interface, mock_client):
    """Test full reconnection sequence."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    await thermalvac_interface.connect()
    assert thermalvac_interface._is_connection_open is True
    assert mock_client.connect.call_count == 1

    await thermalvac_interface.reconnect()

    assert thermalvac_interface._is_connection_open is True
    assert mock_client.disconnect.call_count == 1
    assert mock_client.connect.call_count == 2


@pytest.mark.asyncio
async def test_reconnection_when_not_connected(thermalvac_interface, mock_client):
    """Test reconnection when device is not already connected."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    await thermalvac_interface.reconnect()

    assert thermalvac_interface._is_connection_open is True
    mock_client.disconnect.assert_not_called()
    mock_client.connect.assert_called_once()


@pytest.mark.asyncio
async def test_is_connected_returns_true_when_responsive(thermalvac_interface, mock_client):
    """Test is_connected returns True when device is responsive."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    await thermalvac_interface.connect()

    result = await thermalvac_interface.is_connected()

    assert result is True


@pytest.mark.asyncio
async def test_is_connected_returns_false_when_connection_not_open(
    thermalvac_interface,
):
    """Test is_connected returns False when connection flag is False."""
    result = await thermalvac_interface.is_connected()

    assert result is False


@pytest.mark.asyncio
async def test_is_connected_returns_false_when_device_not_responsive(thermalvac_interface, mock_client):
    """Test is_connected returns False when device is not responsive."""
    thermalvac_interface._is_connection_open = True
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock(side_effect=Exception("Device error"))
    mock_client.get_root_node.return_value = mock_root

    result = await thermalvac_interface.is_connected()

    assert result is False


@pytest.mark.asyncio
async def test_read_node_returns_value(thermalvac_interface, mock_client):
    """Test reading value from a node."""
    mock_variable = AsyncMock()
    mock_variable.read_value = AsyncMock(return_value=42)
    mock_client.get_node.return_value = mock_variable

    result = await thermalvac_interface.read_node("ns=2;i=1234")

    assert result == 42
    mock_client.get_node.assert_called_once_with("ns=2;i=1234")
    mock_variable.read_value.assert_called_once()


@pytest.mark.asyncio
async def test_read_node_with_string_value(thermalvac_interface, mock_client):
    """Test reading string value from a node."""
    test_value = "temperature_sensor"
    mock_variable = AsyncMock()
    mock_variable.read_value = AsyncMock(return_value=test_value)
    mock_client.get_node.return_value = mock_variable

    result = await thermalvac_interface.read_node("ns=2;s=sensor_name")

    assert result == test_value


@pytest.mark.asyncio
async def test_write_node_sets_value(thermalvac_interface, mock_client):
    """Test writing value to a node."""
    mock_variable = AsyncMock()
    mock_variable.set_value = AsyncMock()
    mock_client.get_node.return_value = mock_variable

    with patch("egse.ivs.thermalvac.thermalvac_devif.ua") as mock_ua:
        mock_ua.DataValue = MagicMock()
        mock_ua.Variant = MagicMock()

        await thermalvac_interface.write_node("ns=2;i=1234", 100.5, ua.VariantType.Double)

        mock_variable.set_value.assert_called_once()
        mock_client.get_node.assert_called_once_with("ns=2;i=1234")


@pytest.mark.asyncio
async def test_write_node_with_integer_value(thermalvac_interface, mock_client):
    """Test writing integer value to a node."""
    mock_variable = AsyncMock()
    mock_variable.set_value = AsyncMock()
    mock_client.get_node.return_value = mock_variable

    with patch("egse.ivs.thermalvac.thermalvac_devif.ua") as mock_ua:
        mock_ua.DataValue = MagicMock()
        mock_ua.Variant = MagicMock()

        await thermalvac_interface.write_node("ns=2;i=5678", 42, ua.VariantType.Int32)

        mock_variable.set_value.assert_called_once()


@pytest.mark.asyncio
async def test_server_url_property_format(thermalvac_interface):
    """Test server_url property returns correct OPC UA URL format."""
    expected_url = f"opc.tcp://{thermalvac_interface.hostname}:{thermalvac_interface.port}"

    assert thermalvac_interface.server_url == expected_url


@pytest.mark.asyncio
async def test_server_url_with_custom_hostname_and_port(mock_client):
    """Test server_url with custom hostname and port."""
    custom_hostname = "192.168.1.100"
    custom_port = 4841

    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        interface = ThermalVacOpcUaInterface(hostname=custom_hostname, port=custom_port)

    expected_url = f"opc.tcp://{custom_hostname}:{custom_port}"
    assert interface.server_url == expected_url


@pytest.mark.asyncio
async def test_context_manager_establishes_connection(default_hostname, default_port, mock_client):
    """Test async context manager establishes connection."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        async with ThermalVacOpcUaInterface(hostname=default_hostname, port=default_port) as interface:
            assert interface._is_connection_open is True


@pytest.mark.asyncio
async def test_context_manager_closes_connection(default_hostname, default_port, mock_client):
    """Test async context manager closes connection on exit."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        async with ThermalVacOpcUaInterface(hostname=default_hostname, port=default_port) as interface:
            pass

        assert interface._is_connection_open is False
        mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager_closes_on_exception(default_hostname, default_port, mock_client):
    """Test async context manager closes connection even on exception."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        try:
            async with ThermalVacOpcUaInterface(hostname=default_hostname, port=default_port) as interface:
                raise RuntimeError("Test exception")
        except RuntimeError:
            pass

        assert interface._is_connection_open is False
        mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_operations_with_lock(thermalvac_interface, mock_client):
    """Test that lock prevents concurrent operations on same node."""
    mock_variable = AsyncMock()
    mock_variable.read_value = AsyncMock(return_value=100)
    mock_client.get_node.return_value = mock_variable

    results = await asyncio.gather(
        thermalvac_interface.read_node("ns=2;i=1"),
        thermalvac_interface.read_node("ns=2;i=2"),
    )

    assert results[0] == 100
    assert results[1] == 100
    assert mock_variable.read_value.call_count == 2


@pytest.mark.asyncio
async def test_device_id_is_set_correctly(default_hostname, default_port, mock_client):
    """Test that device_id is set correctly during initialization."""
    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        interface = ThermalVacOpcUaInterface(hostname=default_hostname, port=default_port)

    assert interface.device_id == "ThermalVac"


@pytest.mark.asyncio
async def test_initialization_uses_provided_hostname_and_port(mock_client):
    """Test that initialization uses provided hostname and port."""
    custom_hostname = "custom.host.com"
    custom_port = 9999

    with patch("egse.ivs.thermalvac.thermalvac_devif.Client", return_value=mock_client):
        interface = ThermalVacOpcUaInterface(hostname=custom_hostname, port=custom_port)

    assert interface.hostname == custom_hostname
    assert interface.port == custom_port


@pytest.mark.asyncio
async def test_read_and_write_operations_sequence(thermalvac_interface, mock_client):
    """Test a sequence of read and write operations."""
    mock_root = MagicMock()
    mock_root.read_browse_name = AsyncMock()
    mock_client.get_root_node.return_value = mock_root

    read_variable = AsyncMock()
    read_variable.read_value = AsyncMock(return_value=25.5)

    write_variable = AsyncMock()
    write_variable.set_value = AsyncMock()

    mock_client.get_node.side_effect = [read_variable, write_variable]

    await thermalvac_interface.connect()

    with patch("egse.ivs.thermalvac.thermalvac_devif.ua") as mock_ua:
        mock_ua.DataValue = MagicMock()
        mock_ua.Variant = MagicMock()

        read_result = await thermalvac_interface.read_node("ns=2;i=100")
        await thermalvac_interface.write_node("ns=2;i=101", 30.0, ua.VariantType.Double)

    assert read_result == 25.5
    assert read_variable.read_value.called
    assert write_variable.set_value.called
