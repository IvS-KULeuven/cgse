"""Tests for the DAQ6510 model and the asynchronous driver talking to the model."""

import datetime

import pytest

from egse.tempcontrol.keithley.daq6510_adev import parse_readings
from egse.tempcontrol.keithley.daq6510_config import ScanConfig
from egse.tempcontrol.keithley.daq6510_config import SensorConfig
from egse.tempcontrol.keithley.daq6510_model import DAQ6510Model
from egse.tempcontrol.keithley.daq6510_model import ModelledDAQ6510
from egse.tempcontrol.keithley.daq6510_model import short_form
from egse.tempcontrol.keithley.daq6510_model import split_arguments


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.mark.parametrize(
    "header, expected",
    [
        ("ROUTe:SCAN:COUNt:SCAN", "ROUT:SCAN:COUN:SCAN"),
        ("ROUT:SCAN:COUN:SCAN", "ROUT:SCAN:COUN:SCAN"),
        (":ROUTE:SCAN:CREATE", "ROUT:SCAN:CRE"),
        ("route:scan:interval", "ROUT:SCAN:INT"),
        ("TRACe:ACTual:END?", "TRAC:ACT:END?"),
        ("INITiate:IMMediate", "INIT"),
        ("SYSTem:ERRor:NEXT?", "SYST:ERR?"),
        ("*IDN?", "*IDN?"),
        ("SYST:TIME", "SYST:TIME"),
        ("TRACe:FILL:MODE", "TRAC:FILL:MODE"),
        ("TRAC:DATA?", "TRAC:DATA?"),
    ],
)
def test_short_form(header, expected):
    assert short_form(header) == expected


def test_split_arguments():
    assert split_arguments('"TEMP", (@101:102, 105)') == ['"TEMP"', "(@101:102, 105)"]
    assert split_arguments('1, 10, "defbuffer1", CHAN, READ') == ["1", "10", '"defbuffer1"', "CHAN", "READ"]
    assert split_arguments("") == []


def test_unknown_command_goes_to_error_queue():
    model = DAQ6510Model()

    assert model.process("FOO:BAR 1") is None
    assert model.process("FOO:BAR?") == ""  # queries always get a response, no timeouts

    assert model.process("SYST:ERR?").startswith("-113,")
    assert model.process("SYST:ERR?").startswith("-113,")
    assert model.process("SYST:ERR?") == '0,"No error;0;0 0"'


def test_scan_fills_buffer_with_time():
    clock = FakeClock()
    model = DAQ6510Model(clock=clock, scan_duration=0.1)

    model.process("ROUT:SCAN:CRE (@101:103)")
    model.process("ROUT:SCAN:COUN:SCAN 0")
    model.process("ROUT:SCAN:INT 1")

    assert model.process('TRAC:ACT? "defbuffer1"') == "0"

    model.process("INIT")
    assert model.process("ROUT:SCAN:STAT?").startswith("RUNNING")

    clock.t = 0.05
    assert model.process("TRAC:ACT:END?") == "0"  # the first scan is not finished yet

    clock.t = 2.5
    assert model.process("TRAC:ACT:END?") == "9"  # scans started at 0, 1 and 2 are complete

    model.process("ABOR")
    clock.t = 10.0
    assert model.process("TRAC:ACT:END?") == "9"
    assert model.process("ROUT:SCAN:STAT?").startswith("ABORTED")


def test_finite_scan_count():
    clock = FakeClock()
    model = DAQ6510Model(clock=clock)

    model.process("ROUT:SCAN:CRE (@101,102); ROUT:SCAN:COUN:SCAN 2; ROUT:SCAN:INT 1; INIT")
    clock.t = 100.0

    assert model.process("TRAC:ACT?") == "4"
    assert model.process("ROUT:SCAN:STAT?").startswith("SUCCESS")


def test_scan_waits_for_start_stimulus():
    clock = FakeClock()
    model = DAQ6510Model(clock=clock)

    model.process("ROUT:SCAN:CRE (@101); ROUT:SCAN:COUN:SCAN 0; ROUT:SCAN:STAR:STIM DISP; INIT")
    clock.t = 10.0
    assert model.process("ROUT:SCAN:STAT?").startswith("WAITING")
    assert model.process("TRAC:ACT?") == "0"

    model.process("ABOR; ROUTe:SCAN:STARt:STIMulus NONE; INIT")
    clock.t = 20.0
    assert model.process("ROUT:SCAN:STAT?").startswith("RUNNING")


