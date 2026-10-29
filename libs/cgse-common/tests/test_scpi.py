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
