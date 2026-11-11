"""Reads the log records of a time window from the log files of the logger, for its `history` command.

The logger writes all records to one file (`general.log`), which rotates at midnight into `general.log.YYYY-MM-DD`.
A line starts with the local time of the record, see `LOG_FORMAT_FILE` in `egse.logger.log_cs`:

    2026-11-10T07:14:47.869 [   DEBUG] [       rs_cs] <message> (<name>:<pid>:<package>:<file>:<line>)

A record with a multi-line message continues on the next lines, the part between brackets at the end is on its last
line; a traceback comes after that part. A line that doesn't start with a time belongs to the record above it.

The records are written in the order they arrive, with the time they were created in their process, so the times are
only about sorted. The start of a window is found with a binary search to `SLACK` seconds before it, and the records
are selected on their own time. A request returns at most a number of records and reads at most `MAX_BYTES`; the
answer then has a cursor to continue with.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SLACK = 10.0
"""Seconds that a record may arrive later than the records that were created after it."""

MAX_RECORDS = 5000
"""The default maximum number of records in one answer."""

MAX_BYTES = 8_000_000
"""The maximum number of bytes read for one answer, the logger doesn't handle other requests while it reads."""

MAX_MESSAGE_LENGTH = 4000
"""The message of a record is cut to this length, a traceback included."""

_RECORD_START = re.compile(rb"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3} \[")
_FIRST_LINE = re.compile(r"^(\S+) \[\s*([^\]]*)\] \[\s*([^\]]*)\] ?(.*)$", re.DOTALL)
_TRAILER = re.compile(r"^(.*) \(([^():\s]+):(\d+):([^():]*):([^():]+):(\d+)\)\s*$", re.DOTALL)
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
_SEARCH_BLOCK = 65536
"""The binary search stops when the interval is smaller, the rest is read line by line."""


def parse_time(line: bytes) -> float | None:
    """The time at the start of a line of the log file as a timestamp (local time), None when it's no first line."""
    if not _RECORD_START.match(line):
        return None
    try:
        return datetime.datetime.strptime(line[:23].decode("ascii"), _TIME_FORMAT).timestamp()
    except ValueError:
        return None


def parse_record(lines: list[str]) -> dict[str, Any] | None:
    """The record of the lines (the first line and its continuation lines) as a dictionary like those of the `tail`
    command of the logger: `time`, `level`, `name`, `module`, `process` and `message`, and `pid`, `filename` and
    `lineno`. None when the first line is not the start of a record."""
    match = _FIRST_LINE.match(lines[0].rstrip("\n"))
    if match is None:
        return None
    moment, level, process, rest = match.groups()
    try:
        moment = datetime.datetime.strptime(moment, _TIME_FORMAT).timestamp()
    except ValueError:
        return None
    text = [rest, *(line.rstrip("\n") for line in lines[1:])]
    record = dict(time=moment, level=level.strip(), name="", module="", process=process.strip(), message="")
    for index in range(len(text) - 1, -1, -1):  # the last line with the part between brackets, a traceback follows
        if trailer := _TRAILER.match(text[index]):
            message, name, pid, _package, filename, lineno = trailer.groups()
            text = [*text[:index], message, *text[index + 1 :]] if message else [*text[:index], *text[index + 1 :]]
            record.update(
                name=name, module=filename.removesuffix(".py"), pid=int(pid), filename=filename, lineno=int(lineno)
            )
            break
    record["message"] = "\n".join(text).rstrip()[:MAX_MESSAGE_LENGTH]
    return record


def log_files(location: Path, base_name: str) -> list[tuple[Path, float]]:
    """The log files with the time of their first record, oldest first: the rotated files and the current one.

    Files without records are left out. The order comes from the times of the first records, not from the names: a
    rotated file can have the records of more than one day when the logger was not running at midnight.
    """
    files = []
    for path in [*location.glob(f"{base_name}.*"), location / base_name]:
        if path.is_file() and (first := _first_time(path)) is not None:
            files.append((path, first))
    return sorted(files, key=lambda item: item[1])


