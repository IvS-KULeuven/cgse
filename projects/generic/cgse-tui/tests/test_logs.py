"""Tests for showing log messages in the TUI instead of on the terminal."""

import asyncio
import logging
import threading

import egse.log  # noqa: F401  # attaches the console handlers to the egse and root loggers
from textual.widgets import RichLog

from cgse_tui.app import CgseTuiApp
from cgse_tui.logs import BufferedLogHandler
from cgse_tui.logs import capture_logging
from cgse_tui.logs import quiet


def console_handler_names():
    loggers = (logging.getLogger(), logging.getLogger("egse"))
    return {handler.name for logger in loggers for handler in logger.handlers if type(handler) is logging.StreamHandler}


def test_buffered_log_handler_keeps_messages_from_other_threads():
    handler = BufferedLogHandler(max_messages=3)
    logger = logging.getLogger("cgse_tui.tests.buffer")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        thread = threading.Thread(target=lambda: logger.warning("from a thread"))
        thread.start()
        thread.join()
        for index in range(3):
            logger.info(f"message {index}")
    finally:
        logger.removeHandler(handler)

    messages = handler.drain()
    assert [message.split(": ", 1)[1] for _, message in messages] == ["message 0", "message 1", "message 2"]
    assert handler.drain() == []


def test_capture_logging_replaces_and_restores_the_console_handlers():
    before = console_handler_names()
    assert {"egse_console_handler", "root_console_handler"} <= before

    handler = BufferedLogHandler()
    restore = capture_logging(handler)
    try:
        assert console_handler_names() == set()
        logging.getLogger("egse.tests").warning("captured")
        assert any("captured" in message for _, message in handler.drain())
    finally:
        restore()

    assert console_handler_names() == before
    assert handler not in logging.getLogger().handlers


class EmptyCollector:
    async def run(self):
        pass

    def snapshot(self):
        return []


async def test_log_messages_are_shown_in_the_log_pane():
    before = console_handler_names()
    app = CgseTuiApp(collector=EmptyCollector())
    async with app.run_test() as pilot:
        assert console_handler_names() == set()
        logging.getLogger("egse.tests").error("shown in the log pane")
        app.update_overview()
        await pilot.pause()
        log = app.overview.query_one("#log", RichLog)
        assert any("shown in the log pane" in line.text for line in log.lines)

        await pilot.press("l")
        assert not log.display
    assert console_handler_names() == before


async def test_quiet_hides_other_packages_also_in_worker_threads():
    handler = BufferedLogHandler()
    logger = logging.getLogger("egse.tests.quiet")
    logger.addHandler(handler)
    logging.getLogger("cgse_tui.tests").addHandler(handler)
    try:
        with quiet():
            logger.error("hidden")
            await asyncio.to_thread(logger.error, "hidden in a thread")
            logging.getLogger("cgse_tui.tests").warning("from the TUI itself")
        logger.error("shown again")
    finally:
        logger.removeHandler(handler)
        logging.getLogger("cgse_tui.tests").removeHandler(handler)

    texts = [message for _, message in handler.drain()]
    assert any("from the TUI itself" in text for text in texts)
    assert any("shown again" in text for text in texts)
    assert not any("hidden" in text for text in texts)


async def test_log_file_gets_all_messages_also_the_quiet_ones(tmp_path):
    log_file = tmp_path / "log" / "cgse_tui.log"
    app = CgseTuiApp(collector=EmptyCollector(), log_file=log_file)
    async with app.run_test() as pilot:
        with quiet():
            logging.getLogger("egse.registry.client").error("Request timed out after 2.00s")
        logging.getLogger("egse.tests").error("shown everywhere")
        app.update_overview()
        await pilot.pause()
        pane = [line.text for line in app.overview.query_one("#log", RichLog).lines]

    content = log_file.read_text()
    assert "Request timed out after 2.00s" in content  # in the file ...
    assert not any("Request timed out" in line for line in pane)  # ... but not in the log pane
    assert "shown everywhere" in content and any("shown everywhere" in line for line in pane)
    assert f"All log messages are also written to {log_file}" in content
    # removed on exit (pytest has a file handler of its own on the root logger)
    assert not any(getattr(h, "baseFilename", None) == str(log_file) for h in logging.getLogger().handlers)
