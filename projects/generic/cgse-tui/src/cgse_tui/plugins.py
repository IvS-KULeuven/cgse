"""The content of the Details panel: a plugin of the package of the service, a built-in renderer, or the generic tree.

A package that provides a control server can show the details of its service in its own way. It registers a function
in the entry-point group `cgse.tui.details`, with the `cgse_object` of the service as name, e.g. in the
`pyproject.toml` of `symetrie-hexapod`:

    [project.entry-points."cgse.tui.details"]
    puna = "symetrie_hexapod.tui_details:details"

The function is called with the last status report and the device values of the last monitoring message:

    Section = dict[str, RenderableType]

    def details(report: dict, live: dict) -> RenderableType | Section | list[Section]

It returns a Rich renderable, a dictionary of titled renderables that are shown as separate panels side by side (at
most three per row), or a list of such dictionaries, one per row: a row with a single panel takes the full width. The
function only uses Rich, so the package doesn't depend on Textual or on this package. A renderer that returns the
same renderable object as the previous call, e.g. from a cache, saves the time to render it again. See
`docs/dev_guide/plugins.md`.

The Details panel takes, in this order: the plugin for the `cgse_object` of the service, the built-in renderer of
the TUI for the core services, or the generic tree of `cgse_tui.screens.panels`. A plugin that can't be loaded, that
raises an exception, or that returns something Rich can't render, is logged once and the generic tree is shown.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderableType
from rich.protocol import is_renderable
from rich.text import Text

from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.monitor import live_values
from cgse_tui.data.services import custom_kind
from cgse_tui.screens import panels

logger = logging.getLogger("cgse_tui.plugins")

ENTRY_POINT_GROUP = "cgse.tui.details"

DETAILS = "Details"
"""Title of the panel when the renderer returns a single renderable."""

Renderer = Callable[[dict[str, Any], dict[str, Any]], Any]
Sections = list[tuple[str, RenderableType]]
Rows = list[Sections]
"""The sections of the Details panel by row, the screen shows each row as a grid of panels."""


def latest_details(report: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    """The `details` of the status report updated with the newer live values of the monitoring message."""
    details = report.get("details") if isinstance(report, dict) else None
    if not isinstance(details, dict) or panels.error_of(details):
        details = {}
    return {**details, **live}


def load_entry_points() -> dict[str, Callable[[], Renderer]]:
    """The loaders of the plugins in the entry-point group, by `cgse_object`. Nothing is imported yet."""
    from egse.plugin import entry_points

    return {ep.name: ep.load for ep in entry_points(ENTRY_POINT_GROUP)}


class Guarded:
    """Renders a renderable of a plugin; an exception while it is rendered shows an error instead of crashing."""

    def __init__(self, renderable: RenderableType, on_error: Callable[[Exception], None]):
        self.renderable = renderable
        self.on_error = on_error

    def __rich_console__(self, console: Console, options: ConsoleOptions):
        try:
            lines = list(console.render(self.renderable, options))
        except Exception as exc:
            self.on_error(exc)
            yield Text(f"The plugin couldn't be rendered: {type(exc).__name__}: {exc}", style="red")
            return
        yield from lines


class DetailsRenderers:
    """Finds and calls the renderer of the Details panel of a service.

    Args:
        builtins: the built-in renderers by `cgse_object`, by default those of `cgse_tui.details`.
        entry_points: returns the plugin loaders by `cgse_object`, by default from the entry-point group.
    """

    def __init__(
        self,
        builtins: dict[str, Renderer] | None = None,
        entry_points: Callable[[], dict[str, Callable[[], Renderer]]] = load_entry_points,
    ):
        if builtins is None:
            from cgse_tui.details import BUILTINS

            builtins = BUILTINS
        self.builtins = builtins
        self._entry_points = entry_points
        self._loaders: dict[str, Callable[[], Renderer]] | None = None
        self._plugins: dict[str, Renderer | None] = {}
        self._logged: set[tuple[str, str]] = set()
        self._guarded: dict[tuple[str, str], Guarded] = {}

    def plugin(self, cgse_object: str | None) -> Renderer | None:
        """The plugin for the `cgse_object`, loaded the first time it's needed; None when there is none or it
        couldn't be loaded."""
        if not cgse_object:
            return None
        if cgse_object not in self._plugins:
            if self._loaders is None:
                try:
                    self._loaders = self._entry_points()
                except Exception as exc:
                    logger.warning(f"Couldn't read the entry points {ENTRY_POINT_GROUP}: {type(exc).__name__}: {exc}")
                    self._loaders = {}
            renderer = None
            if loader := self._loaders.get(cgse_object):
                try:
                    renderer = loader()
                except Exception as exc:
                    logger.warning(
                        f"Couldn't load the details plugin for {cgse_object}: {type(exc).__name__}: {exc}",
                        exc_info=True,
                    )
            self._plugins[cgse_object] = renderer
        return self._plugins[cgse_object]

    def render(self, service: ServiceInfo) -> tuple[Sections, str]:
        """The sections of the Details panel, all rows after each other, and the source shown in its border."""
        rows, source = self.render_rows(service)
        return [section for row in rows for section in row], source

    def render_rows(self, service: ServiceInfo) -> tuple[Rows, str]:
        """The sections of the Details panel by row, and the source shown in its border."""
        generic = panels.details_panel(service)
        if not self._has_data(service):
            return [[(DETAILS, generic[0])]], generic[1]

        cgse_object = service.cgse_object
        renderer, source = self.plugin(cgse_object), f"plugin {cgse_object}"
        if renderer is None:
            renderer, source = self.builtins.get(cgse_object or ""), generic[1]
        if renderer is None:
            return [[(DETAILS, generic[0])]], generic[1]

        try:
            result = renderer(service.report, live_values(service.monitoring))
            rows = self._rows(result)
        except Exception as exc:
            self._log_error(cgse_object, exc)
            return [[(DETAILS, generic[0])]], f"{source} failed, see the log".strip()

        def on_error(exc: Exception) -> None:
            self._log_error(cgse_object, exc)

        guarded = [
            [(title, self._guard(service, title, renderable, on_error)) for title, renderable in row] for row in rows
        ]
        return guarded, source

    def _guard(self, service: ServiceInfo, title: str, renderable: RenderableType, on_error) -> Guarded:
        """The guarded renderable; the same object as before when the renderer returned the same renderable, so the
        screen doesn't render it again, e.g. a Setup that is cached by the renderer."""
        key = (service.service_type, title)
        guarded = self._guarded.get(key)
        if guarded is None or guarded.renderable is not renderable:
            guarded = self._guarded[key] = Guarded(renderable, on_error)
        return guarded

    @staticmethod
    def _has_data(service: ServiceInfo) -> bool:
        """False when the Details panel only shows a message, e.g. "No status report received yet"."""
        if custom_kind(service):
            return bool(service.report)
        if live_values(service.monitoring):
            return True
        report = service.report
        return "control_server" in report and not panels.error_of(report.get("details"))

    @classmethod
    def _rows(cls, result: Any) -> Rows:
        """The rows of sections: a list of dictionaries is a row per dictionary, anything else is one row."""
        if isinstance(result, list):
            if not result or not all(isinstance(row, dict) for row in result):
                raise TypeError("a list of rows shall contain dictionaries of titled renderables")
            rows = [cls._sections(row) for row in result]
            titles = [title for row in rows for title, _ in row]
            if len(titles) != len(set(titles)):
                raise ValueError(f"the titles of the sections shall be unique, got {titles}")
            return rows
        return [cls._sections(result)]

    @staticmethod
    def _sections(result: Any) -> Sections:
        if isinstance(result, dict):
            sections = [(str(title), renderable) for title, renderable in result.items()]
        else:
            sections = [(DETAILS, result)]
        if not sections:
            raise ValueError("no sections")
        for title, renderable in sections:
            if not is_renderable(renderable):
                raise TypeError(f"section {title!r} is not a Rich renderable but {type(renderable).__name__}")
        return sections

    def _log_error(self, cgse_object: str | None, exc: Exception) -> None:
        key = (cgse_object or "", f"{type(exc).__name__}: {exc}")
        if key not in self._logged:
            self._logged.add(key)
            logger.error(f"The details of {cgse_object} couldn't be shown: {key[1]}", exc_info=exc)
