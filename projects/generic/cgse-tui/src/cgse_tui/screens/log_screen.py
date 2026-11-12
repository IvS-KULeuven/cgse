"""The log screen: the log messages of a time window, read from the log files by the logger.

The logger reads the records of the window from its own log files with its `history` command, see
`egse.logger.history`, so the TUI can run on another machine. The screen asks for them in pages of `PAGE_RECORDS`,
at most `MAX_RECORDS` for a window.

The window moves back and forward by its own length (`[`, `]`) or by a day (`p`, `n`), `-` and `+` make it shorter
or longer, `g` goes to a given time and `t` to the latest window, which ends now. The tree at the left has the
loggers of the records in the window, with the number of records; `space` selects a logger and the loggers below it,
only their records are shown then. Below it the processes that logged the records, `space` selects a process in the
same way; with loggers and processes selected, a record must be of both. `f` filters the records further, see
`cgse_tui.screens.logtail.LogFilter`.

The latest window is live: after the records from the files, the screen asks the logger for the new records with its
`tail` command every `TAIL_INTERVAL` seconds, as the log panel of the logger does, and the window moves with the
time. The `tail` position is taken before the files are read; the records that are in both are only shown once.
"""

from __future__ import annotations

import collections
import dataclasses
import time
from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Iterator
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Input
from textual.widgets import Static
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.report import request_log_history
from cgse_tui.data.report import request_log_tail
from cgse_tui.screens.log_filter import LogFilterScreen
from cgse_tui.screens.logtail import TAIL_INTERVAL
from cgse_tui.screens.logtail import LogFilter
from cgse_tui.screens.logtail import parse_time
from cgse_tui.screens.logtail import selects_logger
from cgse_tui.screens.logview import FOLLOW_HINT
from cgse_tui.screens.record_view import RecordView

SPANS = (300, 900, 1800, 3600, 3 * 3600, 6 * 3600, 12 * 3600, 86400)
"""The lengths of the window in seconds, `-` and `+` select the previous and the next."""

DEFAULT_SPAN = 3600

PAGE_RECORDS = 5000
"""The number of records asked for in one request."""

MAX_RECORDS = 50_000
"""The maximum number of records of one window, the rest of the window is not read."""

RETRY_INTERVAL = 1.0
"""Seconds between two tries to find the logger, e.g. right after the TUI started."""

DAY = 86400

TAIL_MAXIMUM = 10_000
"""The maximum number of new records asked for in one `tail` request, the logger keeps 10 000 in memory."""

TRIM_RECORDS = 100
"""The live window removes the records older than its start when there are at least this many (or 5 %)."""

DUPLICATE_MARGIN = 60.0
"""Seconds before the end of the files read in which a new record from `tail` can be one of the files."""


