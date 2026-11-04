"""The Details panel of the DAQ6510 in the CGSE TUI (`cgse tui`), registered in the entry-point group
`cgse.tui.details`.

The TUI calls `details(report, live)` every second with the last status report and the components of the last
monitoring message: `latest` (the latest reading per channel), `scan`, `acquisition` and `sinks`, see
`DAQ6510ControlServer.get_component_status()`. Only Rich is used here, this module doesn't depend on the TUI.
"""

from __future__ import annotations

import datetime
import math
from typing import Any

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

HEALTH_STYLES = {"ok": "green", "degraded": "dark_orange", "failed": "red"}


def _number(value: Any, digits: int = 3) -> Text:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return Text("–" if value is None else str(value), justify="right")
    if isinstance(value, float) and math.isnan(value):
        return Text("NaN", style="red", justify="right")
    return Text(f"{value:.{digits}f}" if isinstance(value, float) else str(value), justify="right")


def _age(timestamp: Any) -> str:
    """ "3 s ago" for an ISO 8601 time, "–" when it can't be read."""
    try:
        then = datetime.datetime.fromisoformat(str(timestamp))
    except ValueError:
        return "–"
    if then.tzinfo is None:
        then = then.replace(tzinfo=datetime.timezone.utc)
    seconds = (datetime.datetime.now(datetime.timezone.utc) - then).total_seconds()
    return f"{seconds:.0f} s ago" if seconds < 120 else f"{seconds / 60:.0f} min ago"


def _grid(rows: list[tuple[str, Any]]) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column(overflow="fold")
    for label, value in rows:
        if value is not None:
            grid.add_row(label, value if isinstance(value, Text) else Text(str(value)))
    return grid


def _flag(value: Any, true: str, false: str, true_style: str = "green", false_style: str = "dim") -> Text | None:
    if value is None:
        return None
    return Text(true, style=true_style) if value else Text(false, style=false_style)


def readings(latest: dict[str, Any]) -> RenderableType:
    """The latest reading of every channel, with its unit and age."""
    if not latest:
        return Text("No readings yet: start a scan with `daq6510_cs start-scan`.", style="dim")
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("Channel", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Unit", style="dim")
    table.add_column("Read", style="dim")
    for channel in sorted(latest):
        reading = latest[channel] if isinstance(latest[channel], dict) else {}
        table.add_row(
            channel, _number(reading.get("value")), str(reading.get("unit") or ""), _age(reading.get("timestamp"))
        )
    return table


def scan(values: dict[str, Any]) -> RenderableType:
    """The state of the scan on the instrument and its errors."""
    scan = values.get("scan") or {}
    health = scan.get("health")
    channels = scan.get("channels") or []
    error = scan.get("last_error")
    return _grid(
        [
            ("Scanning", _flag(scan.get("running"), "yes", "no")),
            ("Health", Text(str(health), style=HEALTH_STYLES.get(health, "dark_orange")) if health else None),
            ("Channels", f"{len(channels)}: {', '.join(map(str, channels))}" if channels else None),
            ("Interval", f"{scan['interval']} s" if scan.get("interval") is not None else None),
            ("Started", _age(scan["scan_started_at"]) if scan.get("scan_started_at") else None),
            ("Scans", scan.get("scans_received")),
            ("Rollovers", scan.get("rollovers")),
            ("Restarts", scan.get("restarts")),
            ("Errors", Text(str(scan.get("error_count", 0)), style="dark_orange" if scan.get("error_count") else "")),
            (
                "Last error",
                Text(f"{error} ({_age(scan.get('last_error_at'))})", style="dark_orange") if error else None,
            ),
        ]
    )


def data(values: dict[str, Any]) -> RenderableType:
    """Where the readings go: the acquisition queue, the Storage Manager and the Metrics Hub."""
    acquisition = values.get("acquisition") or {}
    sinks = values.get("sinks") or {}
    dropped, failed = acquisition.get("dropped"), sinks.get("failed_metrics")
    return _grid(
        [
            ("Queue", acquisition.get("queue_size")),
            ("Dropped", Text(str(dropped), style="dark_orange" if dropped else "") if dropped is not None else None),
            ("Stored", sinks.get("stored")),
            ("Metrics sent", sinks.get("sent_metrics")),
            (
                "Metrics failed",
                Text(str(failed), style="dark_orange" if failed else "") if failed is not None else None,
            ),
        ]
    )


def details(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The readings, the scan and the data sinks; `live` (the monitoring message) is newer than the report."""
    values = report.get("details") if isinstance(report.get("details"), dict) else {}
    values = {**values, **live}
    if "latest" not in values:  # a control server of an older version
        readings_ = Text(
            "This server doesn't publish its latest readings, restart it with the current version to see them.",
            style="dim",
        )
    else:
        readings_ = readings(values["latest"] or {})
    return {"Readings": readings_, "Scan": scan(values), "Data": data(values)}
