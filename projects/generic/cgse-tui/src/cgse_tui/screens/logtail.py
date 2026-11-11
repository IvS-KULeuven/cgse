"""The last log lines in the detail screen of the logger.

The logger keeps its most recent records in memory and returns those after a given sequence number with its `tail`
command, see `egse.logger.log_cs`. The detail screen asks for the new records every `TAIL_INTERVAL` seconds while it
is open, and appends them to a `RichLog`.

The screen keeps the records it received, at most `MAX_LINES`, and shows those that pass a `LogFilter`: on levels,
process, logger or module, message text and a time range. Only the records the logger still keeps in memory can be
filtered, the log file is not read.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
import time
from typing import Any

from rich.text import Text

TAIL_INTERVAL = 2.0
"""Seconds between two requests for new log records."""

MAX_LINES = 1000
"""Number of records kept in the log panel, also requested when the screen opens: the filter covers all of them."""

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

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


_RELATIVE_TIME = re.compile(r"^(\d+(?:\.\d+)?)\s*([smhd])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_TIME_FORMATS = ("%H:%M", "%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S")


def parse_time(text: str, now: float | None = None) -> float | None:
    """The moment in a time filter as a timestamp, None for an empty text.

    Accepted: a local time `HH:MM[:SS]` (today), a local date and time `YYYY-MM-DD HH:MM[:SS]`, or a time ago, e.g.
    `30s`, `15m`, `2h` or `1d`.

    Raises:
        ValueError: the text is none of these.
    """
    text = text.strip()
    if not text:
        return None
    now = time.time() if now is None else now
    if match := _RELATIVE_TIME.match(text):
        return now - float(match[1]) * _UNITS[match[2]]
    for time_format in _TIME_FORMATS:
        try:
            moment = datetime.datetime.strptime(text, time_format)
        except ValueError:
            continue
        if "%Y" not in time_format:
            moment = datetime.datetime.combine(datetime.datetime.fromtimestamp(now).date(), moment.time())
        return moment.timestamp()
    raise ValueError(f"{text!r} is not a time: use HH:MM[:SS], YYYY-MM-DD HH:MM[:SS], or a time ago like 15m or 2h")


def _patterns(text: str) -> tuple[list[str], list[str]]:
    """The comma separated words of a filter field in lower case: those to include and those to exclude (`!word`)."""
    words = [word.strip().lower() for word in text.split(",") if word.strip()]
    return [w for w in words if not w.startswith("!")], [w[1:] for w in words if w.startswith("!") and w[1:]]


def _matches(text: str, values: list[str]) -> bool:
    """True when the field text matches the values: one of the included words, and none of the excluded words."""
    included, excluded = _patterns(text)
    values = [value.lower() for value in values]
    if included and not any(word in value for word in included for value in values):
        return False
    return not any(word in value for word in excluded for value in values)


def selects_logger(selected: frozenset[str], name: str) -> bool:
    """True when the logger name is selected: one of the names, below one of them, or one of the `=name`s."""
    return f"={name}" in selected or any(name == s or name.startswith(f"{s}.") for s in selected)


@dataclasses.dataclass(frozen=True)
class LogFilter:
    """Which log records are shown.

    The text fields hold comma separated words, a record passes when it contains one of the words (case is ignored),
    and none of the words with a `!` in front, e.g. `cm_cs, sm_cs` or `!egse.zmq`. An empty field passes all records.

    Attributes:
        levels: the level names that are shown, all levels when empty.
        process: words of the process name, e.g. `cm_cs`.
        module: words of the logger name or the module (the file name without `.py`).
        message: words of the message.
        since: the text of the start of the time range, see `parse_time()`.
        until: the text of the end of the time range.
        dim: the records that don't pass are shown dimmed instead of left out, they keep the context.
        hide_debug: DEBUG records are left out, also when they pass or would be dimmed, see `hides()`.
        loggers: the selected loggers, a record passes when its logger is one of them or below one of them (`egse`
            selects `egse.hexapod` too); a name with `=` in front selects that logger only, e.g. `=egse`. All
            loggers when empty. The selection in the tree of the log screen, see `cgse_tui.screens.log_screen`.
        processes: the selected process names, exact; all processes when empty. The selection in the Processes pane
            of the log screen.
    """

    levels: frozenset[str] = frozenset()
    process: str = ""
    module: str = ""
    message: str = ""
    since: str = ""
    until: str = ""
    dim: bool = False
    hide_debug: bool = False
    loggers: frozenset[str] = frozenset()
    processes: frozenset[str] = frozenset()

    @property
    def active(self) -> bool:
        """True when the filter leaves out (or dims) records on its criteria, `dim` and `hide_debug` don't count."""
        return dataclasses.replace(self, dim=False, hide_debug=False) != LogFilter()

    def hides(self, record: dict[str, Any]) -> bool:
        """True for a record that is left out whatever the other criteria: a DEBUG record with `hide_debug`."""
        return self.hide_debug and record.get("level") == "DEBUG"

    def validate(self) -> None:
        """Raises a ValueError when a time in the time range can't be read."""
        parse_time(self.since)
        parse_time(self.until)

    def matcher(self, now: float | None = None):
        """A function that tells whether a record passes the filter, with the time range taken at `now`."""
        since, until = parse_time(self.since, now), parse_time(self.until, now)

        def matches(record: dict[str, Any]) -> bool:
            if self.levels and str(record.get("level", "")) not in self.levels:
                return False
            moment = record.get("time")
            if since is not None or until is not None:
                if not isinstance(moment, (int, float)):
                    return False
                if (since is not None and moment < since) or (until is not None and moment > until):
                    return False
            if self.loggers and not selects_logger(self.loggers, str(record.get("name", ""))):
                return False
            if self.processes and str(record.get("process", "")) not in self.processes:
                return False
            if self.process and not _matches(self.process, [str(record.get("process", ""))]):
                return False
            if self.module and not _matches(self.module, [str(record.get("name", "")), str(record.get("module", ""))]):
                return False
            return not self.message or _matches(self.message, [str(record.get("message", ""))])

        return matches

    def describe(self) -> str:
        """The filter in a few words, for the border of the log panel."""
        parts = []
        if self.levels:
            parts.append("/".join(level for level in LEVELS if level in self.levels) or ",".join(sorted(self.levels)))
        for label, value in (("process", self.process), ("module", self.module), ("message", self.message)):
            if value.strip():
                parts.append(f"{label} {value.strip()}")
        if self.loggers:
            parts.append(f"loggers {', '.join(sorted(self.loggers))}")
        if self.processes:
            parts.append(f"processes {', '.join(sorted(self.processes))}")
        if self.since.strip() or self.until.strip():
            parts.append(f"time {self.since.strip() or '…'} – {self.until.strip() or 'now'}")
        return "; ".join(parts)
