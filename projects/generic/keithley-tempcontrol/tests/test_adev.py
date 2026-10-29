"""Tests for the asynchronous DAQ6510 driver over a real socket connection to the simulator.

Start the simulator before running these tests, they are skipped otherwise:

    $ daq6510_sim start

The HOSTNAME of the "Keithley DAQ6510" settings must point to the simulator (localhost).
"""

import asyncio
import datetime
import socket

import pytest

from egse.settings import Settings
from egse.tempcontrol.keithley.daq6510_adev import DAQ6510
from egse.tempcontrol.keithley.daq6510_config import ScanConfig
from egse.tempcontrol.keithley.daq6510_config import SensorConfig

settings = Settings.load("Keithley DAQ6510")

SCPI_PORT = settings.get("PORT", 5025)
HOSTNAME = settings.get("HOSTNAME", "localhost")


def is_simulator_available() -> bool:
    """Returns True when the simulator answers the identification query. The check is synchronous on purpose,
    it runs at import time, outside an event loop."""
    try:
        with socket.create_connection((HOSTNAME, SCPI_PORT), timeout=1.0) as sock:
            sock.settimeout(1.0)
            sock.sendall(b"*IDN?\n")
            response = sock.recv(1024).decode()
    except OSError:
        return False

    return "DAQ6510" in response and "SIMULATOR" in response


pytestmark = pytest.mark.skipif(
    not is_simulator_available(), reason="These tests need the DAQ6510 simulator, start it with 'daq6510_sim start'."
)


def make_config(**kwargs) -> ScanConfig:
    defaults = {
        "channel_list": "(@101:102)",
        "interval": 0.2,
        "sensors": [SensorConfig("TEMPERATURE", "(@101:102)", [("TRANSDUCER", "FRTD"), ("RTD:FOUR", "PT100")])],
        "buffer_capacity": 1000,
    }
    defaults.update(kwargs)
    return ScanConfig(**defaults)


async def wait_for_readings(daq: DAQ6510, count: int, timeout: float = 5.0) -> int:
    """Waits until the buffer holds at least `count` readings, returns the index of the last reading."""

    async def _wait():
        while (end := await daq.get_buffer_end()) < count:
            await asyncio.sleep(0.05)
        return end

    return await asyncio.wait_for(_wait(), timeout)


@pytest.fixture
async def daq():
    """Yields a connected driver. The simulator keeps its state between connections, so it is reset first."""
    device = DAQ6510(HOSTNAME, SCPI_PORT)
    await device.connect()
    await device.reset()

    yield device

    if device.is_connection_open:
        await device.abort()
        await device.disconnect()


async def test_connect_and_identify():
    device = DAQ6510(HOSTNAME, SCPI_PORT)
    assert not device.is_connection_open

    await device.connect()
    try:
        assert device.is_connection_open
        assert await device.is_connected()

        manufacturer, model, *_ = (await device.get_idn()).split(",")
        assert manufacturer == "KEITHLEY INSTRUMENTS"
        assert model == "MODEL DAQ6510"
    finally:
        await device.disconnect()

    assert not device.is_connection_open


async def test_context_manager():
    async with DAQ6510(HOSTNAME, SCPI_PORT) as device:
        assert device.is_connection_open

    assert not device.is_connection_open


async def test_error_queue(daq):
    assert await daq.get_errors() == []

    await daq.write("NOT:A:COMMAND")
    await daq.write('SENS:FUNC "TEMP", (@1x)')

    errors = await daq.get_errors()
    assert len(errors) == 2
    assert errors[0].startswith("-113,")
    assert errors[1].startswith("-224,")

    assert await daq.get_errors() == []


async def test_unknown_query_does_not_time_out(daq):
    assert await daq.query_str("NOT:A:QUERY?") == ""
    assert (await daq.get_errors())[0].startswith("-113,")


async def test_set_and_get_time(daq):
    await daq.set_time(datetime.datetime(2025, 1, 2, 3, 4, 5))

    assert (await daq.get_time()).startswith("Thu Jan 02 03:04")


async def test_scan_and_read_buffer(daq):
    config = make_config()

    await daq.set_time()
    await daq.configure_scan(config)
    await daq.start_scan()
    assert await daq.get_errors() == []
    assert (await daq.get_scan_state()).startswith("RUNNING")

    end = await wait_for_readings(daq, 3 * len(config.channel_names))
    end -= end % len(config.channel_names)  # complete scans only

    readings = await daq.read_buffer(1, end)

    assert len(readings) == end
    assert [r.channel for r in readings] == config.channel_names * (end // len(config.channel_names))
    assert all(r.unit == "Celsius" for r in readings)

    now = datetime.datetime.now(datetime.timezone.utc)
    assert all(abs(now - r.timestamp) < datetime.timedelta(seconds=10) for r in readings)

    scan_starts = [r.timestamp for r in readings[:: len(config.channel_names)]]
    assert scan_starts == sorted(scan_starts)
    assert scan_starts[1] - scan_starts[0] == pytest.approx(
        datetime.timedelta(seconds=config.interval), abs=datetime.timedelta(milliseconds=1)
    )

    await daq.abort()
    assert (await daq.get_scan_state()).startswith("ABORTED")


async def test_scan_continues_while_disconnected(daq):
    """The control server reconnects after a timeout and expects the instrument to keep scanning meanwhile."""
    await daq.configure_scan(make_config())
    await daq.start_scan()
    before = await wait_for_readings(daq, 2)

    await daq.disconnect()
    await asyncio.sleep(0.5)
    await daq.connect()

    assert (await daq.get_scan_state()).startswith("RUNNING")
    assert await daq.get_buffer_end() > before


async def test_clear_buffer(daq):
    await daq.configure_scan(make_config())
    await daq.start_scan()
    await wait_for_readings(daq, 2)
    await daq.abort()

    await daq.clear_buffer()

    assert await daq.get_buffer_count() == 0
    assert await daq.get_buffer_end() == 0