def format_span(seconds: float) -> str:
    """The length of the window, e.g. `30 min`, `1 h` or `1 day`."""
    if seconds >= DAY and seconds % DAY == 0:
        days = int(seconds // DAY)
        return f"{days} day" if days == 1 else f"{days} days"
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{int(seconds // 3600)} h"
    return f"{seconds / 60:g} min"


def format_moment(moment: float) -> str:
    return time.strftime("%a %Y-%m-%d %H:%M:%S", time.localtime(moment))


def logger_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """The number of records by logger name."""
    return dict(collections.Counter(str(record.get("name", "")) for record in records))


def process_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """The number of records by process name."""
    return dict(collections.Counter(str(record.get("process", "")) for record in records))


class LoggerTree(Tree[str]):
    """The loggers of the records in the window, as a tree on the dots in their names, with the number of records.

    `space` selects or deselects the logger at the cursor, with the loggers below it; `enter` opens or closes it. The
    data of a node is the logger name, or `=name` for the records of that logger only, without those below it (a
    logger with its own records and loggers below it, e.g. the plain `egse` logger, gets such a node).
    """

    BINDINGS = [Binding("space", "toggle_selected", "Select logger")]

    class Toggled(Message):
        """`space` on a node: the logger of the node is selected or deselected."""

        def __init__(self, node: TreeNode[str]):
            super().__init__()
            self.node = node

    def __init__(self, *args, **kwargs):
        super().__init__("Loggers", *args, **kwargs)
        self.show_root = False
        self._names: set[str] = set()
        self._counts: dict[str, int] = {}
        self._selected: frozenset[str] = frozenset()
        self._closed_loggers: set[str] = set()
        """The loggers whose node was closed, kept while the tree is empty, e.g. while the next window loads."""
        self._cursor_logger: str | None = None
        """The logger at the cursor, kept while the tree is empty."""

    def show(self, counts: dict[str, int], selected: frozenset[str]) -> None:
        """Shows the loggers with their number of records, and which are selected. The nodes are only replaced when
        the loggers change: a node keeps whether it is open, and the cursor stays at the same logger."""
        self._counts, self._selected = counts, selected
        if set(counts) != self._names:
            self._names = set(counts)
            self._rebuild()
        else:
            self._relabel(self.root)

    def _rebuild(self) -> None:
        if self.root.children:
            self._closed_loggers = {
                n.data for n in self._nodes_below(self.root) if n.allow_expand and not n.is_expanded
            }
            self._cursor_logger = self.cursor_node.data if self.cursor_node is not None else None
        closed, cursor = self._closed_loggers, self._cursor_logger
        self.clear()
        children: dict[str, set[str]] = collections.defaultdict(set)
        for name in self._counts:
            parts = name.split(".")
            for depth in range(1, len(parts) + 1):
                parent = ".".join(parts[: depth - 1])
                children[parent].add(".".join(parts[:depth]))

        def add(node: TreeNode[str], name: str) -> None:
            below = sorted(children.get(name, ()))
            if not below:
                node.add_leaf("", data=name)
                return
            branch = node.add("", data=name, expand=name not in closed)
            if self._counts.get(name):
                branch.add_leaf("", data=f"={name}")
            for child in below:
                add(branch, child)

        for name in sorted(children.get("", ())):
            add(self.root, name)
        self._relabel(self.root)
        if cursor is not None:
            node = next((n for n in self._nodes_below(self.root) if n.data == cursor), None)
            if node is not None:
                self.call_after_refresh(self.move_cursor, node)  # the lines of the nodes are known after a refresh

    def _nodes_below(self, node: TreeNode[str]) -> Iterator[TreeNode[str]]:
        for child in node.children:
            yield child
            yield from self._nodes_below(child)

    def _total(self, name: str) -> int:
        if name.startswith("="):
            return self._counts.get(name[1:], 0)
        return sum(count for logger, count in self._counts.items() if selects_logger(frozenset({name}), logger))

    def _relabel(self, node: TreeNode[str]) -> None:
        for child in node.children:
            name = child.data or ""
            if name.startswith("="):
                label = f"{name[1:].rpartition('.')[2] or '(root)'} itself"
            else:
                label = name.rpartition(".")[2] or "(root)"
            if name in self._selected:
                mark = ("● ", "bold")
            elif not name.startswith("=") and selects_logger(self._selected, name):  # a logger above is selected
                mark = ("● ", "dim")
            elif name.startswith("=") and selects_logger(self._selected, name[1:]):
                mark = ("● ", "dim")
            else:
                mark = ("○ ", "dim")
            child.set_label(Text.assemble(mark, label, (f" {self._total(name)}", "dim")))
            self._relabel(child)

    def action_toggle_selected(self) -> None:
        node = self.cursor_node
        if node is not None and node.data is not None:
            self.post_message(self.Toggled(node))


class ProcessTree(Tree[str]):
    """The processes that logged the records in the window, e.g. `cm_cs`, with the number of records.

    `space` selects or deselects the process at the cursor; with processes selected, only their records are shown.
    The data of a node is the process name.
    """

    BINDINGS = [Binding("space", "toggle_selected", "Select process")]

    class Toggled(Message):
        """`space` on a node: the process of the node is selected or deselected."""

        def __init__(self, node: TreeNode[str]):
            super().__init__()
            self.node = node

    def __init__(self, *args, **kwargs):
        super().__init__("Processes", *args, **kwargs)
        self.show_root = False
        self._counts: dict[str, int] = {}
        self._selected: frozenset[str] = frozenset()
        self._cursor_process: str | None = None
        """The process at the cursor, kept while the list is empty, e.g. while the next window loads."""

    def show(self, counts: dict[str, int], selected: frozenset[str]) -> None:
        """Shows the processes with their number of records, and which are selected. The nodes are only replaced when
        the processes change, the cursor stays at the same process."""
        rebuild = set(counts) != set(self._counts)
        self._counts, self._selected = counts, selected
        if rebuild:
            if self.root.children:
                self._cursor_process = self.cursor_node.data if self.cursor_node is not None else None
            self.clear()
            for name in sorted(counts, key=str.lower):
                self.root.add_leaf("", data=name)
            node = next((n for n in self.root.children if n.data == self._cursor_process), None)
            if node is not None:
                self.call_after_refresh(self.move_cursor, node)  # the lines of the nodes are known after a refresh
        for node in self.root.children:
            mark = ("● ", "bold") if node.data in selected else ("○ ", "dim")
            node.set_label(Text.assemble(mark, node.data or "(none)", (f" {counts.get(node.data, 0)}", "dim")))

    def action_toggle_selected(self) -> None:
        node = self.cursor_node
        if node is not None and node.data is not None:
            self.post_message(self.Toggled(node))


class GotoScreen(ModalScreen[float | None]):
    """Asks for the start of the window: a time today, a date and time, or a time ago, see `parse_time()`."""

    DEFAULT_CSS = """
    GotoScreen {
        align: center middle;
    }
    GotoScreen #dialog {
        width: 70;
        max-width: 100%;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 0 1;
    }
    GotoScreen Input {
        margin: 1 0;
    }
    GotoScreen #error {
        color: $error;
        height: auto;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Go to the start of the window (local time)")
            yield Input(placeholder="HH:MM[:SS], YYYY-MM-DD HH:MM[:SS], or a time ago: 15m, 2h, 1d", id="moment")
            yield Static(id="error")
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        try:
            moment = parse_time(event.value)
        except ValueError as exc:
            self.query_one("#error", Static).update(str(exc))
            return
        self.dismiss(moment)

    def action_cancel(self) -> None:
        self.dismiss(None)


class LogScreen(Screen):
    """The log messages of a time window, with the loggers and the processes of the window at the left.

    Args:
        find_logger: returns the logger service, None when it isn't known (yet).
        history: coroutine function that asks the logger for the records of a window, see `request_log_history()`.
        tail: coroutine function that asks the logger for its new records, see `request_log_tail()`.
        until: the end of the first window, now when None: the latest window.
        span: the length of the window in seconds.
    """

    DEFAULT_CSS = """
    LogScreen #window {
        height: auto;
        padding: 0 1;
    }
    LogScreen #body {
        height: 1fr;
    }
    LogScreen .panel {
        border: round $secondary;
        border-title-color: $text;
        border-title-style: bold;
    }
    LogScreen .panel:focus-within {
        border: round $primary;
    }
    LogScreen #left {
        width: 36;
        height: 1fr;
    }
    LogScreen #loggers-panel {
        height: 3fr;
    }
    LogScreen #processes-panel {
        height: 2fr;
    }
    LogScreen #loggers, LogScreen #processes {
        height: 1fr;
    }
    LogScreen #log-panel {
        width: 1fr;
        height: 1fr;
    }
    LogScreen #log-lines {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        Binding("left_square_bracket", "move(-1)", "Earlier", key_display="["),
        Binding("right_square_bracket", "move(1)", "Later", key_display="]"),
        Binding("minus", "zoom(-1)", "Shorter", key_display="-"),
        Binding("plus,equals_sign", "zoom(1)", "Longer", key_display="+"),
        ("p", "day(-1)", "Day before"),
        ("n", "day(1)", "Day after"),
        ("g", "goto", "Go to"),
        ("t", "latest", "Latest"),
        ("r", "reload", "Reload"),
        ("f", "filter_log", "Filter"),
        ("d", "toggle_debug", "Debug"),
        ("c", "clear_selection", "Clear selection"),
        Binding("F", "app.show_log_files", "Files", key_display="F"),
    ]

    def __init__(
        self,
        find_logger: Callable[[], ServiceInfo | None],
        history: Callable[..., Awaitable[dict | None]] | None = None,
        until: float | None = None,
        span: float = DEFAULT_SPAN,
        tail: Callable[..., Awaitable[dict | None]] | None = None,
    ):
        super().__init__()
        self._find_logger = find_logger
        self._history = history or request_log_history
        self._tail = tail or request_log_tail
        self._service: ServiceInfo | None = None
        self._tail_seq: int | None = None
        """The sequence number of the last record received with `tail`, None when the window is not live."""
        self._live = False
        self._polling = False
        self._poll_timer = None
        self._read_until = 0.0
        """The end of the window when the files were read, the new records after it can't be duplicates."""
        self._recent: dict[tuple[str, str, str], list[tuple[float, str]]] = {}
        """The records read from the files near their end, by process, logger and level, to find the duplicates."""
        self._latest = until is None
        """True for the latest window, it ends at the time it is loaded."""
        self._span = span
        self._until = time.time() if until is None else until
        self._records: list[dict[str, Any]] = []
        self._filter = LogFilter()
        self._status = ""
        self._loading = False
        self._shown = 0
        self._generation = 0
        """Counts the windows, a request for an older window is ignored."""

    @property
    def since(self) -> float:
        return self._until - self._span

    @property
    def until(self) -> float:
        return self._until

    @property
    def records(self) -> list[dict[str, Any]]:
        """The records of the window that were received, oldest first."""
        return self._records

    @property
    def log_filter(self) -> LogFilter:
        return self._filter

    @property
    def live(self) -> bool:
        """True while the latest window gets the new records of the logger."""
        return self._live

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="window")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                loggers = Vertical(LoggerTree(id="loggers"), id="loggers-panel", classes="panel")
                loggers.border_title = "Loggers"
                yield loggers
                processes = Vertical(ProcessTree(id="processes"), id="processes-panel", classes="panel")
                processes.border_title = "Processes"
                yield processes
            log = Vertical(RecordView(id="log-lines"), id="log-panel", classes="panel")
            log.border_title = "Log"
            yield log
        yield Footer()

    def on_mount(self) -> None:
        view = self.query_one("#log-lines", RecordView)
        view.on_scroll = lambda: self._in_stack and self._show_log_subtitle()
        view.focus()
        self.call_after_refresh(self.load)  # during on_mount the screen doesn't count as mounted yet

    @property
    def _in_stack(self) -> bool:
        """False before the screen is mounted, and after it was closed while a request was running."""
        app = self.app
        return self.is_mounted and self.is_attached and app.is_running and self in app.screen_stack

    # The window

    def load(self) -> None:
        """Asks the logger for the records of the window, replacing those of the previous window."""
        if not self._in_stack:
            return
        self._generation += 1
        self._stop_live()
        if self._latest:
            self._until = time.time()
        self._records = []
        self._shown = 0
        self._status = ""
        self._loading = True
        self.query_one("#log-lines", RecordView).clear()
        self._show_trees()
        self._show_window()
        self.run_worker(self._load(self._generation), group="history", exclusive=True)

    async def _load(self, generation: int) -> None:
        service = self._find_logger()
        if service is None:
            self._status = "the logger is not known (yet)"
            self._loading = False
            self._show_window()
            self.set_timer(RETRY_INTERVAL, lambda: generation == self._generation and self.load())
            return
        self._service = service
        cursor = None
        complete = False
        try:
            if self._latest:  # the position of the tail before the files are read: no record is missed
                answer = await self._tail(service, 0, 0)
                if generation != self._generation or not self._in_stack:
                    return
                if answer is not None and "records" in answer:
                    self._tail_seq = answer.get("last_seq") or 0
            while True:
                maximum = min(PAGE_RECORDS, MAX_RECORDS - len(self._records))
                answer = await self._history(service, self.since, self.until, maximum, cursor)
                if generation != self._generation or not self._in_stack:
                    return
                if answer is None:
                    self._status = "the logger doesn't answer, r tries again"
                    return
                if answer.get("status") != "ACK":
                    if "status" not in answer:
                        self._status = "this logger can't read its log files, restart it with the current version"
                    else:
                        self._status = f"the logger: {answer.get('error', 'no records')}"
                    return
                self._append(answer.get("records") or [])
                cursor = answer.get("cursor")
                if cursor is None:
                    complete = True
                    return
                if len(self._records) >= MAX_RECORDS:
                    self._status = f"only the first {MAX_RECORDS} records, make the window shorter (-)"
                    return
        finally:
            if generation == self._generation and self._in_stack:
                self._loading = False
                if complete and self._latest and self._tail_seq is not None:
                    self._start_live()
                elif self._latest and not self._status:
                    self._status = "no live updates, the logger doesn't send its new records"
                self._show_window()

    # The live window

    def _start_live(self) -> None:
        self._live = True
        self._read_until = self._until
        self._recent = {}
        for record in self._records:
            if record["time"] >= self._read_until - DUPLICATE_MARGIN:
                key = self._duplicate_key(record)
                self._recent.setdefault(key, []).append((record["time"], str(record.get("message", ""))))
        self._poll_timer = self.set_interval(TAIL_INTERVAL, self._poll_tail)

    def _stop_live(self) -> None:
        self._live = False
        self._tail_seq = None
        self._recent = {}
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None

    def _poll_tail(self) -> None:
        if self._live and not self._polling and self._in_stack:
            self._polling = True
            self.run_worker(self._receive_tail(self._generation), group="tail")

    async def _receive_tail(self, generation: int) -> None:
        try:
            answer = await self._tail(self._service, self._tail_seq, TAIL_MAXIMUM)
        finally:
            self._polling = False
        if generation != self._generation or not self._live or not self._in_stack:
            return
        if answer is None or "records" not in answer:
            self._status = "the logger doesn't answer, waiting for new records"
            self._show_window()
            return
        self._status = ""
        last_seq = answer.get("last_seq") or 0
        if last_seq < self._tail_seq:  # the logger was restarted, its sequence numbers start again
            self._tail_seq = 0
            self._recent = {}
            return
        self._tail_seq = last_seq
        records = [record for record in answer["records"] if not self._is_duplicate(record)]
        self._until = time.time()
        self._trim()
        if records:
            view = self.query_one("#log-lines", RecordView)
            follows = view.follows
            self._records.extend(records)
            self._shown += view.append(records, self._include(), scroll_end=follows)
            self._show_trees()
        self._show_window()
        self._show_log_subtitle()

    @staticmethod
    def _duplicate_key(record: dict[str, Any]) -> tuple[str, str, str]:
        return str(record.get("process", "")), str(record.get("name", "")), str(record.get("level", ""))

    def _is_duplicate(self, record: dict[str, Any]) -> bool:
        """True for a new record that was also read from the files: same process, logger, level and time (to the ms
        of the file), and the message of the file starts with that of the tail (which has no traceback and is cut).
        Two processes can log the same message in the same ms, e.g. cm_cs and sm_cs."""
        moment = record.get("time")
        if not self._recent or not isinstance(moment, (int, float)):
            return False
        message = str(record.get("message", "")).rstrip()
        candidates = self._recent.get(self._duplicate_key(record), ())
        return any(abs(time_ - moment) < 0.002 and text.startswith(message) for time_, text in candidates)

    def _trim(self) -> None:
        """Removes the records older than the start of the live window, and the oldest above `MAX_RECORDS`."""
        since = self.since
        count = next((i for i, record in enumerate(self._records) if record["time"] >= since), len(self._records))
        count = max(count, len(self._records) - MAX_RECORDS)
        if count >= max(TRIM_RECORDS, len(self._records) // 20) or len(self._records) > MAX_RECORDS:
            del self._records[:count]
            self._shown = self.query_one("#log-lines", RecordView).drop_oldest(count)
            self._show_trees()

    def _append(self, records: list[dict[str, Any]]) -> None:
        self._records.extend(records)
        # The latest window follows its end, an older window is shown from its start.
        self._shown += self.query_one("#log-lines", RecordView).append(records, self._include(), self._latest)
        self._show_trees()
        self._show_window()
        self._show_log_subtitle()

    def _show_window(self) -> None:
        parts = [f"{format_moment(self.since)} – {format_moment(self.until)}", format_span(self._span)]
        if self._live:
            parts[-1] += ", live"
        elif self._latest:
            parts[-1] += ", the latest"
        parts.append(f"{len(self._records)} records" + (", loading …" if self._loading else ""))
        if self._status:
            parts.append(self._status)
        self.query_one("#window", Static).update(Text(" · ".join(parts)))

    def _set_window(self, until: float, span: float | None = None) -> None:
        now = time.time()
        self._span = self._span if span is None else span
        self._latest = until >= now
        self._until = min(until, now)
        self.load()

    def action_move(self, direction: int) -> None:
        self._set_window(self._until + direction * self._span)

    def action_day(self, direction: int) -> None:
        self._set_window(self._until + direction * DAY)

    def action_zoom(self, direction: int) -> None:
        """A shorter or longer window with the same start; the latest window keeps ending now."""
        index = min(range(len(SPANS)), key=lambda i: abs(SPANS[i] - self._span))
        span = SPANS[max(0, min(len(SPANS) - 1, index + direction))]
        if span == self._span:
            return
        self._set_window(self._until if self._latest else self.since + span, span)

    def action_latest(self) -> None:
        self._set_window(float("inf"))  # until now; time.time() here would be before the now of _set_window()

    def action_reload(self) -> None:
        self.load()

    def action_goto(self) -> None:
        def go(moment: float | None) -> None:
            if moment is not None:
                self._set_window(moment + self._span)

        self.app.push_screen(GotoScreen(), go)

    # The lines and the filter

    def _include(self):
        """Tells how a record is shown with the filter: True normal, False dimmed, None not at all."""
        matches = self._filter.matcher()

        def include(record: dict[str, Any]) -> bool | None:
            if self._filter.hides(record):
                return None
            if matches(record):
                return True
            return False if self._filter.dim else None

        return include

    def _rewrite(self) -> None:
        self._shown = self.query_one("#log-lines", RecordView).show(self._include())
        self._show_log_subtitle()

    def _show_log_subtitle(self) -> None:
        parts = [FOLLOW_HINT] if self._live and not self.query_one("#log-lines", RecordView).follows else []
        if self._filter.active:
            counts = f"{self._shown} of {len(self._records)}"
            parts.append(f"filter: {self._filter.describe()}, {counts}" + (" match" if self._filter.dim else " shown"))
        if self._filter.hide_debug:
            parts.append("DEBUG hidden")
        self.query_one("#log-panel").border_subtitle = " · ".join(parts)

    def _show_trees(self) -> None:
        """The loggers and the processes of the window at the left, with their number of records."""
        self.query_one("#loggers", LoggerTree).show(logger_counts(self._records), self._filter.loggers)
        self.query_one("#processes", ProcessTree).show(process_counts(self._records), self._filter.processes)

    def set_filter(self, log_filter: LogFilter | None) -> None:
        if log_filter is None or log_filter == self._filter:
            return
        self._filter = log_filter
        self._show_trees()
        self._rewrite()

    def on_logger_tree_toggled(self, event: LoggerTree.Toggled) -> None:
        event.stop()
        name = event.node.data
        loggers = self._filter.loggers
        loggers = loggers - {name} if name in loggers else loggers | {name}
        self.set_filter(dataclasses.replace(self._filter, loggers=loggers))

    def on_process_tree_toggled(self, event: ProcessTree.Toggled) -> None:
        event.stop()
        name = event.node.data
        processes = self._filter.processes
        processes = processes - {name} if name in processes else processes | {name}
        self.set_filter(dataclasses.replace(self._filter, processes=processes))

    def action_clear_selection(self) -> None:
        """Clears the selected loggers and processes."""
        self.set_filter(dataclasses.replace(self._filter, loggers=frozenset(), processes=frozenset()))

    def action_filter_log(self) -> None:
        processes = {str(r["process"]) for r in self._records if r.get("process")}
        modules = {str(r[key]) for r in self._records for key in ("name", "module") if r.get(key)}
        self.app.push_screen(LogFilterScreen(self._filter, processes, modules), self.set_filter)

    def action_toggle_debug(self) -> None:
        self.set_filter(dataclasses.replace(self._filter, hide_debug=not self._filter.hide_debug))
