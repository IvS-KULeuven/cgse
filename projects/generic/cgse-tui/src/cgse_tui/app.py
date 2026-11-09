"""The Textual application."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App
from textual.screen import Screen

from cgse_tui.data.actions import ServiceActions
from cgse_tui.data.collector import Collector
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.logs import BufferedLogHandler
from cgse_tui.logs import capture_logging
from cgse_tui.logs import create_log_file_handler
from cgse_tui.plugins import DetailsRenderers
from cgse_tui.screens.action_select import ActionSelectScreen
from cgse_tui.screens.detail import DetailScreen
from cgse_tui.screens.help import DETAIL_SCREEN_ANCHOR
from cgse_tui.screens.help import HelpScreen
from cgse_tui.screens.overview import OverviewScreen

logger = logging.getLogger("cgse_tui.app")


class CgseTuiApp(App):
    """Shows the status of the CGSE core services and device control servers.

    While the app runs, log messages are shown in the log pane of the overview instead of on the terminal.

    Args:
        collector: collects the status of the services, a default `Collector` when None.
        refresh_interval: seconds between two updates of the overview.
        log_file: file that gets all log messages, also those that are not shown in the log pane, e.g. the timeouts
            of the client libraries. No log file when None.
        actions: starts, stops and restarts the services, a default `ServiceActions` when None.
    """

    BINDINGS = [("f1", "help", "Help")]

    TITLE = "CGSE"
    SUB_TITLE = "Status of services and devices"

    def __init__(
        self,
        collector: Collector | None = None,
        refresh_interval: float = 1.0,
        log_file: Path | None = None,
        actions: ServiceActions | None = None,
    ):
        super().__init__()
        self.log_file = log_file
        self.log_handler = BufferedLogHandler()
        self._restore_logging = None
        self.collector = collector if collector is not None else Collector()
        self.refresh_interval = refresh_interval
        self.actions = actions if actions is not None else ServiceActions(self.collector)
        self.overview = OverviewScreen()
        self.details_renderers = DetailsRenderers()

    def get_default_screen(self) -> Screen:
        return self.overview

    def on_load(self) -> None:
        handlers = [self.log_handler]
        file_error = None
        if self.log_file is not None:
            try:
                handlers.append(create_log_file_handler(self.log_file))
            except OSError as exc:
                file_error = exc
        self._restore_logging = capture_logging(*handlers)
        logging.getLogger("cgse_tui").setLevel(logging.INFO)  # e.g. the state changes logged by the collector

        if file_error is not None:
            logger.warning(f"Couldn't open the log file {self.log_file}: {file_error}")
        elif self.log_file is not None:
            logger.info(f"All log messages are also written to {self.log_file}")

    def on_mount(self) -> None:
        self.run_worker(self.collector.run(), name="collector", group="collector", exit_on_error=False)
        self.call_after_refresh(self.update_overview)  # the overview screen is mounted by then
        self.set_interval(self.refresh_interval, self.update_overview)

    def on_unmount(self) -> None:
        if self._restore_logging is not None:
            self._restore_logging()
            self._restore_logging = None

    def show_details(self, service_type: str) -> None:
        """Opens the detail screen of a service, e.g. selected in the overview or in the registrations."""
        service = next((s for s in self.collector.snapshot() if s.service_type == service_type), None)
        if service is None:
            self.notify(f"{service_type} is not known (yet).", severity="warning")
            return
        refresh = getattr(self.collector, "refresh_report", None)
        self.push_screen(DetailScreen(service, refresh=refresh and (lambda: refresh(service_type))))

    def action_help(self) -> None:
        """Shows the help, at the part about the detail screen when opened from there; F1 in the help closes it."""
        if isinstance(self.screen, HelpScreen):
            return
        anchor = DETAIL_SCREEN_ANCHOR if isinstance(self.screen, DetailScreen) else None
        self.push_screen(HelpScreen(anchor))

    def select_action(self, service: ServiceInfo) -> None:
        """Asks the user to start, stop or restart the service, and performs the selected action."""
        if self.actions.is_busy(service.service_type):
            self.notify(f"{service.name}: an action is still running.", severity="warning")
            return
        is_running = getattr(self.collector, "is_running", None)
        running = is_running(service.service_type) if is_running else service.state is not ServiceState.INACTIVE

        def perform(choice: tuple[str, bool, bool] | None) -> None:
            if choice is not None:
                action, simulator, verbose_debug = choice
                self.run_worker(self._perform(action, service, simulator, verbose_debug), group="actions")

        simulator_support = getattr(self.actions, "simulator_support", None)
        self.push_screen(ActionSelectScreen(service, running, simulator_support), perform)

    async def _perform(self, action: str, service: ServiceInfo, simulator: bool, verbose_debug: bool = False) -> None:
        ok = await self.actions.perform(action, service, simulator, verbose_debug=verbose_debug)
        if not ok:
            self.notify(f"{service.name}: {action} failed, see the log pane.", severity="error")
        self.update_overview()

    def update_overview(self) -> None:
        services = self.collector.snapshot()
        self.overview.show_services(services)
        for screen in self.screen_stack:
            if isinstance(screen, DetailScreen):
                screen.show_services(services)
        if messages := self.log_handler.drain():
            self.overview.show_log_messages(messages)
