"""The built-in renderers of the Details panel for the core services, by `cgse_object`, see `cgse_tui.plugins`.

They have the same signature as a plugin: `details(report, live)` returns a Rich renderable or titled renderables.
The registry also gets a table of its registrations in the detail screen, see `cgse_tui.screens.registry`.
"""

from __future__ import annotations

import datetime
import logging
import time
from collections import Counter
from collections import deque
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.console import RenderableType
from rich.text import Text

from cgse_tui.data.model import Level
from cgse_tui.plugins import latest_details
from cgse_tui.screens.columns import LEVEL_STYLES
from cgse_tui.screens.columns import format_age
from cgse_tui.screens.columns import format_time
from cgse_tui.screens.panels import format_value
from cgse_tui.screens.panels import generic
from cgse_tui.screens.panels import key_values

DISK_WARNING, DISK_CRITICAL = 80.0, 90.0
"""Percentage of the disk in use for a warning and for critical."""

BAR_WIDTH = 30

GIB = 2**30


def registry(report: dict[str, Any], live: dict[str, Any]) -> RenderableType:
    """The service registry: the number of registrations by health. The registrations are in their own table."""
    services = [service for service in report.get("services") or [] if isinstance(service, dict)]
    health = Counter(str(service.get("health") or "unknown") for service in services)
    summary = Text(f"{len(services)} registered")
    for name, count in sorted(health.items()):
        summary.append(", ")
        summary.append(f"{count} {name}", style={"passing": "green", "critical": "red"}.get(name, ""))
    return key_values(
        [
            ("Services", summary),
            ("Unique service types", report.get("enforce_unique_service_types")),
        ]
    )


def disk_level(percent: float) -> Level:
    return Level.CRITICAL if percent >= DISK_CRITICAL else Level.WARNING if percent >= DISK_WARNING else Level.OK


def disk_bar(usage: Any) -> RenderableType:
    """A bar with the part of the disk in use, e.g. "██████░░░░ 13 % used, 827.1 of 951.9 GiB free"."""
    if not isinstance(usage, dict) or not usage.get("total"):
        return Text(format_value(usage))
    total, used, free = usage["total"], usage.get("used") or 0, usage.get("free") or 0
    percent = 100 * used / total
    style = LEVEL_STYLES[disk_level(percent)] or "green"
    filled = round(BAR_WIDTH * used / total)
    return Text.assemble(
        ("█" * filled, style),
        ("░" * (BAR_WIDTH - filled), "dim"),
        f" {percent:.0f} % used, {free / GIB:.1f} of {total / GIB:.1f} GiB free",
    )


def storage(report: dict[str, Any], live: dict[str, Any]) -> RenderableType:
    """The Storage Manager: where the data goes, how full the disk is, and what is stored."""
    details = report.get("details") or {}
    registrations = details.get("registrations") or []
    return Group(
        key_values(
            [
                ("Location", details.get("storage_location")),
                ("Disk", disk_bar(details.get("disk_usage"))),
                ("Loaded Setup", details.get("loaded_setup_id")),
                ("Observation", details.get("obsid") or Text("none running", style="dim")),
                ("Registrations", f"{len(registrations)}: {format_value(registrations)}" if registrations else None),
            ]
        )
    )


def setup_info(setup: Any) -> tuple[str | None, str | None, str | None]:
    """The ID, the folder and the file name of a Setup, None when they're not known.

    The folder is on the machine of the Configuration Manager, which can be another machine than that of the TUI.
    """
    setup_id = folder = filename = None
    try:
        setup_id = setup.get_id()
        if setup.has_private_attribute("_filename"):
            path = Path(setup.get_private_attribute("_filename"))
            folder, filename = str(path.parent), path.name
    except AttributeError:
        pass
    return setup_id, folder, filename


_setup_tree: tuple[tuple, RenderableType] | None = None
"""The tree of the last Setup: rendering a large Setup takes a while, it's only rebuilt for another Setup."""


def setup_tree(setup: dict, key: tuple) -> RenderableType:
    """The whole Setup as a tree, the same object as long as the key (Setup ID and file) is the same.

    By convention the `history` of the Setup comes last.
    """
    global _setup_tree
    if _setup_tree is None or _setup_tree[0] != key:
        ordered = {name: value for name, value in setup.items() if name != "history"}
        if "history" in setup:
            ordered["history"] = setup["history"]
        _setup_tree = key, generic(ordered, max_group_size=None)
    return _setup_tree[1]


def folder_on_host(folder: str | None, report: dict[str, Any]) -> Text | None:
    """The folder with the host of the Configuration Manager, e.g. "/data/LAB/conf  on 192.168.68.75"."""
    if folder is None:
        return None
    control_server = report.get("control_server")
    host = control_server.get("hostname") if isinstance(control_server, dict) else None
    return Text.assemble(folder, (f"  on {host}", "dim") if host else "")