def _first_time(path: Path) -> float | None:
    with path.open("rb") as file:
        for _ in range(100):  # a record with a long traceback, otherwise it's no log file
            line = file.readline()
            if not line:
                return None
            if (moment := parse_time(line)) is not None:
                return moment
    return None


def _seek_time(file, size: int, target: float) -> int:
    """The offset of a first line in the file near before the first record at or after `target`."""
    low, high = 0, size
    while high - low > _SEARCH_BLOCK:
        middle = (low + high) // 2
        file.seek(middle)
        file.readline()  # the rest of a line
        moment = None
        while moment is None:
            line = file.readline()
            if not line or file.tell() > high:
                break
            moment = parse_time(line)
        if moment is not None and moment < target:
            low = middle
        else:
            high = middle
    return low


def _lines(file, offset: int, at_record: bool) -> Iterator[tuple[int, bytes]]:
    """The lines from the first record at or after the offset, with the offset of each line. With `at_record` the
    offset is that of a first line, e.g. from a cursor."""
    file.seek(offset)
    if offset > 0 and not at_record:
        file.readline()  # the rest of a line
    position = file.tell()
    started = False
    for line in iter(file.readline, b""):
        started = started or _RECORD_START.match(line) is not None
        if started:
            yield position, line
        position += len(line)


def read_history(
    location: Path,
    base_name: str,
    since: float,
    until: float,
    max_records: int = MAX_RECORDS,
    cursor: str | None = None,
    max_bytes: int = MAX_BYTES,
) -> dict[str, Any]:
    """The records created between `since` and `until` (timestamps), oldest first as they are in the files.

    Args:
        location: the directory of the log files.
        base_name: the name of the current log file, e.g. `general.log`.
        since: the start of the window.
        until: the end of the window.
        max_records: the maximum number of records in the answer.
        cursor: where to continue, the `cursor` of the previous answer for the same window.
        max_bytes: the maximum number of bytes read.

    Returns:
        A dictionary with `records` (see `parse_record()`), and `cursor`: where to continue when there are more records
        in the window, None when the window is complete.

    Raises:
        ValueError: the cursor is not valid, e.g. its file was rotated.
    """
    files = log_files(location, base_name)
    selected = [
        path
        for index, (path, first) in enumerate(files)
        if first <= until and (index + 1 == len(files) or files[index + 1][1] >= since - SLACK)
    ]
    offset = None
    if cursor is not None:
        name, _, position = cursor.rpartition(":")
        names = [path.name for path in selected]
        if name not in names or not position.isdigit():
            raise ValueError(f"The cursor {cursor!r} is not valid for this window, the log file may have rotated.")
        selected = selected[names.index(name) :]
        offset = int(position)

    records: list[dict[str, Any]] = []
    read = 0

    def keep(lines: list[str]) -> bool:
        """Keeps the record of the lines when it's in the window; False when the window is complete."""
        record = parse_record(lines)
        if record is None:
            return True
        if since <= record["time"] <= until:
            records.append(record)
        return record["time"] <= until + SLACK

    for path in selected:
        with path.open("rb") as file:
            at_record = offset is not None
            if offset is None:
                offset = _seek_time(file, path.stat().st_size, since - SLACK)
            pending: list[str] = []
            for position, line in _lines(file, offset, at_record):
                if _RECORD_START.match(line):
                    if pending and not keep(pending):
                        return dict(records=records, cursor=None)
                    pending = []
                    if len(records) >= max_records or read >= max_bytes:
                        return dict(records=records, cursor=f"{path.name}:{position}")
                pending.append(line.decode("utf-8", errors="replace"))
                read += len(line)
            if pending and not keep(pending):
                return dict(records=records, cursor=None)
            offset = None
    return dict(records=records, cursor=None)
