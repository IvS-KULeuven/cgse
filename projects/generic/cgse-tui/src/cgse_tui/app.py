"""The Textual application."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App
from textual.screen import Screen

from cgse_tui.data.collector import Collector
from cgse_tui.logs import BufferedLogHandler
from cgse_tui.logs import capture_logging
from cgse_tui.logs import create_log_file_handler
from cgse_tui.screens.overview import OverviewScreen


class CgseTuiApp(App):
    """Shows the status of the CGSE core services and device control servers.

    While the app runs, log messages are shown in the log pane of the overview instead of on the terminal.

    Args:
        collector: collects the status of the services, a default `Collector` when None.
        refresh_interval: seconds between two updates of the overview.
        log_file: file that gets all log messages, also those that are not shown in the log pane, e.g. the timeouts
            of the client libraries. No log file when None.
    """

    TITLE = "CGSE"
    SUB_TITLE = "Status of services and devices"

    def __init__(self, collector: Collector | None = None, refresh_interval: float = 1.0, log_file: Path | None = None):
        super().__init__()
        self.log_file = log_file
        self.log_handler = BufferedLogHandler()
        self._restore_logging = None
        self.collector = collector if collector is not None else Collector()
        self.refresh_interval = refresh_interval
        self.overview = OverviewScreen()

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

        logger = logging.getLogger("cgse_tui.app")
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

    def update_overview(self) -> None:
        self.overview.show_services(self.collector.snapshot())
        if messages := self.log_handler.drain():
            self.overview.show_log_messages(messages)