def configuration_manager(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The Configuration Manager: the running observation and the loaded Setup.

    The status report has `obsid_active`, `obsid`, `setup_id` and `site_id`, the monitoring messages of the CM have
    the `obsid` and the whole `setup`, which is shown in its own panel.
    """
    values = latest_details(report, live)
    setup = live.get("setup")
    file_id, folder, filename = setup_info(setup)
    setup_id = values.get("setup_id") or file_id
    obsid = values.get("obsid")
    active = obsid is not None if "obsid" in live else values.get("obsid_active")

    rows = [
        ("Observation", Text(f"running: {obsid}", style="green") if active else Text("none running", style="dim")),
        ("Setup", setup_id),
        ("Site", values.get("site_id") or (setup.get("site_id") if isinstance(setup, dict) else None)),
        ("Folder", folder_on_host(folder, report)),
        ("File", filename),
    ]
    sections = {"Configuration": key_values([(label, value) for label, value in rows if value is not None])}
    if isinstance(setup, dict) and setup:
        sections[f"Setup {setup_id}"] = setup_tree(setup, (setup_id, filename))
    return sections


def process_manager(report: dict[str, Any], live: dict[str, Any]) -> RenderableType:
    """The Process Manager: the number of core services it manages, which are listed in their own table."""
    processes = (report.get("details") or {}).get("core_processes") or {}
    return key_values([("Core services", f"{len(processes)} managed")])


# ----- the logger and the hubs ----------------------------------------------------------------------------------------

RATE_WINDOW = 10.0
"""Seconds over which a rate of messages is computed."""


class Rates:
    """Messages per second from the counters in the successive statuses of a server. Only pass counters: values
    that never go down while the server runs.

    The time of a status is its `timestamp` (seconds since the epoch, from the server), so a status that is shown
    several times doesn't count twice. Counters that go down mean the server was restarted: the rates start over.
    """

    def __init__(self, window: float = RATE_WINDOW):
        self.window = window
        self._samples: dict[str, deque[tuple[float, dict[str, float]]]] = {}

    def update(self, key: str, timestamp: Any, counters: dict[str, Any]) -> dict[str, float | None]:
        samples = self._samples.setdefault(key, deque())
        counters = {name: value for name, value in counters.items() if isinstance(value, (int, float))}
        if isinstance(timestamp, (int, float)) and (not samples or timestamp > samples[-1][0]):
            if samples and any(counters.get(name, 0) < value for name, value in samples[-1][1].items()):
                samples.clear()
            samples.append((timestamp, counters))
            while len(samples) > 2 and timestamp - samples[1][0] >= self.window:
                samples.popleft()
        if len(samples) < 2 or samples[-1][0] <= samples[0][0]:
            return dict.fromkeys(counters)
        (first_time, first), (last_time, last) = samples[0], samples[-1]
        return {name: (last[name] - first.get(name, 0)) / (last_time - first_time) for name in last if name in counters}


RATES = Rates()


def counters(statistics: dict[str, Any], *names: str) -> dict[str, Any]:
    """The counters with the given names: only values that never go down, e.g. not the size of a queue, else the
    rates start over every time such a value goes down."""
    return {name: statistics.get(name) for name in names}


def count(value: Any, rate: float | None = None, style: str = "") -> Text:
    """A counter, with its rate when known, e.g. "19801  (12.5/s)"."""
    text = Text(format_value(value), style=style)
    if rate is not None:
        text.append(f"  ({rate:.1f}/s)", style="dim")
    return text


def problem(value: Any, style: str) -> Text:
    """A counter of problems, e.g. dropped messages: coloured when it isn't zero."""
    return Text(format_value(value), style=style if isinstance(value, (int, float)) and value > 0 else "")


def epoch_timestamp(report: dict[str, Any]) -> float | None:
    """The time of a status as seconds since the epoch: the hubs send a number, the logger an ISO 8601 string."""
    value = report.get("timestamp")
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.datetime.fromisoformat(str(value).replace("+0000", "+00:00")).timestamp()
    except ValueError:
        return None


def when(timestamp: Any) -> Text | str | None:
    """A time as "12 s ago (2026-11-04 21:22:04)", None when not known."""
    if not isinstance(timestamp, (int, float)):
        return None
    return Text.assemble(f"{format_age(timestamp, time.time())} ago", (f"  ({format_time(timestamp)})", "dim"))


def notification_hub(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The notification hub: the events it received and published, and when the last one came in."""
    statistics = report.get("statistics") or {}
    rates = RATES.update("nh", report.get("timestamp"), counters(statistics, "events_received", "events_published"))
    received, published = statistics.get("events_received"), statistics.get("events_published")
    rows = [
        ("Received", count(received, rates.get("events_received"))),
        ("Published", count(published, rates.get("events_published"))),
    ]
    if isinstance(received, int) and isinstance(published, int) and received != published:
        rows.append(("Not published", Text(str(received - published), style="dark_orange")))
    rows += [
        ("Last event", when(statistics.get("last_message_time")) or Text("none yet", style="dim")),
        ("Started", format_time(statistics.get("start_time")) or None),
    ]
    return {"Events": key_values([(label, value) for label, value in rows if value is not None])}


def queue_bar(queue: Any, maximum: Any, watermark: Any) -> RenderableType:
    """The queue of the metrics hub as a bar, orange above the backlog high watermark (a fraction of the maximum)."""
    if not isinstance(queue, (int, float)) or not isinstance(maximum, (int, float)) or maximum <= 0:
        return Text(format_value(queue))
    fraction = queue / maximum
    high = isinstance(watermark, (int, float)) and fraction >= watermark
    filled = round(BAR_WIDTH * fraction)
    return Text.assemble(
        ("█" * filled, "dark_orange" if high else "green"),
        ("░" * (BAR_WIDTH - filled), "dim"),
        f" {queue:g} of {maximum:g}",
    )


def metrics_hub(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The metrics hub: what it received, wrote and dropped, its queue, and the database it writes to."""
    statistics = report.get("statistics") or {}
    rates = RATES.update("mh", report.get("timestamp"), counters(statistics, "received", "written"))
    value = statistics.get  # the counters of the hub
    last_s, avg_s = value("last_write_s"), value("avg_write_s")
    write_time = None
    if isinstance(last_s, (int, float)) and isinstance(avg_s, (int, float)):
        write_time = f"last {last_s * 1000:.1f} ms, average {avg_s * 1000:.1f} ms"
    metrics = [
        ("Received", count(value("received"), rates.get("received"))),
        ("Written", count(value("written"), rates.get("written"))),
        ("Dropped", problem(value("dropped"), "dark_orange")),
        ("Errors", problem(value("errors"), "red")),
        ("Queue", queue_bar(value("queue"), value("queue_maxsize"), report.get("backlog_high_watermark"))),
        ("Pending flushes", value("pending_flushes")),
        ("Batches", f"{format_value(value('write_batches'))}, last {format_value(value('last_batch_size'))}"),
        ("Write time", write_time),
        ("Started", format_time(value("start_time")) or None),
    ]

    backend = report.get("backend") or {}
    reachable = backend.get("reachable")
    if reachable is not None:
        reachable = Text("yes", style="green") if reachable else Text("no", style="red")
    setting = report.get  # the configuration of the hub
    database = [
        ("Backend", backend.get("name")),
        ("Reachable", reachable),
        ("Address", f"{backend['host']}:{backend['port']}" if backend.get("host") else None),
        ("Database", backend.get("database")),
        ("Table", f"{backend.get('table_name')} ({backend.get('schema')})" if backend.get("table_name") else None),
        ("Batch size", f"{format_value(setting('batch_size'))}, at most {format_value(setting('max_batch_size'))}"),
        ("Flush every", f"{format_value(setting('flush_interval'))} s"),
        ("Flushes at a time", setting("flush_concurrency")),
    ]
    return {
        "Metrics": key_values([(label, value) for label, value in metrics if value is not None]),
        "Database": key_values([(label, value) for label, value in database if value is not None]),
    }


LEVEL_COLOURS = {"WARNING": "dark_orange", "ERROR": "red", "CRITICAL": "bold red"}


def level_number(name: str) -> int:
    """The number of a level name, e.g. 30 for WARNING, 0 for a name that logging doesn't know."""
    number = logging.getLevelName(name)
    return number if isinstance(number, int) else 0


def log_summary(summary: Any) -> RenderableType | None:
    """The last warning or error of the logger: when, from where, and the message."""
    if not isinstance(summary, dict):
        return None
    return Group(
        Text.assemble(when(summary.get("time")) or "", (f"  {summary.get('process')} {summary.get('name')}", "dim")),
        Text(str(summary.get("message", "")), style=LEVEL_COLOURS.get(summary.get("level"), "")),
    )


def logger(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The logger: where it writes, at which levels, and what it received."""
    location = report.get("file_logger_location")
    path = Path(location) if location else None
    configuration = [
        ("Folder", str(path.parent) if path else None),
        ("File", path.name if path else None),
        ("File level", report.get("file_logger_level")),
        ("Console level", report.get("stream_logger_level")),
    ]
    sections = {"Logger": key_values([(label, value) for label, value in configuration if value is not None])}

    statistics = report.get("statistics")
    if not isinstance(statistics, dict):
        sections["Messages"] = Text(
            "This logger doesn't report statistics, restart it with the current version to see them.", style="dim"
        )
        return sections

    rates = RATES.update("log", epoch_timestamp(report), {"received": statistics.get("received")})
    levels = Text()
    by_level = sorted((statistics.get("levels") or {}).items(), key=lambda item: level_number(item[0]))
    for name, number in by_level:
        if levels:
            levels.append(", ")
        levels.append(f"{name} {number}", style=LEVEL_COLOURS.get(name, ""))
    messages = [
        ("Received", count(statistics.get("received"), rates.get("received"))),
        ("By level", levels or None),
        ("Last warning", log_summary(statistics.get("last_warning"))),
        ("Last error", log_summary(statistics.get("last_error"))),
        ("Started", format_time(statistics.get("start_time")) or None),
    ]
    sections["Messages"] = key_values([(label, value) for label, value in messages if value is not None])
    return sections


BUILTINS = {
    "reg": registry,
    "sm": storage,
    "cm": configuration_manager,
    "pm": process_manager,
    "log": logger,
    "nh": notification_hub,
    "mh": metrics_hub,
}
"""The built-in renderers by `cgse_object`."""
