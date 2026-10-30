"""The Textual application."""

from __future__ import annotations

from textual.app import App
from textual.screen import Screen

from cgse_tui.screens.overview import OverviewScreen


class CgseTuiApp(App):
    """Shows the status of the CGSE core services and device control servers."""

    TITLE = "CGSE"
    SUB_TITLE = "Status of services and devices"
    BINDINGS = [("q", "quit", "Quit")]

    def get_default_screen(self) -> Screen:
        return OverviewScreen()
