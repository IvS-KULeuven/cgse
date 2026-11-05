"""The core services of the Process Manager, as a table in the detail screen of the Process Manager.

The Process Manager reports the core services it manages (name and service type); their state, process and
resources come from the TUI itself, as in the overview. Select a service (`enter`) to see its details.
"""

from __future__ import annotations

import time
from typing import Any

from textual.widgets import DataTable

from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens.columns import COLUMNS_BY_KEY
from cgse_tui.screens.panels import state_indicator

INDICATOR = "indicator"

COLUMNS = ("type", "state", "host", "pid", "uptime", "cpu", "memory")
"""The columns of the overview that are shown, after the indicator and the name of the Process Manager."""


def core_processes(report: dict[str, Any]) -> dict[str, str]:
    """The core services in the status report of the Process Manager, as name to service type."""
    details = report.get("details")
    processes = details.get("core_processes") if isinstance(details, dict) else None
    return {str(name): str(service_type) for name, service_type in (processes or {}).items()}


class CoreServicesTable(DataTable):
    """The core services of the Process Manager with their state in the TUI, updated in place."""

    def __init__(self, **kwargs):
        super().__init__(cursor_type="row", zebra_stripes=True, cursor_foreground_priority="renderable", **kwargs)
        self.running = 0
        """The number of core services that are running (ok)."""

    def on_mount(self) -> None:
        self.add_column("", key=INDICATOR)
        self.add_column("Name", key="name")
        for key in COLUMNS:
            self.add_column(COLUMNS_BY_KEY[key].header(), key=key)

    def show(self, report: dict[str, Any], services: list[ServiceInfo], now: float | None = None) -> None:
        now = time.time() if now is None else now
        processes = core_processes(report)
        by_type = {service.service_type: service for service in services}
        shown = {row_key.value for row_key in self.rows}

        for service_type in shown - set(processes.values()):
            self.remove_row(service_type)
        self.running = 0
        added = False
        for name, service_type in processes.items():
            service = by_type.get(service_type) or ServiceInfo(name=name, service_type=service_type)
            self.running += service.state is ServiceState.OK
            cells = (state_indicator(service), name, *(COLUMNS_BY_KEY[key].cell(service, now) for key in COLUMNS))
            if service_type in shown:
                for key, value in zip((INDICATOR, "name", *COLUMNS), cells):
                    self.update_cell(service_type, key, value, update_width=True)
            else:
                self.add_row(*cells, key=service_type)
                added = True
        if added:
            self.sort("name", key=lambda name: str(name).lower())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        self.app.show_details(event.row_key.value)
