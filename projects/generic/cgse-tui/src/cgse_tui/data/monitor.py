"""Follows a control server on its monitoring port.

Sync and async control servers publish their status on the monitoring port, by default every second, as one pickled
dictionary per message. A sync control server publishes the device protocol's `get_status()`, with the process
information at the top level. An async control server publishes `get_status()`, with the process information in a
`process` section. Both use the keys of `ProcessStatus.as_dict()`.
"""

from __future__ import annotations

import logging
import pickle
from collections.abc import Callable
from typing import Any

import zmq
import zmq.asyncio

logger = logging.getLogger("cgse_tui.monitor")


def process_fields(status: dict[str, Any]) -> dict[str, Any]:
    """Returns the process information and the publish interval from a monitoring message."""
    process = status.get("process", status)
    delay = status.get("delay")

    return {
        "pid": process.get("PID"),
        "uptime_s": process.get("Up"),
        "cpu_percent": process.get("CPU%"),
        "cpu_user_s": process.get("CPU User"),
        "cpu_system_s": process.get("CPU System"),
        "rss": process.get("RSS"),
        "uss": process.get("USS"),
        "interval_s": delay / 1000 if isinstance(delay, (int, float)) else None,
    }


MONITORING_KEYS = {"schema_version", "timestamp", "delay", "control_server", "process"}
"""Keys of a monitoring message that are not device values."""

PROCESS_KEYS = {"PID", "Up", "UUID", "RSS", "USS", "CPU User", "CPU System", "CPU count", "CPU%"}
"""Keys of `ProcessStatus.as_dict()`, at the top level of the monitoring message of a sync control server."""


def live_values(status: dict[str, Any]) -> dict[str, Any]:
    """Returns the device values from a monitoring message, without the process information.

    A sync control server adds the device values to its status, e.g. the positions of a hexapod. An async control
    server has them in its `components` section, which is returned without the section: these are the same values as
    the `details` of the status report.
    """
    values = {key: value for key, value in status.items() if key not in MONITORING_KEYS | PROCESS_KEYS}
    if set(values) == {"components"} and isinstance(values["components"], dict):
        return values["components"]
    return values


async def subscribe(endpoint: str, on_status: Callable[[dict[str, Any]], None]) -> None:
    """Passes every monitoring message from the given endpoint to `on_status`, until the task is cancelled."""
    socket = zmq.asyncio.Context.instance().socket(zmq.SUB)
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(endpoint)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    try:
        while True:
            message = await socket.recv()
            try:
                status = pickle.loads(message)
            except Exception as exc:
                logger.warning(f"Couldn't unpickle a monitoring message from {endpoint}: {type(exc).__name__}: {exc}")
                continue
            if isinstance(status, dict):
                on_status(status)
    finally:
        socket.close(linger=0)
