"""Judges the process of a service: does it use too much CPU, or does its memory keep growing (a leak)?

The collector keeps the process samples of every service (`ServiceInfo.samples`) and calls `assess()` on every
snapshot. The screens show the CPU and memory numbers in orange for a warning and in red when critical.

- CPU: the average CPU % over the last `CPU_WINDOW` seconds, so a short peak doesn't count.
- Memory: the growth of the RSS over the last `MEMORY_WINDOW` seconds, the median of the last quarter of the samples
  compared to the median of the first quarter. Only judged when the samples cover at least `MIN_COVERAGE` of the
  window, so the growth while a process starts is not taken for a leak, and a memory that stops growing is ok again
  after one window. The RSS is used because every service reports it, also the registry, logger and hubs.
"""

from __future__ import annotations

import statistics

from cgse_tui.data.model import Level
from cgse_tui.data.model import ServiceInfo

CPU_WINDOW = 60.0
"""Seconds over which the CPU % is averaged."""

CPU_WARNING, CPU_CRITICAL = 50.0, 90.0
"""Average CPU % for a warning and for critical. A process with several threads can use more than 100 %."""

MEMORY_WINDOW = 600.0
"""Seconds over which the growth of the memory is judged."""

MEMORY_WARNING, MEMORY_CRITICAL = 0.10, 0.25
"""Relative growth of the RSS within `MEMORY_WINDOW` for a warning and for critical."""

MIN_COVERAGE = 0.5
"""Part of a window that the samples have to cover before it is judged."""


def assess(service: ServiceInfo, now: float) -> None:
    """Sets the CPU and memory level and reason of the service from its samples."""
    service.cpu_level, service.cpu_reason = cpu_level(service.samples, now)
    service.memory_level, service.memory_reason = memory_level(service.samples, now)


def _window(samples, now: float, window: float) -> list[tuple[float, float]]:
    return [(t, value) for t, value in samples if value is not None and now - t <= window]


def cpu_level(samples, now: float) -> tuple[Level, str]:
    """The level of the CPU from (time, pid, cpu %, rss) samples, and the reason when it isn't ok."""
    values = _window(((t, cpu) for t, _, cpu, _ in samples), now, CPU_WINDOW)
    if len(values) < 2 or values[-1][0] - values[0][0] < MIN_COVERAGE * CPU_WINDOW:
        return Level.OK, ""
    average = statistics.fmean(value for _, value in values)
    level = Level.CRITICAL if average >= CPU_CRITICAL else Level.WARNING if average >= CPU_WARNING else Level.OK
    reason = f"average CPU {average:.0f} % over the last {values[-1][0] - values[0][0]:.0f} s"
    return level, "" if level is Level.OK else reason


def memory_level(samples, now: float) -> tuple[Level, str]:
    """The level of the memory from (time, pid, cpu %, rss) samples, and the reason when it isn't ok."""
    values = _window(((t, rss) for t, _, _, rss in samples), now, MEMORY_WINDOW)
    if len(values) < 8:
        return Level.OK, ""
    start, end = values[0][0], values[-1][0]
    span = end - start
    if span < MIN_COVERAGE * MEMORY_WINDOW:
        return Level.OK, ""
    first = statistics.median(value for t, value in values if t <= start + span / 4)
    last = statistics.median(value for t, value in values if t >= end - span / 4)
    if first <= 0:
        return Level.OK, ""
    growth = last / first - 1
    level = Level.CRITICAL if growth >= MEMORY_CRITICAL else Level.WARNING if growth >= MEMORY_WARNING else Level.OK
    reason = f"memory grew {growth:.0%} in {span / 60:.0f} min ({first / 2**20:.1f} → {last / 2**20:.1f} MiB), a leak?"
    return level, "" if level is Level.OK else reason
