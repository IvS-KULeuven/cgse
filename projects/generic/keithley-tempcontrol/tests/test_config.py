import pytest
from egse.setup import Setup

from egse.tempcontrol.keithley.daq6510_config import ScanConfig
from egse.tempcontrol.keithley.daq6510_config import scan_config_from_setup

SETUP_YAML = """
gse:
    DAQ6510:
        channels: (@101:105)
        sensors:
            PT100:
                temperature:
                    TRANSDUCER: FRTD
                    RTD:
                        FOUR: PT100
                    UNIT: CELSIUS
                    AVERAGE:
                        STATE: True
                    channels: (@101:104)
            PT100-2W:
                temperature:
                    TRANSDUCER: RTD
                    RTD:
                        TWO: PT100
                    channels: (@105)
        route:
            scan:
                COUNT:
                    SCAN: 10
                INTERVAL: 5
"""


def test_scan_config_from_setup():
    config = scan_config_from_setup(Setup.from_yaml_string(SETUP_YAML))

    assert config.channel_list == "(@101:105)"
    assert config.channel_names == ["101", "102", "103", "104", "105"]
    assert config.interval == 5.0
    assert config.buffer_name == "defbuffer1"

    assert len(config.sensors) == 2
    assert config.sensors[0].function == "TEMPERATURE"
    assert config.sensors[0].channel_list == "(@101:104)"
    assert config.sensors[0].settings == [
        ("TRANSDUCER", "FRTD"),
        ("RTD:FOUR", "PT100"),
        ("UNIT", "CELSIUS"),
        ("AVERAGE:STATE", "ON"),
    ]
    assert config.sensors[1].channel_list == "(@105)"
    assert config.sensors[1].settings == [("TRANSDUCER", "RTD"), ("RTD:TWO", "PT100")]


def test_scan_config_overrides():
    config = scan_config_from_setup(Setup.from_yaml_string(SETUP_YAML), buffer_capacity=500, interval=None)

    assert config.buffer_capacity == 500
    assert config.interval == 5.0  # None doesn't override


def test_scan_config_without_daq_section():
    with pytest.raises(ValueError, match="No gse.DAQ6510 section"):
        scan_config_from_setup(Setup.from_yaml_string("gse:\n    hexapod: {}\n"))


def test_scan_config_validation():
    with pytest.raises(ValueError, match="Invalid channel list"):
        ScanConfig(channel_list="101")

    with pytest.raises(ValueError, match="at least two scans"):
        ScanConfig(channel_list="(@101:110)", buffer_capacity=10)
