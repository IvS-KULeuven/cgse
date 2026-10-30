"""The detail screen: the status report of one service."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import Header
from textual.widgets import Pretty
from textual.widgets import Static

from cgse_tui.data.model import ServiceInfo


class DetailScreen(Screen):
    """Shows the last status report of a service."""

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, service: ServiceInfo):
        super().__init__()
        self.service = service

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            f"[b]{self.service.name}[/b] ({self.service.service_type}) – {self.service.state.value}", id="title"
        )
        with VerticalScroll():
            if self.service.report:
                yield Pretty(self.service.report, id="report")
            else:
                yield Static("No status report received yet.", id="report")
        yield Footer()
