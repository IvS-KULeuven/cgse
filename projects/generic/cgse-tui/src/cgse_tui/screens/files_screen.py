"""The log-files screen: the files of the log folders of the machines, e.g. the output of a service that didn't start.

Every machine with services runs a log-files service (`cgse lf`, see `egse.logfiles`), which reads the files of
its own log folder: the `*.start.log` and `*.stop.log` files with the output of the processes that were started with a
`cgse <object> start` command, and the other files in the folder. The tree at the left has the machines and their
files, the most recently changed first; `enter` shows a file.

A file is shown from its last page (`PAGE_BYTES`); `b` adds the page before it, up to `MAX_BYTES`. The view follows
the file: the new lines are asked for every `FOLLOW_INTERVAL` seconds. While scrolled up the view stays where it is,
`end` follows again.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Log
from textual.widgets import Static
from textual.widgets import Tree

from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.report import request_log_file_page
from cgse_tui.data.report import request_log_files
from cgse_tui.screens.logview import FOLLOW_HINT

PAGE_BYTES = 256 * 1024
"""The number of bytes asked for in one request."""

MAX_BYTES = 4 * 1024 * 1024
"""The maximum number of bytes of a file in the view, `b` doesn't add pages beyond it."""

FOLLOW_INTERVAL = 2.0
"""Seconds between two requests for the new lines of the file in the view."""


def format_size(size: int) -> str:
    """The size of a file, e.g. `812 B`, `14.2 KiB`, `3.1 MiB`."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / 1024 / 1024:.1f} MiB"


def format_age(seconds: float) -> str:
    """How long ago a file changed, e.g. `12 s`, `5 min`, `3 h`, `2 d`."""
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds // 60:.0f} min"
    if seconds < 86400:
        return f"{seconds // 3600:.0f} h"
    return f"{seconds // 86400:.0f} d"


def machine_name(service: ServiceInfo) -> str:
    """The name of the machine of a log-files service, its host name when it's known."""
    return service.hostname or service.registered_host or service.host or service.name


