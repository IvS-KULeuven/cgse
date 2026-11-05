"""The registrations in the service registry, as a table in the detail screen of the registry.

Select a registration (`enter`) to see the details of that service.
"""

from __future__ import annotations

import time
from typing import Any

from rich.text import Text
from textual.widgets import DataTable

from cgse_tui.screens.columns import format_age
from cgse_tui.screens.columns import format_uptime
from cgse_tui.screens.panels import format_value

HEALTH_STYLES = {"passing": "green", "critical": "red"}

COLUMNS = (
    ("name", "Name"),
    ("type", "Type"),
    ("object", "cgse object"),
    ("device_id", "Device ID"),
    ("host", "Host"),
    ("port", "Port"),
    ("health", "Health"),
    ("heartbeat", "Heartbeat"),
    ("ttl", "TTL"),
    ("pid", "PID"),
    ("uptime", "Uptime"),
)


def service_type(record: dict[str, Any]) -> str:
    """The service type of a registration, as the collector keys its services."""
    metadata = record.get("metadata") or {}
    return str(metadata.get("type") or record.get("name"))


def cells(record: dict[str, Any], now: float) -> tuple:
    metadata = record.get("metadata") or {}
    status = record.get("status") or {}
    health = str(record.get("health") or "")
    heartbeat = record.get("last_heartbeat")
    return (
        format_value(record.get("name")),
        service_type(record),
        format_value(metadata.get("cgse_object")),
        format_value(metadata.get("device_id")),
        format_value(record.get("host")),
        Text(format_value(record.get("port")), justify="right"),
        Text(health, style=HEALTH_STYLES.get(health, "")),
        Text(f"{format_age(heartbeat, now)} ago" if heartbeat else "", justify="right"),
        Text(f"{record['ttl']} s" if record.get("ttl") is not None else "", justify="right"),
        Text(format_value(status.get("pid")), justify="right"),
        Text(format_uptime(status.get("uptime_s")), justify="right"),
    )


class RegistryTable(DataTable):
    """The registrations of the registry, updated in place so the cursor stays on its row."""

    def __init__(self, **kwargs):
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.service_types: dict[str, str] = {}
        """Service type by row key (the registration id)."""

    def on_mount(self) -> None:
        for key, label in COLUMNS:
            self.add_column(label, key=key)

    def show(self, report: dict[str, Any], now: float | None = None) -> None:
        now = time.time() if now is None else now
        records = {
            str(record.get("id") or record.get("name")): record
            for record in report.get("services") or []
            if isinstance(record, dict)
        }
        for key in set(self.service_types) - records.keys():
            self.remove_row(key)
            del self.service_types[key]
        added = False
        for key, record in records.items():
            values = cells(record, now)
            if key in self.service_types:
                for (column, _), value in zip(COLUMNS, values):
                    self.update_cell(key, column, value, update_width=True)
            else:
                self.add_row(*values, key=key)
                added = True
            self.service_types[key] = service_type(record)
        if added:
            self.sort("name", key=lambda name: str(name).lower())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        if service_type := self.service_types.get(event.row_key.value):
            self.app.show_details(service_type)
