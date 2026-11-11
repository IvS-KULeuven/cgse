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
from cgse_tui.screens.logview import FOLLOW_HINT
from cgse_tui.screens.logview import FollowingLog
from cgse_tui.screens.panels import state_indicator

INDICATOR_COLUMN = ""
"""The first column, without a label: a coloured square with the state of the service, see `state_indicator()`."""

INDICATOR_KEY = "indicator"


def service_row(service: ServiceInfo, columns: list[Column] | None = None, now: float | None = None) -> tuple[str, ...]:
    """The cells of a service for the given columns, by default the columns shown at start-up."""
    columns = visible_columns(DEFAULT_COLUMNS) if columns is None else columns
    now = time.time() if now is None else now
    return tuple(column.value(service, now) for column in columns)


logger = logging.getLogger("cgse_tui.overview")

LOG_STYLES = {logging.WARNING: "yellow", logging.ERROR: "red", logging.CRITICAL: "bold red"}


def _log_style(level: int) -> str:
    return next((style for minimum, style in sorted(LOG_STYLES.items(), reverse=True) if level >= minimum), "")


class LogPane(FollowingLog):
    """The log messages of the TUI below the table. It follows the new messages, or keeps its position when scrolled
    up, which its top border tells. With the focus, `m` makes it fill the screen and back (`esc` too)."""

    BINDINGS = [*FollowingLog.BINDINGS, ("m", "toggle_maximized", "Maximize log")]

    def show_follow_state(self) -> None:
        self.border_title = "" if self.follows else FOLLOW_HINT

    def action_toggle_maximized(self) -> None:
        if self.screen.maximized is self:
            self.screen.minimize()
        else:
            self.screen.maximize(self, container=False)


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
    OverviewScreen #log.-maximized {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("a", "select_action", "Actions"),
        ("l", "toggle_log", "Log"),
        ("L", "show_logs", "Log screen"),
        ("o", "select_columns", "Columns"),
    ]

    def __init__(self):
        super().__init__()
        self.services: dict[str, ServiceInfo] = {}
        self.columns: list[Column] = visible_columns(DEFAULT_COLUMNS)
        self._mounted = False

    def compose(self) -> ComposeResult:
        yield Header()
        # The cell's own colour wins on the cursor row, so the state indicator keeps its colour when selected
        yield DataTable(id="services", cursor_type="row", zebra_stripes=True, cursor_foreground_priority="renderable")
        yield LogPane(id="log", max_lines=1000)
        yield Footer()

    def show_log_messages(self, messages: list[tuple[int, str]]) -> None:
        """Appends (level, text) log messages to the log pane."""
        self.query_one("#log", LogPane).write_lines(
            Text(message, style=_log_style(level)) for level, message in messages
        )

    def action_toggle_log(self) -> None:
        if self.maximized is not None:
            self.minimize()
        log = self.query_one("#log", RichLog)
        log.display = not log.display

    def action_show_logs(self) -> None:
        show_logs = getattr(self.app, "show_logs", None)
        if show_logs is not None:
            show_logs()

    def on_mount(self) -> None:
        self._add_columns(self.query_one("#services", DataTable))
        self._mounted = True

    def _add_columns(self, table: DataTable) -> None:
        table.add_column(INDICATOR_COLUMN, key=INDICATOR_KEY)
        for column in self.columns:
            table.add_column(column.header(), key=column.key)

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
            cells = (state_indicator(service), *(column.cell(service, now) for column in self.columns))
            if service.state is ServiceState.INACTIVE:  # not running: dimmed
                for cell in cells[1:]:
                    cell.stylize("dim")
            if service_type in shown:
                for key, value in zip(keys, cells):
                    # A column is sized to its content when a row is added, e.g. still without host at start-up
                    table.update_cell(service_type, key, value, update_width=True)
            else:
                table.add_row(*cells, key=service_type)
                added = True

        if added:
            table.sort("name", key=lambda name: str(name).lower())

    def selected_service(self) -> ServiceInfo | None:
        table = self.query_one("#services", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return self.services.get(row_key.value)

    def action_select_action(self) -> None:
        service = self.selected_service()
        if service is not None:
            self.app.select_action(service)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key.value in self.services:
            self.app.show_details(event.row_key.value)

    def action_refresh(self) -> None:
        collector = getattr(self.app, "collector", None)
        if collector is not None:
            logger.info("Refresh: polling the registry and requesting the status of all services ...")
            self.run_worker(self._refresh(collector), group="refresh", exclusive=True)

    async def _refresh(self, collector) -> None:
        await collector.poll(reports=True)
        logger.info("Refresh done.")
        update_overview = getattr(self.app, "update_overview", None)
        if update_overview is not None:
            update_overview()
