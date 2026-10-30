"""The service information that is shown in the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any


class ServiceState(str, Enum):
    """The state of a service as seen by the TUI."""

    OK = "ok"
    """The service answered its last request or published on its monitoring port in time."""

    INACTIVE = "inactive"
    """The service is known, e.g. a core service from the entry points, but it is not running."""

    UNKNOWN = "unknown"
    """No information has been received yet."""

    STALE = "stale"
    """The last information is too old: the service is gone or busy with a long command."""


@dataclass
class ServiceInfo:
    """One service, as a row in the overview and the content of the detail screen."""

    name: str
    service_type: str
    host: str | None = None
    state: ServiceState = ServiceState.UNKNOWN
    server_kind: str | None = None
    """Taken from the registry metadata: "sync", "async", or None for the custom servers."""

    pid: int | None = None
    uptime_s: float | None = None
    cpu_percent: float | None = None
    rss: int | None = None

    connected: bool | None = None
    """Device connection, None for services without a device or when this is not known."""

    sim_mode: bool | None = None

    last_update: float | None = None
    """Time of the last information, seconds since the epoch."""

    report: dict[str, Any] = field(default_factory=dict)
    """The last status report, shown in the detail screen."""
