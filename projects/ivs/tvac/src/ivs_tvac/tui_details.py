"""The Details panel of the ThermalVac in the CGSE TUI (`cgse tui`), registered in the entry-point group
`cgse.tui.details`.

The TUI calls `details(report, live)` every second with the last status report and the components of the last
monitoring message: `latest` (the latest sample and its time), `scan`, `acquisition` and `sinks`, see
`ThermalVacControlServer.get_component_status()`. Only Rich is used here, this module doesn't depend on the TUI.
"""

from __future__ import annotations

import datetime
import math
from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text


def _value(value: Any, unit: str = "", digits: int = 2) -> Text:
    if value is None:
        return Text("–")
    if isinstance(value, bool):
        return Text("yes" if value else "no")
    if isinstance(value, float):
        if math.isnan(value):
            return Text("NaN", style="red")
        text = f"{value:.3g}" if 0 < abs(value) < 0.01 else f"{value:.{digits}f}"  # e.g. a pressure of 1e-05 mbar
        return Text(f"{text} {unit}".rstrip())
    return Text(f"{value} {unit}".rstrip())


def _state(on: Any, true: str = "on", false: str = "off") -> Text:
    """A state that is on (green) or off (dim)."""
    if on is None:
        return Text("–")
    return Text(true, style="green") if on else Text(false, style="dim")


def _alarm(alarm: Any) -> Text:
    """An error or alarm flag: red when set."""
    if alarm is None:
        return Text("–")
    return Text("yes", style="bold red") if alarm else Text("no", style="dim")


def _grid(rows: list[tuple[str, Any]]) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column(overflow="fold")
    for label, value in rows:
        if value is not None:
            grid.add_row(label, value if isinstance(value, (Text, Table)) else Text(str(value)))
    return grid


def _age(timestamp: Any) -> str:
    try:
        then = datetime.datetime.fromisoformat(str(timestamp))
    except ValueError:
        return "–"
    if then.tzinfo is None:
        then = then.replace(tzinfo=datetime.timezone.utc)
    seconds = (datetime.datetime.now(datetime.timezone.utc) - then).total_seconds()
    return f"{seconds:.0f} s ago" if seconds < 120 else f"{seconds / 60:.0f} min ago"


def vessel(sample: dict[str, Any]) -> RenderableType:
    """The state of the vessel, its pressure and the pumps."""
    state = sample.get("tvac_state_text")
    code = sample.get("tvac_state_code")
    return _grid(
        [
            ("State", Text(f"{state} ({code})" if code is not None else str(state), style="bold") if state else None),
            ("Pressure", _value(sample.get("vessel_pressure"), "mbar")),
            ("Filtered", _value(sample.get("vessel_pressure_filtered"), "mbar")),
            ("Gauge", _state(sample.get("vacuum_gauge_powered"), "powered", "off")),
            ("Gauge error", _alarm(sample.get("vacuum_gauge_error"))),
            ("Scroll pump", _state(sample.get("scroll_pump_running"), "running", "stopped")),
            ("Scroll alarm", _alarm(sample.get("scroll_pump_alarm"))),
            ("Turbo pump", _value(sample.get("turbo_pump_rpm"), "rpm")),
            ("Turbo error", _alarm(sample.get("turbo_pump_error"))),
        ]
    )


def temperatures(sample: dict[str, Any]) -> RenderableType:
    """The temperatures of the vessel and the DUT, the setpoint and the control."""
    dut = Table(box=None, padding=(0, 2), show_edge=False)
    dut.add_column("DUT", style="bold")
    dut.add_column("Temperature", justify="right")
    dut.add_column("Weight", justify="right")
    for index in (1, 2, 3):
        dut.add_row(
            str(index),
            _value(sample.get(f"dut_temperature{index}"), "°C"),
            _value(sample.get(f"dut_temp_sensor_weight{index}")),
        )
    return Group(
        _grid(
            [
                ("Temperature 1", _value(sample.get("temperature1"), "°C")),
                ("Temperature 2", _value(sample.get("temperature2"), "°C")),
                ("Average", _value(sample.get("average_temperature"), "°C")),
                ("Setpoint", _value(sample.get("temperature_setpoint"), "°C")),
                ("Control", _state(sample.get("temperature_ctrl_active"), "active", "off")),
                ("PID cooling", _value(sample.get("pid_output_cooling"))),
                ("PID heating", _value(sample.get("pid_output_heating"))),
            ]
        ),
        Text(""),
        dut,
    )


def data(values: dict[str, Any], sample: dict[str, Any], timestamp: Any) -> RenderableType:
    """The scan, where the samples go, and the data logging of the ThermalVac itself."""
    scan = values.get("scan") or {}
    acquisition = values.get("acquisition") or {}
    sinks = values.get("sinks") or {}
    dropped, failed = acquisition.get("dropped"), sinks.get("failed_metrics")
    queue, maximum = acquisition.get("queue_size"), acquisition.get("queue_maxsize")
    error = sample.get("data_logging_error")
    return _grid(
        [
            ("Scanning", _state(scan.get("running"), "yes", "no")),
            ("Sample", _age(timestamp) if timestamp else None),
            ("Queue", f"{queue} of {maximum}" if maximum else queue),
            ("Dropped", Text(str(dropped), style="dark_orange" if dropped else "") if dropped is not None else None),
            ("CSV rows", sinks.get("written_csv")),
            ("Metrics sent", sinks.get("sent_metrics")),
            (
                "Metrics failed",
                Text(str(failed), style="dark_orange" if failed else "") if failed is not None else None,
            ),
            ("Logging", _state(sample.get("data_logging_active"), "active", "off") if sample else None),
            ("Logging error", _alarm(error) if error is not None else None),
            ("Logging file", sample.get("data_logging_filename") or None),
        ]
    )


def details(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The vessel, the temperatures and the data; `live` (the monitoring message) is newer than the report."""
    values = report.get("details") if isinstance(report.get("details"), dict) else {}
    values = {**values, **live}
    latest = values.get("latest") or {}
    sample = latest.get("sample") or {}
    if not sample:
        if "latest" not in values:  # a control server of an older version
            note = Text(
                "This server doesn't publish its latest sample, restart it with the current version to see it.",
                style="dim",
            )
        else:
            note = Text("No sample yet: the scan of the ThermalVac hasn't delivered data.", style="dim")
        return {"Vessel": note, "Temperatures": Text(""), "Data": data(values, sample, None)}
    return {
        "Vessel": vessel(sample),
        "Temperatures": temperatures(sample),
        "Data": data(values, sample, latest.get("timestamp")),
    }
