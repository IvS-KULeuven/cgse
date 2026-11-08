"""The service information that is shown in the TUI."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any

SAMPLES_KEPT = 900.0
"""Seconds of process samples kept per service, for `cgse_tui.data.health`."""

MAX_SAMPLES = 5000
"""Maximum number of process samples kept per service, for a service that publishes very often."""


class Level(str, Enum):
    """How the CPU or memory use of a process is judged, see `cgse_tui.data.health`."""

    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


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

    cgse_object: str | None = None
    """The `cgse <object>` command that starts, stops and shows the status of the service, e.g. "puna"."""

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
    swap: int | None = None
    """Memory of the process that is swapped out [bytes], None when the service doesn't report it (older versions)."""

    device_id: str | None = None

    setup_path: str | None = None
    """Where the device driver is in the Setup, e.g. "gse.DAQ6510", None when it is not in the Setup."""

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

    monitoring: dict[str, Any] = field(default_factory=dict)
    """The last message on the monitoring port of a control server, with the live values of the device."""

    samples: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    """(time, pid, cpu %, memory) of the process, oldest first, of the last `SAMPLES_KEPT` seconds. The memory is the
    RSS plus the swapped-out memory, see `memory`."""

    cpu_level: Level = Level.OK
    cpu_reason: str = ""
    """Why the CPU level is not ok, e.g. "average CPU 95 % over the last 60 s"."""

    memory_level: Level = Level.OK
    memory_reason: str = ""
    """Why the memory level is not ok, e.g. "memory grew 30 % in 10 min (40.0 → 52.0 MiB), a leak?"."""

    @property
    def memory(self) -> int | None:
        """The memory of the process: the RSS plus what is swapped out. A leak ends up in swap, the RSS alone can even
        go down while the memory grows. Only the RSS for a service that doesn't report its swap."""
        if self.rss is None:
            return None
        return self.rss + (self.swap or 0)

    def add_sample(self, now: float) -> None:
        """Adds the current CPU % and memory to the samples; a new process (PID) starts with new samples."""
        if self.cpu_percent is None and self.rss is None:
            return
        if self.samples and self.samples[-1][1] != self.pid:
            self.samples.clear()
        self.samples.append((now, self.pid, self.cpu_percent, self.memory))
        while self.samples and now - self.samples[0][0] > SAMPLES_KEPT:
            self.samples.popleft()
