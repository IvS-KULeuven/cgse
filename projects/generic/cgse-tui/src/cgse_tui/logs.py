"""Shows log messages in the TUI instead of on the terminal.

The `egse.log` module attaches console handlers to the `egse` and root loggers. They write directly to the terminal,
over the Textual screen. While the TUI runs, these handlers are replaced by a handler that keeps the formatted
messages in a buffer, which the app shows in its log pane.
"""

from __future__ import annotations

import collections
import contextlib
import contextvars
import logging
import logging.handlers
import sys
import threading
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"
LOG_FILE_FORMAT = "%(asctime)s %(levelname)-8s %(threadName)s %(name)s: %(message)s"
LOG_FILE_NAME = "cgse_tui.log"

_quiet = contextvars.ContextVar("cgse_tui_quiet", default=False)


@contextlib.contextmanager
def quiet() -> Iterator[None]:
    """Messages that other packages log in this context are not shown, e.g. the timeouts of the client libraries.

    The TUI uses this for its own status requests: the result of a request is shown as the state of the service, and
    the collector logs the state changes. The context is also used in threads started with `asyncio.to_thread()`.
    """
    token = _quiet.set(True)
    try:
        yield
    finally:
        _quiet.reset(token)


class BufferedLogHandler(logging.Handler):
    """Keeps the last formatted log messages, also when they are logged from another thread."""

    def __init__(self, max_messages: int = 1000):
        super().__init__()
        self.setFormatter(logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        self._messages: collections.deque[tuple[int, str]] = collections.deque(maxlen=max_messages)
        self._messages_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        if _quiet.get() and not record.name.startswith("cgse_tui"):
            return
        try:
            message = self.format(record)
        except Exception:
            self.handleError(record)
            return
        with self._messages_lock:
            self._messages.append((record.levelno, message))

    def drain(self) -> list[tuple[int, str]]:
        """Returns the messages as (level, text) and removes them from the buffer."""
        with self._messages_lock:
            messages = list(self._messages)
            self._messages.clear()
        return messages


def _is_console_handler(handler: logging.Handler) -> bool:
    return type(handler) is logging.StreamHandler and handler.stream in (sys.stderr, sys.stdout, sys.__stderr__)


def create_log_file_handler(path: Path, max_bytes: int = 1_000_000, backup_count: int = 3) -> logging.Handler:
    """Returns a rotating file handler for all log messages, also those that `quiet()` keeps out of the log pane."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count)
    handler.setFormatter(logging.Formatter(fmt=LOG_FILE_FORMAT))
    return handler


def capture_logging(*handlers: logging.Handler) -> Callable[[], None]:
    """Replaces the console handlers of the root and `egse` loggers by the given handlers.

    The handlers are added to the root logger only, messages of the `egse` logger reach them through propagation.

    Returns:
        A function that removes the handlers and puts the console handlers back.
    """
    removed: list[tuple[logging.Logger, logging.Handler]] = []
    for logger in (logging.getLogger(), logging.getLogger("egse")):
        for console_handler in [h for h in logger.handlers if _is_console_handler(h)]:
            logger.removeHandler(console_handler)
            removed.append((logger, console_handler))

    root = logging.getLogger()
    for handler in handlers:
        root.addHandler(handler)

    def restore() -> None:
        for handler in handlers:
            root.removeHandler(handler)
            if not isinstance(handler, BufferedLogHandler):
                handler.close()
        for logger, console_handler in removed:
            logger.addHandler(console_handler)

    return restore
