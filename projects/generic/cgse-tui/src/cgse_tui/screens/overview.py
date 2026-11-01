"""The overview screen: one row per service."""

from __future__ import annotations

import logging

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import RichLog

from cgse_tui.data.model import ServiceInfo
from cgse_tui.screens.detail import DetailScreen

COLUMNS = ("Name", "Type", "Host", "State", "Uptime", "PID", "CPU %", "Memory", "Device", "Simulator")

NOT_APPLICABLE = "–"
"""Shown in the device columns of a service that controls no device. An empty cell means: not known."""


def format_uptime(seconds: float | None) -> str:
    if seconds is None:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}" if days else f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_bytes(value: int | None) -> str:
    if value is None:
        return ""
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""  # not reached


def format_flag(value: bool | None, true: str, false: str) -> str:
    return "" if value is None else (true if value else false)


def service_row(service: ServiceInfo) -> tuple[str, ...]:
    return (
        service.name,
        service.service_type,
        service.host or "",
        service.state.value,
        format_uptime(service.uptime_s),
        "" if service.pid is None else str(service.pid),
        "" if service.cpu_percent is None else f"{service.cpu_percent:.1f}",
        format_bytes(service.rss),
        NOT_APPLICABLE if service.has_device is False else format_flag(service.connected, "connected", "not connected"),
        NOT_APPLICABLE if service.has_device is False else format_flag(service.sim_mode, "yes", "no"),
    )


LOG_STYLES = {logging.WARNING: "yellow", logging.ERROR: "red", logging.CRITICAL: "bold red"}


class OverviewScreen(Screen):
    """Shows all services in a table, and the log messages below it. Select a row to see the status report."""

    DEFAULT_CSS = """
    OverviewScreen #services {
        height: 1fr;
    }
    OverviewScreen #log {
        height: 10;
        border-top: solid $secondary;
    }
    """

    BINDINGS = [("r", "refresh", "Refresh"), ("l", "toggle_log", "Log")]

    def __init__(self):
        super().__init__()
        self.services: dict[str, ServiceInfo] = {}
        self._columns = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="services", cursor_type="row", zebra_stripes=True)
        yield RichLog(id="log", max_lines=1000, wrap=False)
        yield Footer()

    def show_log_messages(self, messages: list[tuple[int, str]]) -> None:
        """Appends (level, text) log messages to the log pane."""
        log = self.query_one("#log", RichLog)
        for level, message in messages:
            style = next((style for minimum, style in sorted(LOG_STYLES.items(), reverse=True) if level >= minimum), "")
            log.write(Text(message, style=style))

    def action_toggle_log(self) -> None:
        log = self.query_one("#log", RichLog)
        log.display = not log.display

    def on_mount(self) -> None:
        self._columns = self.query_one("#services", DataTable).add_columns(*COLUMNS)

    def show_services(self, services: list[ServiceInfo]) -> None:
        """Updates the table with the given services, the rows are keyed by service type."""
        if not self._columns:
            return  # not mounted yet
        table = self.query_one("#services", DataTable)
        self.services = {service.service_type: service for service in services}
        shown = {row_key.value for row_key in table.rows}

        for service_type in shown - self.services.keys():
            table.remove_row(service_type)

        added = False
        for service_type, service in self.services.items():
            cells = service_row(service)
            if service_type in shown:
                for column, value in zip(self._columns, cells):
                    table.update_cell(service_type, column, value)
            else:
                table.add_row(*cells, key=service_type)
                added = True

        if added:
            table.sort(self._columns[0], key=lambda name: name.lower())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        service = self.services.get(event.row_key.value)
        if service is None:
            return
        collector = getattr(self.app, "collector", None)
        refresh = None if collector is None else (lambda: collector.refresh_report(service.service_type))
        self.app.push_screen(DetailScreen(service, refresh=refresh))

    def action_refresh(self) -> None:
        collector = getattr(self.app, "collector", None)
        if collector is not None:
            self.run_worker(collector.poll(), group="refresh", exclusive=True)
