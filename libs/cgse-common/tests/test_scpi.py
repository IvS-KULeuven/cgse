import asyncio
import contextlib

import pytest

from egse.device import DeviceConnectionError
from egse.scpi import AsyncSCPIInterface
from egse.scpi import count_number_of_channels
from egse.scpi import create_channel_list
from egse.scpi import get_channel_names


def test_get_channel_names():
    assert get_channel_names("1") == []
    assert get_channel_names("(@101)") == ["101"]
    assert get_channel_names("(@101,102,103)") == ["101", "102", "103"]
    assert get_channel_names("(@101:105)") == ["101", "102", "103", "104", "105"]
    assert get_channel_names("(@101, 102, 103, 105)") == ["101", "102", "103", "105"]
    assert get_channel_names("(@201:204,205,206,207:209,211)") == [
        "201",
        "202",
        "203",
        "204",
        "205",
        "206",
        "207",
        "208",
        "209",
        "211",
    ]


def test_get_channel_names_invalid():
    assert get_channel_names("") == []
    assert get_channel_names("101") == []
    assert get_channel_names("(@)") == []
    assert get_channel_names("(@101,,103)") == []
    assert get_channel_names("(@101:abc)") == []
    assert get_channel_names("(@101:102:103)") == []
    assert get_channel_names("(@101-105)") == []
    assert get_channel_names("(@10a)") == []
    assert get_channel_names("(@101, 10b)") == []
    assert get_channel_names("(@101:10c)") == []


def test_count_number_of_channels():
    assert count_number_of_channels("(@101)") == 1
    assert count_number_of_channels("(@101,102,103)") == 3
    assert count_number_of_channels("(@101:105)") == 5
    assert count_number_of_channels("(@101, 102, 103, 105)") == 4
    assert count_number_of_channels("(@201:204,205,206,207:209,211)") == 10
    assert count_number_of_channels("") == 0
    assert count_number_of_channels("101") == 0
    assert count_number_of_channels("(@)") == 0
    assert count_number_of_channels("(@101,,103)") == 0
    assert count_number_of_channels("(@101:abc)") == 0
    assert count_number_of_channels("(@101:102:103)") == 0
    assert count_number_of_channels("(@101-105)") == 0
    assert count_number_of_channels("(@10a)") == 0
    assert count_number_of_channels("(@101, 10b)") == 0
    assert count_number_of_channels("(@101:10c)") == 0


def test_create_channel_list():
    assert create_channel_list() == ""
    assert create_channel_list("101") == "(@101)"
    assert create_channel_list(["101"]) == "(@101)"
    assert create_channel_list(["101", "104"]) == "(@101:104)"
    assert create_channel_list("101", "102", "103") == "(@101,102,103)"
    assert create_channel_list("101", "102", "103", "104", "105") == "(@101,102,103,104,105)"
    assert create_channel_list("101", "102", "103", "105") == "(@101,102,103,105)"
    assert create_channel_list(["201", "204"], "205", "206", ["207", "209"], "211") == "(@201:204,205,206,207:209,211)"


@pytest.mark.asyncio
async def test_disconnect_after_the_device_closed_the_connection():
    """A device that restarts closes the connection on its side, a reconnect must be possible afterwards."""

    connections = []
    handlers = []

    async def handle(reader, writer):
        connections.append(writer)
        handlers.append(asyncio.current_task())
        while await reader.readline():
            writer.write(b"ACME,MODEL 1,SN,1.0\n")
            await writer.drain()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    device = AsyncSCPIInterface("ACME", hostname="127.0.0.1", port=port, read_timeout=1.0)
    await device.connect()
    assert (await device.trans("*IDN?")).startswith(b"ACME")

    # the device closes the connection, e.g. after a power cycle
    for writer in connections:
        writer.close()
    await asyncio.sleep(0.1)

    with pytest.raises(DeviceConnectionError):
        for _ in range(3):  # depending on timing, the first transaction might not fail yet
            await device.trans("*IDN?")

    with contextlib.suppress(DeviceConnectionError):
        await device.disconnect()  # might raise for the broken connection, but must close it anyway

    assert not device._is_connection_open

    await device.connect()
    assert (await device.trans("*IDN?")).startswith(b"ACME")

    await device.disconnect()
    server.close()
    # A handler whose connection was closed on the server side never sees EOF, wait_closed() would wait for it
    for handler in handlers:
        handler.cancel()
    await asyncio.gather(*handlers, return_exceptions=True)


async def _identification_server(identification: bytes, delay: float = 0.0):
    """A device that answers every line with the given identification, after `delay` seconds."""

    async def handle(reader, writer):
        try:
            while await reader.readline():
                await asyncio.sleep(delay)
                writer.write(identification + b"\n")
                await writer.drain()
        except ConnectionError:
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identification, delay",
    [
        (b"OTHER,MODEL 2,SN,1.0", 0.0),  # the wrong device
        (b"ACME,MODEL 1,SN,1.0", 1.0),  # the right device, but it answers after the read timeout
    ],
)
async def test_connect_fails_and_does_not_hang_when_the_identification_fails(identification, delay):
    """connect() used to deadlock here: is_connected() called disconnect() while connect() held the connect lock."""
    server, port = await _identification_server(identification, delay)
    device = AsyncSCPIInterface("ACME", hostname="127.0.0.1", port=port, read_timeout=0.3, id_validation="ACME")
    try:
        with pytest.raises(DeviceConnectionError, match="identity verification"):
            await asyncio.wait_for(device.connect(), timeout=5.0)
        assert not device._is_connection_open
    finally:
        server.close()


@pytest.mark.asyncio
async def test_connect_validates_the_identification():
    server, port = await _identification_server(b"ACME,MODEL 1,SN,1.0")
    device = AsyncSCPIInterface("ACME", hostname="127.0.0.1", port=port, read_timeout=1.0, id_validation="ACME")
    try:
        await asyncio.wait_for(device.connect(), timeout=5.0)
        assert device._is_connection_open
        assert device.identification == "ACME,MODEL 1,SN,1.0"
        await device.connect()  # already connected: a warning, no second validation
        await device.disconnect()
    finally:
        server.close()
