"""Tests for the Details panel of the DAQ6510 in the CGSE TUI."""

import datetime

from rich.console import Console

from keithley_tempcontrol.tui_details import details


def render(renderable) -> str:
    console = Console(width=100, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

LIVE = {
    "latest": {
        "101": {"value": 21.5, "unit": "Celsius", "timestamp": NOW},
        "102": {"value": float("nan"), "unit": "Celsius", "timestamp": NOW},
    },
    "scan": {
        "running": True,
        "health": "degraded",
        "channels": ["101", "102"],
        "interval": 10,
        "scans_received": 12,
        "error_count": 1,
        "last_error": "timeout",
        "last_error_at": NOW,
    },
    "acquisition": {"queue_size": 0, "dropped": 2},
    "sinks": {"stored": 12, "sent_metrics": 12, "failed_metrics": 0},
}


def test_the_sections():
    sections = details({"details": {}}, LIVE)
    assert list(sections) == ["Readings", "Scan", "Data"]
    readings = render(sections["Readings"])
    assert "101" in readings and "21.500" in readings and "Celsius" in readings and "NaN" in readings
    scan = render(sections["Scan"])
    assert "degraded" in scan and "2: 101, 102" in scan and "timeout" in scan
    assert "Dropped" in render(sections["Data"])


def test_no_readings_yet():
    sections = details({"details": {"scan": {"running": False}, "latest": {}}}, {})
    assert "No readings yet" in render(sections["Readings"])
    assert "no" in render(sections["Scan"])


def test_an_older_server_without_latest():
    sections = details({"details": {"scan": {"running": True}}}, {"scan": {"running": True}})
    assert "restart it with the current version" in render(sections["Readings"])
