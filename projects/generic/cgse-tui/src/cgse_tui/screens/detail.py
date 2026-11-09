"""The detail screen: the status of one service in panels, updated live."""

from __future__ import annotations

import collections
import dataclasses
import logging
import time
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import ScrollableContainer
from textual.containers import Vertical
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Pretty
from textual.widgets import RichLog
from textual.widgets import Static

from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.data.report import request_log_tail
from cgse_tui.data.services import custom_kind
from cgse_tui.plugins import DetailsRenderers
from cgse_tui.screens import panels
from cgse_tui.screens.log_filter import LogFilterScreen
from cgse_tui.screens.logtail import MAX_LINES
from cgse_tui.screens.logtail import TAIL_INTERVAL
from cgse_tui.screens.logtail import LogFilter
from cgse_tui.screens.logtail import format_record
from cgse_tui.screens.procman import CoreServicesTable
from cgse_tui.screens.registry import RegistryTable

logger = logging.getLogger("cgse_tui.detail")


MAX_SECTION_COLUMNS = 3
"""Sections of the Details panel side by side; more sections continue on the next row."""


def panel(title: str, *children, id: str | None = None) -> Vertical:
    container = Vertical(*children, id=id, classes="panel")
    container.border_title = title
    return container


class LogPanel(Vertical):
    """The panel with the log lines of the logger, which can fill the screen (`m`)."""

    ALLOW_MAXIMIZE = True


class LogTail(RichLog):
    """The log lines, scrolled with the keys of a scrollable container when it has the focus."""

    BINDINGS = ScrollableContainer.BINDINGS


