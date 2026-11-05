"""The last log lines in the detail screen of the logger.

The logger keeps its most recent records in memory and returns those after a given sequence number with its `tail`
command, see `egse.logger.log_cs`. The detail screen asks for the new records every `TAIL_INTERVAL` seconds while it
is open, and appends them to a `RichLog`.
"""

from __future__ import annotations

import time
from typing import Any

from rich.text import Text

TAIL_INTERVAL = 2.0
"""Seconds between two requests for new log records."""

FIRST_LINES = 200
"""Number of records requested when the screen opens."""

MAX_LINES = 1000
"""Number of lines kept in the log panel."""

LEVEL_STYLES = {"DEBUG": "dim", "WARNING": "dark_orange", "ERROR": "red", "CRITICAL": "bold red"}


def format_record(record: dict[str, Any]) -> Text:
    """One log record as a line: time, level, process and logger name, and the message coloured by level."""
    level = str(record.get("level", ""))
    moment = record.get("time")
    clock = time.strftime("%H:%M:%S", time.localtime(moment)) if isinstance(moment, (int, float)) else "--:--:--"
    style = LEVEL_STYLES.get(level, "")
    return Text.assemble(
        (clock, "dim"),
        " ",
        (f"{level:<8}", style or "bold"),
        " ",
        (f"{record.get('process', '')} {record.get('name', '')}", "cyan"),
        " ",
        (str(record.get("message", "")), style),
    )
