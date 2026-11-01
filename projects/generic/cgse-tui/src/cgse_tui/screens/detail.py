"""The detail screen: the status report of one service."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Pretty
from textual.widgets import Static

from cgse_tui.data.model import ServiceInfo

logger = logging.getLogger("cgse_tui.detail")


class DetailScreen(Screen):
    """Shows the last status report of a service, and requests a new one when opened or refreshed.

    Args:
        service: the service to show.
        refresh: coroutine function that requests the status again and returns the updated service.
    """

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("r", "refresh", "Refresh")]

    def __init__(self, service: ServiceInfo, refresh: Callable[[], Awaitable[ServiceInfo | None]] | None = None):
        super().__init__()
        self.service = service
        self._refresh = refresh

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._title(), id="title")
        with VerticalScroll():
            yield Pretty(self.service.report or "No status report received yet.", id="report")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    def _title(self) -> str:
        service = self.service
        return f"[b]{service.name}[/b] ({service.service_type}) – {service.state.value}"

    def action_refresh(self) -> None:
        if self._refresh is not None:
            logger.info(f"Requesting the status of {self.service.name} ...")
            self.notify(f"Requesting the status of {self.service.name} ...", timeout=2)
            self.run_worker(self._update(), group="refresh", exclusive=True)

    async def _update(self) -> None:
        service = await self._refresh()
        if service is None:
            return
        if service.report:
            logger.info(f"Status of {service.name} received.")
        else:
            logger.warning(f"No status received from {service.name}.")
        self.service = service
        self.query_one("#title", Static).update(self._title())
        self.query_one("#report", Pretty).update(service.report or "No status report received.")
