"""The content of the panels in the detail screen, as Rich renderables built from a `ServiceInfo`.

Every detail screen has the same panels: Service (registration and endpoints), Process (live), Device (when the
service controls a device) and Details (service specific). The functions here only read the `ServiceInfo`, so they can
be tested without running the app.

The Details panel shows the device values of the last monitoring message when there is one, updated every second,
on top of the `details` of the last status report: both come from the same `get_status()` of the device protocol
(sync) or `get_component_status()` (async), the monitoring message is just newer.

The Details panel renders any status generically: the keys in the left column, nested dictionaries drawn as a tree
like `rich.tree.Tree` does, the values in the right column, and lists of dictionaries as tables. The status reports
come from many servers and versions, so nothing is assumed about the types of the values: a sync control server sends
its `details` over pickle, e.g. with `NaN` in a hexapod's `alength`.
"""

from __future__ import annotations

import math
from typing import Any

from rich.console import Group
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from cgse_tui.data.model import Level
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.data.monitor import live_values
from cgse_tui.data.services import custom_kind
from cgse_tui.screens.columns import LEVEL_STYLES
from cgse_tui.screens.columns import format_age
from cgse_tui.screens.columns import format_mib
from cgse_tui.screens.columns import format_seconds
from cgse_tui.screens.columns import format_time
from cgse_tui.screens.columns import format_uptime
from cgse_tui.screens.columns import other_ports
from cgse_tui.screens.columns import service_type

NOT_KNOWN = "–"

Row = tuple[str, Any]
"""A label and a value; the value is formatted with `format_value()` unless it is a Rich `Text`."""

MAX_GROUP_SIZE = 200
"""A nested dictionary that takes more rows than this is not unfolded: the Details panel is rendered every second."""

TIME_SUFFIXES = ("_time", "_at", "timestamp", "heartbeat")
"""Keys with one of these endings and a value in seconds since the epoch are shown as local date and time."""


def is_time(key: str | None, value: Any) -> bool:
    return (
        key is not None
        and str(key).endswith(TIME_SUFFIXES)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 1e9
    )


def format_value(value: Any, key: str | None = None) -> str:
    """A value of any type as a short text: e.g. floats with 6 significant digits, NaN as "NaN", None as "–", and
    seconds since the epoch as local date and time when the key says it's a time, e.g. `start_time`."""
    if value is None:
        return NOT_KNOWN
    if is_time(key, value):
        return format_time(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return f"{value:.1f}" if abs(value) >= 1e5 else f"{value:.6g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(format_value(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{name}={format_value(item, name)}" for name, item in value.items())
    return str(value)


def flag(value: bool | None, true_style: str = "green", false_style: str = "dark_orange") -> Text:
    """yes/no in colour, "–" when not known."""
    if value is None:
        return Text(NOT_KNOWN)
    return Text("yes", style=true_style) if value else Text("no", style=false_style)


def error_of(section: Any) -> str | None:
    """The error of a report section that couldn't be retrieved: such a section contains only an `error` entry."""
    if isinstance(section, dict) and set(section) == {"error"}:
        return str(section["error"])
    return None


def error_text(message: str) -> Text:
    return Text(f"error: {message}", style="red")


