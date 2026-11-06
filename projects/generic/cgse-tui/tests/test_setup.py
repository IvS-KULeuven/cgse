"""Tests for the device drivers of the Setup: found in the Setup, shown when not running, matched when running."""

from cgse_tui.data.setup import SetupDevice
from cgse_tui.data.setup import matches
from cgse_tui.data.setup import setup_devices

SETUP = {
    "site_id": "LAB",
    "gse": {
        "DAQ6510": {"device_name": "Keithley DAQ6510", "cgse_object": "daq6510", "channels": {"cgse_object": "x"}},
        "hexapods": {
            "one": {"device_name": "PUNA Hexapod", "cgse_object": "puna", "device_id": "PUNA_01"},
            "two": {"cgse_object": "puna", "device_id": 2},
        },
        "tcs": {"device_name": "TCS", "device": "class//egse.tcs.tcs.TCSProxy"},  # no cgse_object: not shown
    },
    "history": {"1": "first Setup"},
}


def test_setup_devices():
    devices = setup_devices(SETUP)
    assert devices == [
        SetupDevice("daq6510", None, "Keithley DAQ6510", "gse.DAQ6510"),  # its sub-nodes are configuration
        SetupDevice("puna", "PUNA_01", "PUNA Hexapod", "gse.hexapods.one"),
        SetupDevice("puna", "2", "two", "gse.hexapods.two"),  # the key when there's no device_name
    ]
    assert [device.key for device in devices] == ["setup:daq6510:", "setup:puna:PUNA_01", "setup:puna:2"]


def test_matches():
    daq, puna, _ = setup_devices(SETUP)
    assert matches(daq, "daq6510", None) and matches(daq, "daq6510", "ANY")  # no device_id in the Setup
    assert matches(puna, "puna", "PUNA_01") and not matches(puna, "puna", "PUNA_02")
    assert not matches(puna, "zonda", "PUNA_01")


def test_a_setup_object_is_read_too():
    from egse.setup import Setup

    devices = setup_devices(Setup(SETUP))
    assert [device.cgse_object for device in devices] == ["daq6510", "puna", "puna"]
