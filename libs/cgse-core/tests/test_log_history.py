"""Tests for reading a time window from the log files of the logger, see `egse.logger.history`."""

import datetime
import os
import types

import pytest

from egse.logger import history
from egse.logger import log_cs
from egse.logger.history import log_files
from egse.logger.history import parse_record
from egse.logger.history import read_history


def at(hour, minute=0, second=0.0, day=9):
    moment = datetime.datetime(2026, 11, day, hour, minute) + datetime.timedelta(seconds=second)
    return moment.timestamp()


def line(moment, message="message", level="INFO", process="cm_cs", name="egse.x", filename="x.py"):
    stamp = datetime.datetime.fromtimestamp(moment).strftime("%Y-%m-%dT%H:%M:%S.%f")[:23]
    return f"{stamp} [{level:>8s}] [{process:>12s}] {message} ({name}:1234:egse:{filename}:42)\n"


def write(path, lines, mtime=None):
    path.write_text("".join(lines))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_parse_record():
    record = parse_record([line(at(14), "Started.", "WARNING", "sm_cs", "egse.storage", "storage.py")])
    assert record == dict(
        time=at(14),
        level="WARNING",
        name="egse.storage",
        module="storage",
        process="sm_cs",
        message="Started.",
        pid=1234,
        filename="storage.py",
        lineno=42,
    )
    assert parse_record(["no log line\n"]) is None


def test_parse_record_with_more_lines():
    # A message of more lines: the part between brackets is on the last line.
    first = line(at(14), "Could not reach the CM.").replace(" (egse.x:1234:egse:x.py:42)", "")
    record = parse_record([first, "\n", "Check it (twice).\n", " (egse:99:egse:_setup_core.py:39)\n"])
    assert record["message"] == "Could not reach the CM.\n\nCheck it (twice)."
    assert (record["name"], record["module"], record["lineno"]) == ("egse", "_setup_core", 39)

    # A traceback comes after the part between brackets.
    lines = [line(at(14), "Task failed: oops"), "Traceback (most recent call last):\n", "ValueError: oops\n"]
    record = parse_record(lines)
    assert record["message"] == "Task failed: oops\nTraceback (most recent call last):\nValueError: oops"
    assert record["name"] == "egse.x"


def test_parse_record_message_with_brackets():
    record = parse_record([line(at(14), "value (a:1:b:c:2) in the message")])
    assert record["message"] == "value (a:1:b:c:2) in the message"
    assert record["name"] == "egse.x"


def test_window_with_late_records(tmp_path):
    lines = [line(at(13, 59, s)) for s in range(0, 60, 5)]
    lines += [line(at(14, 0, 1), "late"), line(at(13, 59, 58), "arrived late")]  # created before the window
    lines += [line(at(14, m), f"at {m}") for m in range(1, 30)]
    lines += [line(at(14, 30, 5), "after the window, arrived late"), line(at(14, 29, 59), "late, in the window")]
    write(tmp_path / "general.log", lines)

    records = read_history(tmp_path, "general.log", at(14), at(14, 30))["records"]
    messages = [r["message"] for r in records]
    assert messages[0] == "late"
    assert "arrived late" not in messages
    assert messages[-1] == "late, in the window"
    assert len(records) == 1 + 29 + 1


def test_window_in_a_large_file(tmp_path):
    # Large enough for the binary search, with continuation lines.
    lines = []
    for second in range(0, 6 * 3600, 2):
        lines.append(line(at(8, 0, second), f"record {second}"))
        if second % 100 == 0:
            lines += ["Traceback (most recent call last):\n", "ValueError: x\n"]
    write(tmp_path / "general.log", lines)
    assert (tmp_path / "general.log").stat().st_size > 10 * 65536

    answer = read_history(tmp_path, "general.log", at(10), at(10, 1))
    assert [r["message"].split("\n")[0] for r in answer["records"]] == [f"record {s}" for s in range(7200, 7262, 2)]
    assert answer["cursor"] is None


def test_window_across_midnight(tmp_path):
    write(tmp_path / "general.log.2026-11-08", [line(at(23, m, day=8), f"8 {m}") for m in range(0, 60, 10)])
    write(tmp_path / "general.log.2026-11-07", [line(at(10, day=7), "7")])
    write(tmp_path / "general.log", [line(at(0, m), f"9 {m}") for m in range(0, 60, 10)])
    write(tmp_path / "general.log.2026-11-06", [])  # no records

    assert [path.name for path, _ in log_files(tmp_path, "general.log")] == [
        "general.log.2026-11-07",
        "general.log.2026-11-08",
        "general.log",
    ]
    records = read_history(tmp_path, "general.log", at(23, 30, day=8), at(0, 30))["records"]
    assert [r["message"] for r in records] == ["8 30", "8 40", "8 50", "9 0", "9 10", "9 20", "9 30"]


def test_pages_with_a_cursor(tmp_path):
    write(tmp_path / "general.log.2026-11-08", [line(at(23, 59, s, day=8), f"8 {s}") for s in range(50, 60)])
    write(tmp_path / "general.log", [line(at(0, 0, s), f"9 {s}") for s in range(10)])
    since, until = at(23, 59, 52, day=8), at(0, 0, 5)

    messages, cursor, pages = [], None, 0
    while True:
        answer = read_history(tmp_path, "general.log", since, until, max_records=3, cursor=cursor)
        assert len(answer["records"]) <= 3
        messages += [r["message"] for r in answer["records"]]
        cursor, pages = answer["cursor"], pages + 1
        if cursor is None:
            break
    assert messages == [f"8 {s}" for s in range(52, 60)] + [f"9 {s}" for s in range(6)]
    assert pages >= 5

    with pytest.raises(ValueError, match="not valid"):
        read_history(tmp_path, "general.log", since, until, cursor="general.log.2026-11-01:0")


def test_max_bytes(tmp_path):
    write(tmp_path / "general.log", [line(at(14, 0, s)) for s in range(30)])
    answer = read_history(tmp_path, "general.log", at(14), at(15), max_bytes=500)
    assert 0 < len(answer["records"]) < 30
    assert answer["cursor"].startswith("general.log:")


def test_history_command(tmp_path, monkeypatch):
    write(tmp_path / "general.log", [line(at(14, m), f"at {m}") for m in range(10)])
    monkeypatch.setattr(log_cs, "file_handler", types.SimpleNamespace(baseFilename=str(tmp_path / "general.log")))

    answer = log_cs.handle_command(f"history {at(14, 2)} {at(14, 5)}")
    assert answer["status"] == "ACK"
    assert [r["message"] for r in answer["records"]] == ["at 2", "at 3", "at 4", "at 5"]
    assert answer["cursor"] is None

    answer = log_cs.handle_command(f"history {at(14)} {at(15)} 4")
    assert len(answer["records"]) == 4 and answer["cursor"]
    answer = log_cs.handle_command(f"history {at(14)} {at(15)} 4 {answer['cursor']}")
    assert [r["message"] for r in answer["records"]] == ["at 4", "at 5", "at 6", "at 7"]

    assert log_cs.handle_command("history yesterday")["status"] == "NACK"
    assert log_cs.handle_command(f"history {at(14)} {at(15)} 4 nofile:0")["status"] == "NACK"
    assert history.MAX_RECORDS > 0
