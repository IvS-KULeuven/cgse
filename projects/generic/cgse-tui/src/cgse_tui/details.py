"""The built-in renderers of the Details panel for the core services, by `cgse_object`, see `cgse_tui.plugins`.

They have the same signature as a plugin: `details(report, live)` returns a Rich renderable or titled renderables.
The registry also gets a table of its registrations in the detail screen, see `cgse_tui.screens.registry`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.console import RenderableType
from rich.text import Text

from cgse_tui.data.model import Level
from cgse_tui.plugins import latest_details
from cgse_tui.screens.columns import LEVEL_STYLES
from cgse_tui.screens.panels import format_value
from cgse_tui.screens.panels import generic
from cgse_tui.screens.panels import key_values

DISK_WARNING, DISK_CRITICAL = 80.0, 90.0
"""Percentage of the disk in use for a warning and for critical."""

BAR_WIDTH = 30

GIB = 2**30


def registry(report: dict[str, Any], live: dict[str, Any]) -> RenderableType:
    """The service registry: the number of registrations by health. The registrations are in their own table."""
    services = [service for service in report.get("services") or [] if isinstance(service, dict)]
    health = Counter(str(service.get("health") or "unknown") for service in services)
    summary = Text(f"{len(services)} registered")
    for name, count in sorted(health.items()):
        summary.append(", ")
        summary.append(f"{count} {name}", style={"passing": "green", "critical": "red"}.get(name, ""))
    return key_values(
        [
            ("Services", summary),
            ("Unique service types", report.get("enforce_unique_service_types")),
        ]
    )


def disk_level(percent: float) -> Level:
    return Level.CRITICAL if percent >= DISK_CRITICAL else Level.WARNING if percent >= DISK_WARNING else Level.OK


def disk_bar(usage: Any) -> RenderableType:
    """A bar with the part of the disk in use, e.g. "██████░░░░ 13 % used, 827.1 of 951.9 GiB free"."""
    if not isinstance(usage, dict) or not usage.get("total"):
        return Text(format_value(usage))
    total, used, free = usage["total"], usage.get("used") or 0, usage.get("free") or 0
    percent = 100 * used / total
    style = LEVEL_STYLES[disk_level(percent)] or "green"
    filled = round(BAR_WIDTH * used / total)
    return Text.assemble(
        ("█" * filled, style),
        ("░" * (BAR_WIDTH - filled), "dim"),
        f" {percent:.0f} % used, {free / GIB:.1f} of {total / GIB:.1f} GiB free",
    )


def storage(report: dict[str, Any], live: dict[str, Any]) -> RenderableType:
    """The Storage Manager: where the data goes, how full the disk is, and what is stored."""
    details = report.get("details") or {}
    registrations = details.get("registrations") or []
    return Group(
        key_values(
            [
                ("Location", details.get("storage_location")),
                ("Disk", disk_bar(details.get("disk_usage"))),
                ("Loaded Setup", details.get("loaded_setup_id")),
                ("Observation", details.get("obsid") or Text("none running", style="dim")),
                ("Registrations", f"{len(registrations)}: {format_value(registrations)}" if registrations else None),
            ]
        )
    )


def setup_info(setup: Any) -> tuple[str | None, str | None, str | None]:
    """The ID, the folder and the file name of a Setup, None when they're not known.

    The folder is on the machine of the Configuration Manager, which can be another machine than that of the TUI.
    """
    setup_id = folder = filename = None
    try:
        setup_id = setup.get_id()
        if setup.has_private_attribute("_filename"):
            path = Path(setup.get_private_attribute("_filename"))
            folder, filename = str(path.parent), path.name
    except AttributeError:
        pass
    return setup_id, folder, filename


_setup_tree: tuple[tuple, RenderableType] | None = None
"""The tree of the last Setup: rendering a large Setup takes a while, it's only rebuilt for another Setup."""


def setup_tree(setup: dict, key: tuple) -> RenderableType:
    """The whole Setup as a tree, the same object as long as the key (Setup ID and file) is the same.

    By convention the `history` of the Setup comes last.
    """
    global _setup_tree
    if _setup_tree is None or _setup_tree[0] != key:
        ordered = {name: value for name, value in setup.items() if name != "history"}
        if "history" in setup:
            ordered["history"] = setup["history"]
        _setup_tree = key, generic(ordered, max_group_size=None)
    return _setup_tree[1]


def folder_on_host(folder: str | None, report: dict[str, Any]) -> Text | None:
    """The folder with the host of the Configuration Manager, e.g. "/data/LAB/conf  on 192.168.68.75"."""
    if folder is None:
        return None
    control_server = report.get("control_server")
    host = control_server.get("hostname") if isinstance(control_server, dict) else None
    return Text.assemble(folder, (f"  on {host}", "dim") if host else "")


def configuration_manager(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The Configuration Manager: the running observation and the loaded Setup.

    The status report has `obsid_active`, `obsid`, `setup_id` and `site_id`, the monitoring messages of the CM have
    the `obsid` and the whole `setup`, which is shown in its own panel.
    """
    values = latest_details(report, live)
    setup = live.get("setup")
    file_id, folder, filename = setup_info(setup)
    setup_id = values.get("setup_id") or file_id
    obsid = values.get("obsid")
    active = obsid is not None if "obsid" in live else values.get("obsid_active")

    rows = [
        ("Observation", Text(f"running: {obsid}", style="green") if active else Text("none running", style="dim")),
        ("Setup", setup_id),
        ("Site", values.get("site_id") or (setup.get("site_id") if isinstance(setup, dict) else None)),
        ("Folder", folder_on_host(folder, report)),
        ("File", filename),
    ]
    sections = {"Configuration": key_values([(label, value) for label, value in rows if value is not None])}
    if isinstance(setup, dict) and setup:
        sections[f"Setup {setup_id}"] = setup_tree(setup, (setup_id, filename))
    return sections


def process_manager(report: dict[str, Any], live: dict[str, Any]) -> RenderableType:
    """The Process Manager: the number of core services it manages, which are listed in their own table."""
    processes = (report.get("details") or {}).get("core_processes") or {}
    return key_values([("Core services", f"{len(processes)} managed")])


BUILTINS = {"reg": registry, "sm": storage, "cm": configuration_manager, "pm": process_manager}
"""The built-in renderers by `cgse_object`."""
