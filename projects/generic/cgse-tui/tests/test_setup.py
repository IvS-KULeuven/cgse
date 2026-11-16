"""Tests for the key of the row of a device driver of the Setup that isn't running, see `egse.setup` for the rest."""

from cgse_tui.data.setup import setup_key
from egse.setup import SetupDevice


def test_setup_key():
    assert setup_key(SetupDevice("daq6510", None, "Keithley DAQ6510", "gse.DAQ6510")) == "setup:daq6510:"
    assert setup_key(SetupDevice("puna", "PUNA_01", "PUNA Hexapod", "gse.hexapod")) == "setup:puna:PUNA_01"
