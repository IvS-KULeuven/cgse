"""Tests for the Details panel of the hexapods in the CGSE TUI."""

import math

from rich.console import Console

from symetrie_hexapod.tui_details import details


def render(renderable) -> str:
    console = Console(width=100, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def test_live_positions_win_over_the_report():
    import numpy as np

    report = {"details": {"mach": [0.0] * 6, "user": [0.0] * 6, "alength": [1.0] * 6}}
    live = {"mach": [np.float64(1.5), 0.0, 0.0, 0.0, np.float64(-0.0), 0.0], "alength": [math.nan] * 6}
    sections = details(report, live)
    assert list(sections) == ["Position", "Actuators"]

    position = render(sections["Position"])
    assert "X" in position and "1.5000" in position and "mm" in position and "deg" in position
    assert "-0.0000" not in position
    assert "NaN" in render(sections["Actuators"])


def test_a_disconnected_hexapod_has_no_positions():
    sections = details({"details": {}}, {})
    assert "–" in render(sections["Position"]) and "–" in render(sections["Actuators"])


def test_a_failed_details_section_is_ignored():
    sections = details({"details": {"error": "boom"}}, {"mach": [1.0] * 6})
    assert "1.0000" in render(sections["Position"])
