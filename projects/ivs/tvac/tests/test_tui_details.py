"""Tests for the Details panel of the ThermalVac in the CGSE TUI."""

import datetime

from rich.console import Console

from ivs_tvac.tui_details import details


def render(renderable) -> str:
    console = Console(width=100, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


SAMPLE = {
    "vacuum_gauge_powered": True,
    "vacuum_gauge_error": False,
    "vessel_pressure": 1.2e-5,
    "vessel_pressure_filtered": 1.3e-5,
    "temperature1": 19.43,
    "temperature2": 19.93,
    "dut_temperature1": 19.73,
    "dut_temperature2": 18.94,
    "dut_temperature3": 19.52,
    "dut_temp_sensor_weight1": 1,
    "dut_temp_sensor_weight2": 1,
    "dut_temp_sensor_weight3": 0,
    "average_temperature": 19.45,
    "temperature_setpoint": -20.0,
    "pid_output_cooling": 35.0,
    "pid_output_heating": 0.0,
    "temperature_ctrl_active": True,
    "scroll_pump_running": True,
    "scroll_pump_alarm": False,
    "turbo_pump_rpm": 1500,
    "turbo_pump_error": True,
    "tvac_state_code": 3,
    "tvac_state_text": "Cooling",
    "data_logging_active": False,
    "data_logging_error": False,
    "data_logging_filename": "run.csv",
}

LIVE = {
    "latest": {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sample": SAMPLE},
    "scan": {"running": True},
    "acquisition": {"queue_size": 0, "queue_maxsize": 10000, "dropped": 0},
    "sinks": {"written_csv": 100, "sent_metrics": 100, "failed_metrics": 3},
}


def test_the_sections():
    sections = details({"details": {}}, LIVE)
    assert list(sections) == ["Vessel", "Temperatures", "Data"]
    vessel = render(sections["Vessel"])
    assert "Cooling (3)" in vessel and "1.2e-05 mbar" in vessel and "1500 rpm" in vessel
    temperatures = render(sections["Temperatures"])
    assert "19.43 °C" in temperatures and "-20.00 °C" in temperatures and "active" in temperatures
    data = render(sections["Data"])
    assert "0 of 10000" in data and "run.csv" in data


def test_no_sample_yet():
    sections = details({"details": {"scan": {"running": False}, "latest": {"timestamp": None, "sample": {}}}}, {})
    assert "No sample yet" in render(sections["Vessel"])


def test_an_older_server_without_latest():
    sections = details({"details": {"scan": {"running": True}}}, {"scan": {"running": True}})
    assert "restart it with the current version" in render(sections["Vessel"])