def test_init_without_scan_list_is_an_error():
    model = DAQ6510Model()
    model.process("INIT")
    assert model.process("SYST:ERR?").startswith("-221,")


def test_trace_data_out_of_range():
    model = DAQ6510Model()
    assert model.process('TRAC:DATA? 1, 5, "defbuffer1", READ') == ""
    assert model.process("SYST:ERR?").startswith("-222,")


def test_set_and_get_time():
    model = DAQ6510Model()
    model.process("SYST:TIME 2025, 1, 2, 3, 4, 5")
    assert model.process("SYST:TIME? 1") == "Thu Jan 02 03:04:05 2025"


def test_parse_readings():
    readings = parse_readings("101,1700000000,0.250000000,2.012345E+01,Celsius,102,1700000000,0.5,2.1E+01,Celsius")

    assert [r.channel for r in readings] == ["101", "102"]
    assert readings[0].value == pytest.approx(20.12345)
    assert readings[0].unit == "Celsius"
    assert readings[0].timestamp == datetime.datetime(2023, 11, 14, 22, 13, 20, 250000, tzinfo=datetime.timezone.utc)
    assert readings[1].timestamp - readings[0].timestamp == datetime.timedelta(seconds=0.25)

    assert parse_readings("") == []

    with pytest.raises(ValueError):
        parse_readings("101,1700000000,0.25")


@pytest.mark.asyncio
async def test_driver_configure_and_read_scan():
    clock = FakeClock()
    model = DAQ6510Model(clock=clock, scan_duration=0.1)
    daq = ModelledDAQ6510(model)
    await daq.connect()

    config = ScanConfig(
        channel_list="(@101:102)",
        interval=2.0,
        sensors=[
            SensorConfig(
                "TEMPERATURE", "(@101:102)", [("TRANSDUCER", "FRTD"), ("RTD:FOUR", "PT100"), ("UNIT", "KELVIN")]
            )
        ],
        buffer_capacity=1000,
    )

    await daq.configure_scan(config)
    await daq.start_scan()

    assert await daq.get_errors() == []
    assert model.scan_channels == ["101", "102"]
    assert model.scan_count == 0
    assert model.scan_interval == 2.0
    assert model.scan_start_stimulus == "NONE"
    assert model.buffers["defbuffer1"].capacity == 1000
    assert model.sense[("101", "RTD:FOUR")] == "PT100"

    clock.t = 4.5
    end = await daq.get_buffer_end()
    assert end == 6

    readings = await daq.read_buffer(1, end)
    assert [r.channel for r in readings] == ["101", "102"] * 3
    assert all(r.unit == "Kelvin" for r in readings)
    assert all(r.value > 273 for r in readings)
    assert readings[2].timestamp - readings[0].timestamp == datetime.timedelta(seconds=2.0)

    await daq.abort()
    assert (await daq.get_scan_state()).startswith("ABORTED")


@pytest.mark.asyncio
async def test_driver_reports_device_errors():
    daq = ModelledDAQ6510()
    await daq.connect()

    await daq.write('SENS:FUNC "TEMP", (@1x)')
    await daq.write("NOT:A:COMMAND")

    errors = await daq.get_errors()
    assert len(errors) == 2
    assert errors[0].startswith("-224,")
    assert errors[1].startswith("-113,")


def test_wait_blocks_until_a_finite_scan_completes():
    clock = FakeClock()

    def sleep(seconds: float):
        clock.t += seconds

    model = DAQ6510Model(clock=clock, scan_duration=0.1, sleep=sleep)

    model.process("ROUT:SCAN:CRE (@101,102); ROUT:SCAN:COUN:SCAN 3; ROUT:SCAN:INT 1; INIT; *WAI")

    assert clock.t == pytest.approx(2.1)
    assert model.process("TRAC:ACT?") == "6"
    assert model.process("ROUT:SCAN:STAT?").startswith("SUCCESS")

    # A scan that repeats until aborted never completes, don't wait for it
    model.process("ROUT:SCAN:COUN:SCAN 0; INIT")
    assert model.process("*OPC?") == "1"
    assert clock.t == pytest.approx(2.1)


def test_trace_data_timestamp_element():
    model = DAQ6510Model(wall_clock=lambda: datetime.datetime(2025, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc))

    model.process("ROUT:SCAN:CRE (@101); INIT; *WAI")

    channel, tst = model.process('TRAC:DATA? 1, 1, "defbuffer1", CHAN, TST').split(",")
    assert channel == "101"
    assert tst.startswith("01/02/2025 03:04:05.")
    assert len(tst.split(".")[1]) == 9
