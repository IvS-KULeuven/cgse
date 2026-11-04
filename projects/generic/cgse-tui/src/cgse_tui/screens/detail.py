"""The detail screen: the status of one service in panels, updated live."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable
from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
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
from cgse_tui.screens.logtail import FIRST_LINES
from cgse_tui.screens.logtail import MAX_LINES
from cgse_tui.screens.logtail import TAIL_INTERVAL
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


class DetailScreen(Screen):
    """Shows the status of a service in panels: Service, Process, Device and Details.

    The Details panel comes from a plugin of the package of the service, a built-in renderer, or the generic tree, see
    `cgse_tui.plugins`. A renderer can split the details over several panels. The detail screen of the service
    registry also has a table of the registrations, that of the Process Manager a table of the core services: `enter`
    shows the details of the selected service.

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
        layout: grid;
        grid-columns: 1fr;
        grid-rows: auto;
        height: auto;
    }
    DetailScreen #details-area .panel {
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
    ]

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
        self.service = service
        self._refresh = refresh
        self._renderers = renderers
        self._section_titles: list[str] = []
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
            yield Horizontal(id="details-area")
            yield panel("Registrations", RegistryTable(id="registrations"), id="registry-panel")
            yield panel("Core services", CoreServicesTable(id="core-services"), id="procman-panel")
        yield panel("Log", RichLog(id="log-tail", max_lines=MAX_LINES, wrap=True, markup=False), id="log-panel")
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

    def show_services(self, services: list[ServiceInfo]) -> None:
        """Follows the service in the given services; a service that is gone keeps its last information."""
        self._services = services
        service = next((s for s in services if s.service_type == self.service.service_type), None)
        self._gone = service is None
        if service is not None:
            self.service = service
        self.refresh_view()

    def refresh_view(self) -> None:
        if not self.is_mounted:
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
        if service.cgse_object == "log" and not self._tail_busy and not self._gone:
            if self._tail_requested_at is None or time.monotonic() - self._tail_requested_at >= TAIL_INTERVAL:
                self._tail_requested_at = time.monotonic()
                self._tail_busy = True
                self.run_worker(self._show_log_tail(), group="log-tail")

        if self._raw_report is not service.report:
            self._raw_report = service.report
            self.query_one("#raw", Pretty).update(service.report or "No status report received yet.")

    def _show_details(self, service: ServiceInfo) -> None:
        """Shows the sections of the Details renderer, a panel per section. The panels are only replaced when the
        titles of the sections change, otherwise their content is updated."""
        sections, source = self._renderers.render(service)
        titles = [title for title, _ in sections]
        area = self.query_one("#details-area")
        if titles != self._section_titles:
            self._section_titles = titles
            self._sections = [Static(renderable, classes="section") for _, renderable in sections]
            self._section_panels = [panel(title, static) for title, static in zip(titles, self._sections)]
            area.remove_children()
            area.styles.grid_size_columns = min(len(self._section_panels), MAX_SECTION_COLUMNS)
            area.mount_all(self._section_panels)
        else:
            for static, (_, renderable) in zip(self._sections, sections):
                if renderable is not static.content:  # the same object needn't be rendered again
                    static.update(renderable)
        self._section_panels[0].border_subtitle = source

    async def _show_log_tail(self) -> None:
        """Appends the log records that arrived since the last request."""
        try:
            maximum = FIRST_LINES if self._tail_seq == 0 else MAX_LINES
            answer = await self._log_tail(self.service, self._tail_seq, maximum)
        finally:
            self._tail_busy = False
        log = self.query_one("#log-tail", RichLog)
        panel_ = self.query_one("#log-panel")
        if answer is None:
            panel_.border_subtitle = "the logger doesn't answer"
            return
        if "records" not in answer:
            if self._tail_seq == 0:
                log.write(Text("This logger can't send its log lines, restart it with the current version.", "dim"))
                self._tail_seq = -1  # don't write the message again
            return
        last_seq = answer.get("last_seq") or 0
        if 0 < last_seq < self._tail_seq:
            log.write(Text("--- the logger was restarted ---", "dim"))
        for record in answer["records"]:
            log.write(format_record(record))
        self._tail_seq = last_seq
        panel_.border_subtitle = f"{last_seq} messages received"

    def action_toggle_raw(self) -> None:
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