class DetailScreen(Screen):
    """Shows the status of a service in panels: Service, Process, Device and Details.

    The Details panel comes from a plugin of the package of the service, a built-in renderer, or the generic tree, see
    `cgse_tui.plugins`. A renderer can split the details over several panels. The detail screen of the service
    registry also has a table of the registrations, that of the Process Manager a table of the core services: `enter`
    shows the details of the selected service.

    The detail screen of the logger has the last log lines at the bottom. They follow the new lines while the view is
    at the end; scrolled up, the view stays at the same lines. `m` makes the log panel fill the screen and back, `f`
    filters the lines, see `cgse_tui.screens.logtail.LogFilter`.

    The app passes the services to `show_services()` on every update of the overview, so the panels follow the
    service live, also when it is restarted. The status report is requested when the screen opens and with `r`, the
    collector requests it regularly as well. `v` shows the raw status report instead of the panels.

    Args:
        service: the service to show.
        refresh: coroutine function that requests the status again and returns the updated service.
        renderers: the renderers of the Details panel, by default those of the app, or new `DetailsRenderers`.
    """

    DEFAULT_CSS = """
    DetailScreen #title {
        height: auto;
        padding: 0 1;
    }
    DetailScreen .panel {
        height: auto;
        border: round $secondary;
        border-title-color: $text;
        border-title-style: bold;
        padding: 0 1;
    }
    /* A grid row is as high as its highest cell, and height 100% makes every panel fill its cell: the
       Service, Process and Device panels get the same height. */
    DetailScreen #top {
        layout: grid;
        grid-size: 3;
        grid-columns: 1fr;
        grid-rows: auto;
        height: auto;
    }
    DetailScreen #top.-no-device {
        grid-size: 2;
    }
    DetailScreen #top .panel {
        height: 100%;
    }
    /* The sections of the Details panel side by side, at most MAX_SECTION_COLUMNS per row, each row as high as its
       highest section, like the top row. The number of columns is set in _show_details(). */
    DetailScreen #details-area {
        height: auto;
    }
    DetailScreen .details-row {
        layout: grid;
        grid-columns: 1fr;
        grid-rows: auto;
        height: auto;
    }
    DetailScreen .details-row .panel {
        height: 100%;
    }
    DetailScreen #registrations, DetailScreen #core-services {
        height: auto;
        max-height: 20;
    }
    DetailScreen #panels.-dimmed .panel {
        opacity: 60%;
    }
    DetailScreen #raw-view {
        display: none;
    }
    /* The logger: the panels take the height they need (at most 60 %), the log lines fill the rest. */
    DetailScreen #log-panel {
        display: none;
        height: 1fr;
        min-height: 8;
    }
    DetailScreen.-with-log #log-panel {
        display: block;
    }
    DetailScreen.-with-log #log-panel.-hidden {
        display: none;
    }
    DetailScreen.-with-log #panels {
        height: auto;
        max-height: 60%;
    }
    DetailScreen #log-tail {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("r", "refresh", "Refresh"),
        ("a", "select_action", "Actions"),
        ("v", "toggle_raw", "Raw report"),
        ("m", "toggle_log_maximized", "Maximize"),
        ("f", "filter_log", "Filter"),
        ("d", "toggle_debug", "Debug"),
    ]

    LOG_ACTIONS = ("toggle_log_maximized", "filter_log", "toggle_debug")
    """The actions of the log panel, only possible in the detail screen of the logger."""

    def __init__(
        self,
        service: ServiceInfo,
        refresh: Callable[[], Awaitable[ServiceInfo | None]] | None = None,
        renderers: DetailsRenderers | None = None,
        log_tail: Callable[..., Awaitable[dict | None]] | None = None,
    ):
        super().__init__()
        self._log_tail = log_tail or request_log_tail
        self._tail_seq = 0
        """The sequence number of the last log record shown, see `egse.logger.log_cs`."""
        self._tail_requested_at: float | None = None
        self._tail_busy = False
        self._log_entries: collections.deque[dict[str, Any]] = collections.deque(maxlen=MAX_LINES)
        """The received log records, and markers `{"marker": text}`, e.g. when the logger was restarted."""
        self._log_filter = LogFilter()
        self._log_shown = 0
        """The number of records in `_log_entries` that pass the filter."""
        self._log_records = 0
        """The number of records in `_log_entries`, without the markers."""
        self._log_status = ""
        self.service = service
        self._refresh = refresh
        self._renderers = renderers
        self._section_titles: list[list[str]] = []
        self._sections: list[Static] = []
        self._section_panels: list[Vertical] = []
        self._services: list[ServiceInfo] = []
        self._requesting = False
        self._gone = False
        self._raw_report: dict | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="title")
        with VerticalScroll(id="panels"):
            with Horizontal(id="top"):
                yield panel("Service", Static(id="service"), id="service-panel")
                yield panel("Process", Static(id="process"), id="process-panel")
                yield panel("Device", Static(id="device"), id="device-panel")
            yield Vertical(id="details-area")
            yield panel("Registrations", RegistryTable(id="registrations"), id="registry-panel")
            yield panel("Core services", CoreServicesTable(id="core-services"), id="procman-panel")
        log_tail = LogTail(id="log-tail", max_lines=MAX_LINES, wrap=True, markup=False)
        log_panel = LogPanel(log_tail, id="log-panel", classes="panel")
        log_panel.border_title = "Log"
        yield log_panel
        with VerticalScroll(id="raw-view"):
            yield Pretty({}, id="raw")
        yield Footer()

    def on_mount(self) -> None:
        if self._renderers is None:
            self._renderers = getattr(self.app, "details_renderers", None) or DetailsRenderers()
        # During on_mount the screen doesn't count as mounted yet, refresh_view() would do nothing: show the service
        # right after the first refresh, instead of at the next update of the app, up to a second later.
        self.call_after_refresh(self.refresh_view)
        self.action_refresh()
        if self.service.cgse_object == "log":
            self.query_one("#log-tail", RichLog).focus()  # the keys scroll the log lines, e.g. `end` to follow again

    def show_services(self, services: list[ServiceInfo]) -> None:
        """Follows the service in the given services; a service that is gone keeps its last information."""
        self._services = services
        service = next((s for s in services if s.service_type == self.service.service_type), None)
        self._gone = service is None
        if service is not None:
            self.service = service
        self.refresh_view()

    @property
    def _in_stack(self) -> bool:
        """False before the screen is mounted, after it was closed while a request was running, and while the app
        exits: then the screen is still in the stack, but its widgets may be removed already."""
        app = self.app
        return self.is_mounted and self.is_attached and app.is_running and self in app.screen_stack

    def refresh_view(self) -> None:
        if not self._in_stack:
            return
        service = self.service
        now = time.time()
        self.query_one("#title", Static).update(
            panels.title(service, panels.state_indicator(service), now, self._requesting, self._gone)
        )
        self.query_one("#panels").set_class(
            self._gone or service.state in (ServiceState.STALE, ServiceState.INACTIVE), "-dimmed"
        )
        self.query_one("#service", Static).update(panels.key_values(panels.service_rows(service, now)))
        self.query_one("#process", Static).update(panels.process_panel(service))

        device_panel = self.query_one("#device-panel")
        device_panel.display = panels.has_device_panel(service)
        self.query_one("#top").set_class(not device_panel.display, "-no-device")
        if device_panel.display:
            self.query_one("#device", Static).update(panels.device_panel(service))

        self._show_details(service)

        registry_panel = self.query_one("#registry-panel")
        registry_panel.display = custom_kind(service) == "registry"
        if registry_panel.display:
            self.query_one("#registrations", RegistryTable).show(service.report, now)

        procman_panel = self.query_one("#procman-panel")
        procman_panel.display = service.cgse_object == "pm"
        if procman_panel.display:
            table = self.query_one("#core-services", CoreServicesTable)
            table.show(service.report, self._services, now)
            procman_panel.border_subtitle = f"{table.running} of {table.row_count} running"

        self.set_class(service.cgse_object == "log", "-with-log")
        if service.cgse_object == "log":
            self._show_log_subtitle()
        if service.cgse_object == "log" and not self._tail_busy and not self._gone:
            if self._tail_requested_at is None or time.monotonic() - self._tail_requested_at >= TAIL_INTERVAL:
                self._tail_requested_at = time.monotonic()
                self._tail_busy = True
                self.run_worker(self._show_log_tail(), group="log-tail")

        if self._raw_report is not service.report:
            self._raw_report = service.report
            self.query_one("#raw", Pretty).update(service.report or "No status report received yet.")

    def _show_details(self, service: ServiceInfo) -> None:
        """Shows the sections of the Details renderer, a panel per section, a grid per row. The panels are only
        replaced when the titles of the sections change, otherwise their content is updated."""
        rows, source = self._renderers.render_rows(service)
        sections = [section for row in rows for section in row]
        titles = [[title for title, _ in row] for row in rows]
        area = self.query_one("#details-area")
        if titles != self._section_titles:
            self._section_titles = titles
            self._sections = [Static(renderable, classes="section") for _, renderable in sections]
            statics = iter(self._sections)
            self._section_panels = []
            grids = []
            for row in rows:
                row_panels = [panel(title, next(statics)) for title, _ in row]
                self._section_panels += row_panels
                grid = Horizontal(*row_panels, classes="details-row")
                grid.styles.grid_size_columns = min(len(row_panels), MAX_SECTION_COLUMNS)
                grids.append(grid)
            area.remove_children()
            area.mount_all(grids)
        else:
            for static, (_, renderable) in zip(self._sections, sections):
                if renderable is not static.content:  # the same object needn't be rendered again
                    static.update(renderable)
        self._section_panels[0].border_subtitle = source

    async def _show_log_tail(self) -> None:
        """Appends the log records that arrived since the last request."""
        try:
            answer = await self._log_tail(self.service, self._tail_seq, MAX_LINES)
        finally:
            self._tail_busy = False
        if not self._in_stack:
            return
        if answer is None:
            self._log_status = "the logger doesn't answer"
            self._show_log_subtitle()
            return
        if "records" not in answer:
            if self._tail_seq == 0:
                message = "This logger can't send its log lines, restart it with the current version."
                self._append_log([{"marker": message}])
                self._tail_seq = -1  # don't write the message again
            return
        last_seq = answer.get("last_seq") or 0
        entries = []
        if 0 < last_seq < self._tail_seq:
            entries.append({"marker": "--- the logger was restarted ---"})
        entries += answer["records"]
        self._tail_seq = last_seq
        self._log_status = f"{last_seq} messages received"
        self._append_log(entries)

    @staticmethod
    def _log_line(entry: dict[str, Any], dimmed: bool = False) -> Text:
        if "marker" in entry:
            return Text(entry["marker"], "dim")
        line = format_record(entry)
        return Text(line.plain, "dim") if dimmed else line

    def _write_log_entry(self, log: RichLog, entry: dict[str, Any], matches, scroll_end: bool) -> None:
        """Writes the entry when it passes the filter, or dimmed when the filter dims the other lines."""
        if self._log_filter.hides(entry):
            return
        if matches(entry):
            log.write(self._log_line(entry), scroll_end=scroll_end)
        elif self._log_filter.dim:
            log.write(self._log_line(entry, dimmed=True), scroll_end=scroll_end)

    def _log_matcher(self) -> Callable[[dict[str, Any]], bool]:
        matches = self._log_filter.matcher()
        return lambda entry: "marker" in entry or matches(entry)

    def _append_log(self, entries: list[dict[str, Any]]) -> None:
        """Keeps the entries and writes those that pass the filter, and the others dimmed when the filter dims.

        The view follows the new lines when it is at the end. Otherwise it stays at the same lines: when the oldest
        lines are removed (`max_lines`), it is scrolled up by as many lines.
        """
        self._log_entries.extend(entries)
        log = self.query_one("#log-tail", RichLog)
        matches = self._log_matcher()
        follow = log.is_vertical_scroll_end  # before the writes: a write scrolls to the end only after a refresh
        start_line = log._start_line  # the number of lines removed at the top, private in RichLog
        for entry in entries:
            self._write_log_entry(log, entry, matches, follow)
        removed = log._start_line - start_line
        if not follow and removed > 0:
            log.scroll_to(y=max(0, log.scroll_y - removed), animate=False, immediate=True)
        self._count_log_matches(matches)
        self._show_log_subtitle()

    def _count_log_matches(self, matches) -> None:
        """Counts the records that pass the filter, and all records that are not hidden; markers are no records."""
        records = [e for e in self._log_entries if "marker" not in e and not self._log_filter.hides(e)]
        self._log_shown = sum(1 for entry in records if matches(entry))
        self._log_records = len(records)

    def _rewrite_log(self) -> None:
        """Writes the kept entries again after a change of the filter."""
        log = self.query_one("#log-tail", RichLog)
        log.clear()
        matches = self._log_matcher()
        for entry in self._log_entries:
            self._write_log_entry(log, entry, matches, scroll_end=True)
        self._count_log_matches(matches)
        self._show_log_subtitle()

    def _show_log_subtitle(self) -> None:
        """The border of the log panel: the number of messages, the filter, and whether the view follows new lines."""
        log = self.query_one("#log-tail", RichLog)
        parts = [] if log.is_vertical_scroll_end else ["scrolled, end to follow"]  # first, a long border is cut
        if self._log_status:
            parts.append(self._log_status)
        if self._log_filter.active:
            counts = f"{self._log_shown} of {self._log_records}"
            counts += " match, others dimmed" if self._log_filter.dim else " shown"
            parts.append(f"filter: {self._log_filter.describe()}, {counts}")
        if self._log_filter.hide_debug:
            parts.append("DEBUG hidden")
        self.query_one("#log-panel").border_subtitle = " · ".join(parts)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in self.LOG_ACTIONS:
            return self.service.cgse_object == "log"
        return True

    def action_toggle_log_maximized(self) -> None:
        if self.maximized is not None:
            self.minimize()
            return
        raw = self.query_one("#raw-view")
        if raw.display:
            self.action_toggle_raw()
        log_panel = self.query_one("#log-panel", LogPanel)
        self.maximize(log_panel, container=False)
        self.query_one("#log-tail", RichLog).focus()

    def action_filter_log(self) -> None:
        processes = {str(e["process"]) for e in self._log_entries if e.get("process")}
        modules = {str(e[key]) for e in self._log_entries for key in ("name", "module") if e.get(key)}
        self.app.push_screen(LogFilterScreen(self._log_filter, processes, modules), self._set_log_filter)

    def action_toggle_debug(self) -> None:
        self._set_log_filter(dataclasses.replace(self._log_filter, hide_debug=not self._log_filter.hide_debug))

    def _set_log_filter(self, log_filter: LogFilter | None) -> None:
        if log_filter is None or log_filter == self._log_filter:
            return
        self._log_filter = log_filter
        self._rewrite_log()

    def action_toggle_raw(self) -> None:
        if self.maximized is not None:
            self.minimize()
        raw = self.query_one("#raw-view")
        raw.display = not raw.display
        self.query_one("#panels").display = not raw.display
        self.query_one("#log-panel").set_class(raw.display, "-hidden")

    def action_select_action(self) -> None:
        self.app.select_action(self.service)

    def action_refresh(self) -> None:
        if self._refresh is not None:
            logger.info(f"Requesting the status of {self.service.name} ...")
            self._requesting = True
            self.refresh_view()
            self.run_worker(self._update(), group="refresh", exclusive=True)

    async def _update(self) -> None:
        try:
            service = await self._refresh()
        finally:
            self._requesting = False
        if service is None:
            self.refresh_view()
            return
        if service.report:
            logger.info(f"Status of {service.name} received.")
        else:
            logger.warning(f"No status received from {service.name}.")
        self.service = service
        self.refresh_view()
