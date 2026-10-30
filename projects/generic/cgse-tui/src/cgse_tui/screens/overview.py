"""The overview screen: one row per service."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable
from textual.widgets import Footer
from textual.widgets import Header

from cgse_tui.data.model import ServiceInfo
from cgse_tui.screens.detail import DetailScreen

COLUMNS = ("Name", "Type", "Host", "State", "Uptime", "PID", "CPU %", "Memory", "Device", "Simulator")


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
        format_flag(service.connected, "connected", "not connected"),
        format_flag(service.sim_mode, "yes", "no"),
    )


class OverviewScreen(Screen):
    """Shows all services in a table. Select a row to see the status report of that service."""

    BINDINGS = [("r", "refresh", "Refresh")]

    def __init__(self):
        super().__init__()
        self.services: dict[str, ServiceInfo] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="services", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#services", DataTable).add_columns(*COLUMNS)

    def show_services(self, services: list[ServiceInfo]) -> None:
        """Replaces the rows of the table by the given services."""
        table = self.query_one("#services", DataTable)
        table.clear()
        self.services = {service.name: service for service in services}
        for service in services:
            table.add_row(*service_row(service), key=service.name)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        service = self.services.get(event.row_key.value)
        if service is not None:
            self.app.push_screen(DetailScreen(service))

    def action_refresh(self) -> None:
        # The data layer is added in the next step, until then there is nothing to refresh.
        self.notify("Data collection is not implemented yet.")
