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
