"""The columns of the overview table: all the information the TUI has about a service.

Each column takes its value from a `ServiceInfo`. The user selects the columns that are shown (key `o` in the
overview), the columns with `default=True` are shown at start-up. The Name column is always shown.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from rich.text import Text

from cgse_tui.data.model import ServiceInfo

NOT_APPLICABLE = "–"
"""Shown in the device columns of a service that controls no device. An empty cell means: not known."""


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    value: Callable[[ServiceInfo, float], str]
    """Returns the cell text for a service, at the given time (seconds since the epoch)."""
    description: str
    default: bool = False
    justify: str = "left"
    """"right" for numbers, so the digits line up."""

    def header(self) -> Text:
        return Text(self.label, justify=self.justify)

    def cell(self, service: ServiceInfo, now: float) -> Text:
        return Text(self.value(service, now), justify=self.justify)


def format_uptime(seconds: float | None) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}" if days else f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_mib(value: int | None) -> str:
    """Bytes in MiB with one decimal, the unit is in the column header."""
    return "" if value is None else f"{value / 2**20:.1f}"


def format_flag(value: bool | None, true: str, false: str) -> str:
    return "" if value is None else (true if value else false)


def format_time(timestamp: float | None) -> str:
    """Local date and time of a timestamp in seconds since the epoch."""
    if timestamp is None:
        return ""
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_age(timestamp: float | None, now: float) -> str:
    """Seconds between a timestamp and now, e.g. "3 s" or "00:05:12"."""
    if timestamp is None:
        return ""
    age = max(0.0, now - timestamp)
    return f"{age:.0f} s" if age < 60 else format_uptime(age)


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return ""
    return f"{seconds:.1f} s" if seconds < 60 else format_uptime(seconds)


def format_number(value: Any) -> str:
    return "" if value is None else str(value)


def cpu_time(service: ServiceInfo) -> float | None:
    if service.cpu_user_s is None and service.cpu_system_s is None:
        return None
    return (service.cpu_user_s or 0.0) + (service.cpu_system_s or 0.0)


def device_value(service: ServiceInfo, value: str) -> str:
    return NOT_APPLICABLE if service.has_device is False else value


def report_details(service: ServiceInfo) -> dict[str, Any]:
    details = service.report.get("details")
    return details if isinstance(details, dict) else {}


def setup_id(service: ServiceInfo) -> Any:
    """The Setup in the status details: `setup_id` of the Configuration Manager, `loaded_setup_id` of the SM."""
    details = report_details(service)
    return details.get("setup_id", details.get("loaded_setup_id"))


def statistic(*keys: str) -> Callable[[ServiceInfo, float], str]:
    """Value from the statistics in the status of a hub: the first of the given keys that is present.

    The notification hub counts `events_received` and `events_published`, the metrics hub `received`, `written`,
    `dropped` and has the queue size in `queue`.
    """

    def value(service: ServiceInfo, now: float) -> str:
        statistics = service.report.get("statistics")
        if not isinstance(statistics, dict):
            return ""
        return next((format_number(statistics[key]) for key in keys if key in statistics), "")

    return value


EXTRA_PORTS_IGNORED = {"service_port", "monitoring_port"}
"""Ports that have their own column."""


def other_ports(service: ServiceInfo, now: float) -> str:
    """The ports in the metadata of the registration that have no column, e.g. "pub 6201, collector 6202".

    The registry doesn't register itself, its ports come from its status.
    """
    sources = [service.metadata]
    if service.service_type == "SERVICE_REGISTRY":
        sources.append(service.report)
    ports = {}
    for source in sources:
        for key, port in source.items():
            if key.endswith("_port") and key not in EXTRA_PORTS_IGNORED and port and port != service.port:
                ports.setdefault(port, key.removesuffix("_port"))
    return ", ".join(f"{name} {port}" for port, name in ports.items())


COLUMNS: tuple[Column, ...] = (
    Column("name", "Name", lambda s, now: s.name, "Name of the service", default=True),
    Column("type", "Type", lambda s, now: s.service_type, "Service type in the registry", default=True),
    Column(
        "command",
        "Command",
        lambda s, now: f"cgse {s.cgse_object}" if s.cgse_object else "",
        "The cgse command that starts and stops the service",
    ),
    Column("kind", "Kind", lambda s, now: s.server_kind or "", "How the TUI asks for the status (server_kind)"),
    Column("host", "Host", lambda s, now: s.host or "", "Host (IP address) of the registration", default=True),
    Column("port", "Port", lambda s, now: format_number(s.port), "Commanding port, or requests port of a hub"),
    Column("service_port", "Service port", lambda s, now: format_number(s.service_port), "Service commanding port"),
    Column("monitoring_port", "Mon. port", lambda s, now: format_number(s.monitoring_port), "Monitoring port"),
    Column("other_ports", "Other ports", other_ports, "Other ports, e.g. publisher and collector of a hub"),
    Column("state", "State", lambda s, now: s.state.value, "State as seen by the TUI", default=True),
    Column(
        "uptime",
        "Uptime",
        lambda s, now: format_uptime(s.uptime_s),
        "Uptime of the process",
        default=True,
        justify="right",
    ),
    Column("started", "Started", lambda s, now: format_time(s.start_time), "Start time of the process"),
    Column("pid", "PID", lambda s, now: format_number(s.pid), "Process identifier", default=True, justify="right"),
    Column(
        "cpu",
        "CPU %",
        lambda s, now: "" if s.cpu_percent is None else f"{s.cpu_percent:.1f}",
        "CPU usage of the process",
        default=True,
        justify="right",
    ),
    Column(
        "cpu_time",
        "CPU time",
        lambda s, now: format_seconds(cpu_time(s)),
        "CPU time, user plus system",
        justify="right",
    ),
    Column(
        "memory",
        "Mem [MiB]",
        lambda s, now: format_mib(s.rss),
        "Resident memory (RSS)",
        default=True,
        justify="right",
    ),
    Column("uss", "USS [MiB]", lambda s, now: format_mib(s.uss), "Memory unique to the process (USS)", justify="right"),
    Column(
        "device_id",
        "Device ID",
        lambda s, now: device_value(s, s.device_id or ""),
        "Identifier of the controlled device",
        default=True,
    ),
    Column(
        "device",
        "Device",
        lambda s, now: device_value(s, format_flag(s.connected, "connected", "not connected")),
        "Connection with the device",
        default=True,
    ),
    Column(
        "simulator",
        "Simulator",
        lambda s, now: device_value(s, format_flag(s.sim_mode, "yes", "no")),
        "The control server talks to a simulator",
        default=True,
    ),
    Column("setup", "Setup", lambda s, now: format_number(setup_id(s)), "Loaded Setup (CM, SM)"),
    Column(
        "obsid", "Obsid", lambda s, now: format_number(report_details(s).get("obsid")), "Running observation (CM, SM)"
    ),
    Column("site", "Site", lambda s, now: format_number(report_details(s).get("site_id")), "Site identifier (CM)"),
    Column(
        "received",
        "Received",
        statistic("events_received", "received"),
        "Events or metrics received (hubs)",
        justify="right",
    ),
    Column(
        "sent",
        "Sent",
        statistic("events_published", "written"),
        "Events published, metrics written (hubs)",
        justify="right",
    ),
    Column("dropped", "Dropped", statistic("dropped"), "Metrics dropped (metrics hub)", justify="right"),
    Column("queue", "Queue", statistic("queue"), "Metrics waiting to be written (metrics hub)", justify="right"),
    Column(
        "heartbeat",
        "Heartbeat",
        lambda s, now: format_age(s.last_heartbeat, now),
        "Age of the last heartbeat",
        justify="right",
    ),
    Column("health", "Health", lambda s, now: s.health or "", "Health according to the registry"),
    Column(
        "ttl",
        "TTL",
        lambda s, now: format_number(s.ttl),
        "Registry time-to-live without heartbeat [s]",
        justify="right",
    ),
    Column(
        "updated",
        "Updated",
        lambda s, now: format_age(s.last_update, now),
        "Age of the last status in the TUI",
        justify="right",
    ),
    Column(
        "stale_after",
        "Stale after",
        lambda s, now: f"{s.stale_after:.0f} s",
        "Stale without status for",
        justify="right",
    ),
    Column("registered", "Registered", lambda s, now: format_time(s.registered_at), "When the TUI saw it register"),
    Column("service_id", "Service ID", lambda s, now: s.service_id or "", "Identifier of the registration"),
)

COLUMNS_BY_KEY = {column.key: column for column in COLUMNS}

REQUIRED_COLUMNS = ("name",)
"""Always shown: the rows are sorted by name."""

DEFAULT_COLUMNS = tuple(column.key for column in COLUMNS if column.default)


def visible_columns(keys) -> list[Column]:
    """The columns for the given keys in table order, with the required columns."""
    selected = set(keys) | set(REQUIRED_COLUMNS)
    return [column for column in COLUMNS if column.key in selected]
