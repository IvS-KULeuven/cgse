"""The overview screen: one row per service."""

from __future__ import annotations

import logging
import time

from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import RichLog

from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens.column_select import ColumnSelectScreen
from cgse_tui.screens.columns import DEFAULT_COLUMNS
from cgse_tui.screens.columns import Column
from cgse_tui.screens.columns import visible_columns
from cgse_tui.screens.detail import DetailScreen

INDICATOR_COLUMN = ""
"""The first column, without a label: a coloured square with the state of the service, see `state_indicator()`."""

INDICATOR_KEY = "indicator"

FILLED, FRAME = "■", "□"


def state_indicator(service: ServiceInfo) -> Text:
    """Returns the coloured square that shows the state of a service.

    - green: running
    - orange: running, but no connection with the device
    - red: not responding within the stale time
    - empty frame: not running
    - grey: registered, but no information received yet
    """
    if service.state is ServiceState.OK:
        if service.has_device and service.connected is False:
            return Text(FILLED, style="dark_orange")
        return Text(FILLED, style="green")
    if service.state is ServiceState.STALE:
        return Text(FILLED, style="red")
    if service.state is ServiceState.INACTIVE:
        return Text(FRAME)
    return Text(FILLED, style="grey50")


def service_row(service: ServiceInfo, columns: list[Column] | None = None, now: float | None = None) -> tuple[str, ...]:
    """The cells of a service for the given columns, by default the columns shown at start-up."""
    columns = visible_columns(DEFAULT_COLUMNS) if columns is None else columns
    now = time.time() if now is None else now
    return tuple(column.value(service, now) for column in columns)


logger = logging.getLogger("cgse_tui.overview")

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

    BINDINGS = [("r", "refresh", "Refresh"), ("l", "toggle_log", "Log"), ("o", "select_columns", "Columns")]

    def __init__(self):
        super().__init__()
        self.services: dict[str, ServiceInfo] = {}
        self.columns: list[Column] = visible_columns(DEFAULT_COLUMNS)
        self._mounted = False

    def compose(self) -> ComposeResult:
        yield Header()
        # The cell's own colour wins on the cursor row, so the state indicator keeps its colour when selected
        yield DataTable(id="services", cursor_type="row", zebra_stripes=True, cursor_foreground_priority="renderable")
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
        self._add_columns(self.query_one("#services", DataTable))
        self._mounted = True

    def _add_columns(self, table: DataTable) -> None:
        table.add_column(INDICATOR_COLUMN, key=INDICATOR_KEY)
        for column in self.columns:
            table.add_column(column.label, key=column.key)

    def action_select_columns(self) -> None:
        self.app.push_screen(ColumnSelectScreen([column.key for column in self.columns], self.set_columns))

    def set_columns(self, keys) -> None:
        """Shows the columns with the given keys, in the order of `columns.COLUMNS`."""
        columns = visible_columns(keys)
        if columns == self.columns:
            return
        self.columns = columns
        if not self._mounted:
            return
        table = self.query_one("#services", DataTable)
        cursor_row = table.cursor_row
        table.clear(columns=True)
        self._add_columns(table)
        self.show_services(list(self.services.values()))
        table.move_cursor(row=cursor_row)

    def show_services(self, services: list[ServiceInfo]) -> None:
        """Updates the table with the given services, the rows are keyed by service type."""
        if not self._mounted:
            return
        table = self.query_one("#services", DataTable)
        self.services = {service.service_type: service for service in services}
        shown = {row_key.value for row_key in table.rows}

        for service_type in shown - self.services.keys():
            table.remove_row(service_type)

        now = time.time()
        keys = [INDICATOR_KEY, *(column.key for column in self.columns)]
        added = False
        for service_type, service in self.services.items():
            cells = (state_indicator(service), *service_row(service, self.columns, now))
            if service_type in shown:
                for key, value in zip(keys, cells):
                    table.update_cell(service_type, key, value)
            else:
                table.add_row(*cells, key=service_type)
                added = True

        if added:
            table.sort("name", key=lambda name: name.lower())

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
            logger.info("Refresh: polling the registry and the services ...")
            self.run_worker(self._refresh(collector), group="refresh", exclusive=True)

    async def _refresh(self, collector) -> None:
        await collector.poll()
        logger.info("Refresh done.")
        update_overview = getattr(self.app, "update_overview", None)
        if update_overview is not None:
            update_overview()