def key_values(rows: list[Row]) -> Table:
    """A two-column grid of labels and values. A label can be a Rich `Text`, e.g. with the guides of a tree."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column(overflow="fold")  # e.g. a long path is folded, not cut off
    for label, value in rows:
        key = label.plain if isinstance(label, Text) else label
        # A Rich renderable (Text, Table, Group, ...) is shown as it is, any other value is formatted
        renderable = hasattr(value, "__rich_console__") or hasattr(value, "__rich__")
        grid.add_row(label, value if renderable else Text(format_value(value, key)))
    return grid


FILLED, FRAME = "■", "□"


def state_indicator(service: ServiceInfo) -> Text:
    """Returns the coloured square that shows the state of a service.

    - green: running
    - orange: running, but no connection with the device
    - red: not responding within the stale time
    - empty frame: not running
    - grey: registered, but no information received yet
    """
    if service.state is ServiceState.OK:
        if service.has_device and service.connected is False:
            return Text(FILLED, style="dark_orange")
        return Text(FILLED, style="green")
    if service.state is ServiceState.STALE:
        return Text(FILLED, style="red")
    if service.state is ServiceState.INACTIVE:
        return Text(FRAME)
    return Text(FILLED, style="grey50")


# ----- the panels -----------------------------------------------------------------------------------------------------


def title(service: ServiceInfo, indicator: Text, now: float, requesting: bool = False, gone: bool = False) -> Text:
    """The line above the panels: state square, name, service type, state and the age of the information."""
    text = Text.assemble(indicator, " ", (service.name, "bold"), f" ({service.service_type}) – {service.state.value}")
    if gone:
        text.append(" – no longer registered", style="dark_orange")
    elif service.last_update is not None:
        text.append(f" – updated {format_age(service.last_update, now)} ago", style="dim")
    if requesting:
        text.append(" – requesting the status …", style="italic")
    return text


def service_rows(service: ServiceInfo, now: float) -> list[Row]:
    """The registration of the service and its endpoints."""
    control_server = service.report.get("control_server")
    control_server = control_server if isinstance(control_server, dict) else {}
    rows: list[Row] = [
        ("Service type", service_type(service) or None),
        ("In the Setup", service.setup_path),
        ("Device ID", service.device_id),
        ("Host", service.host),
        ("Registered host", service.registered_host or service.host),
        ("Hostname", service.hostname),
        ("Server kind", service.server_kind),
        ("cgse object", service.cgse_object),
        # The registry doesn't register itself
        ("Registered", None if custom_kind(service) == "registry" else flag(service.registered, false_style="")),
        ("Health", service.health),
        ("Heartbeat", f"{format_age(service.last_heartbeat, now)} ago" if service.last_heartbeat else None),
        ("TTL", f"{service.ttl} s" if service.ttl is not None else None),
        ("Port", service.port),
        ("Service port", service.service_port),
        ("Monitoring port", service.monitoring_port),
        ("Device port", control_server.get("device_commanding_port")),
        ("Other ports", other_ports(service, now) or None),
    ]
    return [(label, value) for label, value in rows if value is not None]


def process_rows(service: ServiceInfo) -> list[Row]:
    """The process information; CPU % and memory in orange or red when they are judged too high."""
    cpu_style, memory_style = LEVEL_STYLES[service.cpu_level], LEVEL_STYLES[service.memory_level]

    def mib(value: int | None) -> Text | None:
        return None if value is None else Text(f"{format_mib(value)} MiB", style=memory_style)

    return [
        ("PID", service.pid),
        ("Started", format_time(service.start_time) or None),
        ("Uptime", format_uptime(service.uptime_s) or None),
        ("CPU %", None if service.cpu_percent is None else Text(format_value(service.cpu_percent), style=cpu_style)),
        ("CPU user", format_seconds(service.cpu_user_s) or None),
        ("CPU system", format_seconds(service.cpu_system_s) or None),
        ("RSS", mib(service.rss)),
        ("USS", mib(service.uss)),
        ("Swap", mib(service.swap)),
    ]


def process_panel(service: ServiceInfo) -> RenderableType:
    """The process information, and why the CPU or memory use is judged too high, see `cgse_tui.data.health`."""
    reasons = [
        Text(reason, style=LEVEL_STYLES[level])
        for level, reason in ((service.cpu_level, service.cpu_reason), (service.memory_level, service.memory_reason))
        if level is not Level.OK
    ]
    return Group(key_values(process_rows(service)), *([Text("")] + reasons if reasons else []))


def has_device_panel(service: ServiceInfo) -> bool:
    """False for the services that control no device; the panel is shown while this is not known."""
    return service.has_device is not False and not custom_kind(service)


def device_panel(service: ServiceInfo) -> RenderableType:
    device = service.report.get("device")
    if error := error_of(device):
        return error_text(error)
    rows: list[Row] = [
        ("Connected", flag(service.connected)),
        ("Simulator", flag(service.sim_mode, true_style="yellow", false_style="")),
    ]
    if isinstance(device, dict):
        rows += [(key, value) for key, value in device.items() if key not in ("connected", "sim_mode")]
    return key_values(rows)


LIVE, LAST_MONITORING, REPORT = "live", "last monitoring message", "status report"
"""The source of the Details panel, shown in its border."""


def details_panel(service: ServiceInfo) -> tuple[RenderableType, str]:
    """The service specific status and its source (`LIVE`, `REPORT`, or "" for a message).

    For a control server: the `details` of the status report, updated with the device values of the last monitoring
    message. For a custom server: its whole status, without the process information of the Process panel.
    """
    report = service.report
    if service.state is ServiceState.INACTIVE and not report:
        return Text("Not running.", style="dim"), ""
    if custom_kind(service):
        if not report:
            return Text("No status received yet.", style="dim"), ""
        return generic({key: value for key, value in report.items() if key != "process"}), REPORT

    details, message = {}, None
    if not report:
        message = Text("No status report received yet.", style="dim")
    elif "control_server" not in report:
        message = Text(
            "This server doesn't offer the status report, restart it with the current version to see its details.",
            style="dark_orange",
        )
    elif error := error_of(report.get("details")):
        message = error_text(error)
    elif report.get("details"):
        details = report["details"] if isinstance(report["details"], dict) else {"details": report["details"]}

    if live := live_values(service.monitoring):
        return generic({**details, **live}), LIVE if service.state is ServiceState.OK else LAST_MONITORING
    if details:
        return generic(details), REPORT
    return message or Text("No details.", style="dim"), ""


# ----- generic rendering ----------------------------------------------------------------------------------------------


def is_table(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) > 0 and all(isinstance(item, dict) for item in value)


GUIDES = {"branch": "├── ", "last": "└── ", "line": "│   ", "space": "    "}
"""The guides of a tree, as `rich.tree.Tree` draws them."""


def generic(values: dict[str, Any], max_group_size: int | None = MAX_GROUP_SIZE) -> RenderableType:
    """Renders a status of any shape: the keys in the left column, with nested dictionaries as a tree, the values in
    the right column. A list of dictionaries is a table in the right column.

    A nested dictionary of more than `max_group_size` rows is not unfolded, None unfolds all. Rendering ~1000 rows
    takes about 0.25 s, too long for a panel that is rendered every second.
    """
    rows: list[Row] = []
    _tree_rows(values, "", None, rows, max_group_size)
    return key_values(rows)


def _tree_rows(values: dict, prefix: str, depth: int | None, rows: list[Row], max_group_size: int | None) -> None:
    """Adds a row per key; `prefix` is the guides of the parent levels, `depth` is None for the top level."""
    items = list(values.items())
    for index, (key, value) in enumerate(items):
        key = str(key)
        last = index == len(items) - 1
        guide = "" if depth is None else GUIDES["last" if last else "branch"]
        label = Text.assemble((prefix + guide, "not bold dim"), key)
        if isinstance(value, dict) and value:
            if max_group_size is not None and count_rows(value, max_group_size + 1) > max_group_size:
                rows.append((label, Text(f"more than {max_group_size} rows, see the raw report (v)", style="dim")))
                continue
            rows.append((label, Text("")))
            child_prefix = "" if depth is None else prefix + GUIDES["space" if last else "line"]
            _tree_rows(value, child_prefix, 0 if depth is None else depth + 1, rows, max_group_size)
        elif is_table(value):
            rows.append((label, table(None, value)))
        else:
            rows.append((label, value))


def count_rows(values: dict, limit: int) -> int:
    """The number of rows of a nested dictionary: its values and group headings. Counting stops at `limit`."""
    count = 0
    for value in values.values():
        count += 1 + (count_rows(value, limit - count - 1) if isinstance(value, dict) else 0)
        if count >= limit:
            break
    return count


def table(name: str | None, items: list[dict]) -> Table:
    """A table with a column per key of the dictionaries, in order of appearance, with the name as title."""
    columns: dict[str, None] = {}
    for item in items:
        columns.update(dict.fromkeys(map(str, item)))
    result = Table(title=name, title_justify="left", title_style="bold", expand=False, padding=(0, 1))
    for column in columns:
        result.add_column(column, no_wrap=True, overflow="ellipsis", max_width=40)
    for item in items:
        values = {str(key): value for key, value in item.items()}
        result.add_row(*(format_value(values.get(column), column) for column in columns))
    return result