class LogFilesScreen(Screen):
    """The machines and the files of their log folders at the left, the selected file at the right.

    Args:
        find_services: returns the log-files services that are registered, one per machine and log folder.
        files: coroutine function that asks a service for its files, see `request_log_files()`.
        page: coroutine function that asks a service for a page of a file, see `request_log_file_page()`.
    """

    DEFAULT_CSS = """
    LogFilesScreen #body {
        height: 1fr;
    }
    LogFilesScreen .panel {
        border: round $secondary;
        border-title-color: $text;
        border-title-style: bold;
    }
    LogFilesScreen .panel:focus-within {
        border: round $primary;
    }
    LogFilesScreen #files-panel {
        width: 56;
        height: 1fr;
    }
    LogFilesScreen #files {
        height: 1fr;
    }
    LogFilesScreen #file-panel {
        width: 1fr;
        height: 1fr;
    }
    LogFilesScreen #file-lines {
        height: 1fr;
    }
    LogFilesScreen #status {
        height: auto;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("r", "reload", "Reload"),
        ("b", "earlier", "Earlier"),
    ]

    def __init__(
        self,
        find_services: Callable[[], list[ServiceInfo]],
        files: Callable[..., Awaitable[dict | None]] | None = None,
        page: Callable[..., Awaitable[dict | None]] | None = None,
    ):
        super().__init__()
        self._find_services = find_services
        self._files = files or request_log_files
        self._page = page or request_log_file_page
        self._file_service: ServiceInfo | None = None
        self._file_name: str | None = None
        self._file_text = ""
        """The text of the file in the view."""
        self._file_start = 0
        """The offset in the file of the text in the view."""
        self._file_end = 0
        """The offset in the file where the next page starts."""
        self._file_size = 0
        self._generation = 0
        """Counts the files shown, an answer for an earlier file is ignored."""
        self._following = False
        self._status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="status")
        with Horizontal(id="body"):
            files = Vertical(Tree("Machines", id="files"), id="files-panel", classes="panel")
            files.border_title = "Log files"
            yield files
            view = Vertical(Log(id="file-lines", auto_scroll=False), id="file-panel", classes="panel")
            view.border_title = "File"
            yield view
        yield Footer()

    def on_mount(self) -> None:
        tree = self.query_one("#files", Tree)
        tree.show_root = False
        tree.focus()
        self.set_interval(FOLLOW_INTERVAL, self._follow)
        self.watch(
            self.query_one("#file-lines", Log), "scroll_y", lambda _: self._in_stack and self._show_file_subtitle()
        )
        self.call_after_refresh(self.action_reload)

    @property
    def _in_stack(self) -> bool:
        app = self.app
        return self.is_mounted and self.is_attached and app.is_running and self in app.screen_stack

    @property
    def file_name(self) -> str | None:
        """The name of the file in the view."""
        return self._file_name

    @property
    def text(self) -> str:
        """The text of the file in the view."""
        return self._file_text

    # The files

    def action_reload(self) -> None:
        """Asks every log-files service for its files, and the file in the view for its new lines."""
        self.run_worker(self._load_files(), group="files", exclusive=True)

    async def _load_files(self) -> None:
        services = sorted(self._find_services(), key=machine_name)
        if not services:
            self._show_status("No log-files service is registered: start one with `cgse lf start`.")
        answers = [(service, await self._files(service)) for service in services]
        if not self._in_stack:
            return
        tree = self.query_one("#files", Tree)
        cursor = tree.cursor_node.data if tree.cursor_node is not None else None
        tree.clear()
        now = time.time()
        for service, answer in answers:
            label = machine_name(service)
            if answer is None or answer.get("status") != "ACK":
                error = "doesn't answer" if answer is None else answer.get("error", "no files")
                tree.root.add_leaf(escape(f"{label}: {error}"), data=None)
                continue
            node = tree.root.add(f"{escape(label)}  [dim]{escape(answer.get('folder', ''))}[/]", data=None, expand=True)
            for item in answer.get("files") or []:
                text = f"{escape(item['name'])}  [dim]{format_size(item['size'])}, {format_age(now - item['mtime'])}[/]"
                node.add_leaf(text, data=(service.service_type, item["name"]))
        if services:
            self._show_status("")
        if cursor is not None:
            for line in range(tree.last_line + 1):
                node = tree.get_node_at_line(line)
                if node is not None and node.data == cursor:
                    tree.move_cursor(node)
                    break

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        event.stop()
        if event.node.data is None:
            return
        service_type, name = event.node.data
        service = next((s for s in self._find_services() if s.service_type == service_type), None)
        if service is None:
            self._show_status(f"The log-files service of {name} is gone, `r` reloads.")
            return
        self.show_file(service, name)

    # The file

    def show_file(self, service: ServiceInfo, name: str) -> None:
        """Shows the last page of the file, and follows it."""
        self._generation += 1
        self._file_service, self._file_name = service, name
        self._file_text, self._file_start, self._file_end, self._file_size = "", 0, 0, 0
        self._following = False
        view = self.query_one("#file-lines", Log)
        view.clear()
        panel = self.query_one("#file-panel")
        panel.border_title = f"{name} ({machine_name(service)})"
        self.run_worker(self._load_last(self._generation), group="file", exclusive=True)

    async def _load_last(self, generation: int) -> None:
        answer = await self._page(self._file_service, self._file_name, maximum=PAGE_BYTES)
        if generation != self._generation or not self._in_stack:
            return
        if not self._accept(answer):
            return
        self._file_text, self._file_start, self._file_end, self._file_size = (
            answer["text"],
            answer["offset"],
            answer["end"],
            answer["size"],
        )
        view = self.query_one("#file-lines", Log)
        view.clear()
        view.write(self._file_text, scroll_end=True)
        self._following = True
        self._show_file_subtitle()

    def _accept(self, answer: dict[str, Any] | None) -> bool:
        """True for a page, else the reason is shown."""
        if answer is None:
            self._show_status(f"{self._file_name}: the log-files service doesn't answer, `r` tries again.")
            return False
        if answer.get("status") != "ACK":
            self._show_status(f"{self._file_name}: {answer.get('error', 'no answer')}")
            return False
        self._show_status("")
        return True

    async def _follow(self) -> None:
        """Asks for the new lines of the file in the view, and adds them."""
        if not (self._following and self._file_service and self._file_name and self._in_stack):
            return
        generation = self._generation
        answer = await self._page(self._file_service, self._file_name, offset=self._file_end, maximum=PAGE_BYTES)
        if generation != self._generation or not self._in_stack or not self._accept(answer):
            return
        if answer.get("truncated"):  # the file was replaced, e.g. a new start log: show it from its end again
            self._following = False
            self.run_worker(self._load_last(self._generation), group="file", exclusive=True)
            return
        self._file_size = answer["size"]
        if answer["text"]:
            view = self.query_one("#file-lines", Log)
            self._file_text += answer["text"]
            self._file_end = answer["end"]
            view.write(answer["text"], scroll_end=view.is_vertical_scroll_end)
        self._show_file_subtitle()

    def action_earlier(self) -> None:
        """Adds the page before the text in the view."""
        if not (self._file_service and self._file_name) or self._file_start == 0:
            return
        if self._file_end - self._file_start >= MAX_BYTES:
            self._show_status(f"At most {format_size(MAX_BYTES)} of a file are shown.")
            return
        self.run_worker(self._load_earlier(self._generation), group="file", exclusive=True)

    async def _load_earlier(self, generation: int) -> None:
        answer = await self._page(self._file_service, self._file_name, before=self._file_start, maximum=PAGE_BYTES)
        if generation != self._generation or not self._in_stack or not self._accept(answer):
            return
        if answer["end"] != self._file_start:  # the file changed under the view
            self.show_file(self._file_service, self._file_name)
            return
        view = self.query_one("#file-lines", Log)
        lines_before = view.line_count
        self._file_text = answer["text"] + self._file_text
        self._file_start = answer["offset"]
        scroll_y = view.scroll_y
        view.clear()
        view.write(self._file_text, scroll_end=False)
        view.scroll_to(y=scroll_y + view.line_count - lines_before, animate=False)
        self._show_file_subtitle()

    # Status

    def _show_status(self, text: str) -> None:
        self._status_text = text
        if self.is_mounted:
            self.query_one("#status", Static).update(text)

    def _show_file_subtitle(self) -> None:
        if not self._file_name:
            return
        view = self.query_one("#file-lines", Log)
        shown = f"{format_size(self._file_end - self._file_start)} of {format_size(self._file_size)}"
        earlier = ", b for earlier" if self._file_start > 0 else ""
        follow = "" if view.is_vertical_scroll_end else f", {FOLLOW_HINT}"
        self.query_one("#file-panel").border_subtitle = f"{shown}{earlier}{follow}"
