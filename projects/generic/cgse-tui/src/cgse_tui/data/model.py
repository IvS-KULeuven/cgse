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

    registered: bool = False
    """True while the service is listed in the service registry."""

    registered_at: float | None = None
    """Time the TUI saw the registration, seconds since the epoch."""

    service_id: str | None = None
    """The identifier the registry gave to the registration."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """The metadata of the registration, e.g. extra ports like `pub_port`."""

    last_heartbeat: float | None = None
    """Time of the last heartbeat according to the registry, seconds since the epoch."""

    ttl: int | None = None
    """Seconds without heartbeat after which the registry considers the service unhealthy."""

    health: str | None = None
    """Health according to the registry: "passing" or "critical"."""

    port: int | None = None
    service_port: int | None = None
    monitoring_port: int | None = None

    pid: int | None = None
    start_time: float | None = None
    """Start of the process, seconds since the epoch."""
    uptime_s: float | None = None
    cpu_percent: float | None = None
    cpu_user_s: float | None = None
    cpu_system_s: float | None = None
    rss: int | None = None
    uss: int | None = None

    device_id: str | None = None

    connected: bool | None = None
    """Device connection, None for services without a device or when this is not known."""

    sim_mode: bool | None = None

    has_device: bool | None = None
    """False when the status report says the service controls no device, None when this is not known."""

    last_update: float | None = None
    """Time of the last information, seconds since the epoch."""

    stale_after: float = 5.0
    """Seconds without new information after which the service is shown as stale."""

    report: dict[str, Any] = field(default_factory=dict)
    """The last status report, shown in the detail screen."""
