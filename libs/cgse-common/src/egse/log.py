"""
Configure local logging for the CGSE.

I use 'local logging' here because the CGSE also has a Logger server which stores
all CGSE log messages in a rotated file. That server is part of the `cgse-core` package.

Environment variables that affect logging:

  - LOG_FORMAT: full | FULL
  - LOG_LEVEL: an integer [10, 50] or a level name DEBUG, INFO, WARNING, CRITICAL, ERROR

"""

__all__ = [
    "LOG_FORMAT_FULL",
    "LOG_FORMAT_CLEAN",
    "LOG_FORMAT_STYLE",
    "LOG_DATE_FORMAT_FULL",
    "LOG_DATE_FORMAT_CLEAN",
    "logger",
    "logging",  # export to guarantee that this module is imported and initialized before users use logging
    "root_logger",
    "egse_logger",
    "get_log_level_from_env",
    "PackageFilter",
]

import logging
import os
import textwrap
from pathlib import Path

import rich

# The format for the log messages.
# The log record attributes are listed: https://docs.python.org/3.12/library/logging.html#logrecord-attributes

LOG_FORMAT_STYLE = "{"
LOG_FORMAT_FULL = (
    "{asctime:19s}.{msecs:03.0f} : {processName:20s} : {levelname:8s} : {name:^25s} : {lineno:6d} : {filename:20s} : {"
    "message}"
)
LOG_FORMAT_CLEAN = (
    "{asctime} [{levelname:>8s}] {message} ({processName}[{process}]:{package_name}:{filename}:{lineno:d})"
)

LOG_DATE_FORMAT_FULL = "%Y-%m-%d %H:%M:%S"
LOG_DATE_FORMAT_CLEAN = "%Y-%m-%d %H:%M:%S"


class PackageFilter(logging.Filter):
    """Adds 'package_name' to the log record.

    When this filter is added to a handler of a logger, the formatter of that
    logger can use the 'package_name' attribute.

    When the package name can not be determined, is will contain 'n/a'.

    NOTE: this filer assumes the root package is 'egse'.
    """

    def filter(self, record):
        if hasattr(record, "pathname"):
            parts = Path(record.pathname).parent.parts
            try:
                egse_index = parts.index("egse")
                package_name = ".".join(parts[egse_index:])
            except ValueError:
                package_name = "n/a"

            record.package_name = package_name
        else:
            record.package_name = "n/a"

        return True


class EGSEFilter(logging.Filter):
    def filter(self, record):
        return record.name.startswith("egse")


class NonEGSEFilter(logging.Filter):
    def filter(self, record):
        return not record.name.startswith("egse")


def get_log_level_from_env(env_var: str = "LOG_LEVEL", default: str = "INFO") -> int:
    """Read the log level from an environment variable."""
    log_level_str = os.getenv(env_var, default)

    # Try to convert to integer first (for numeric levels)
    try:
        log_level = int(log_level_str)

        if 10 <= log_level <= 50:
            return log_level
        else:
            logging.warning(f"Log level {log_level} outside standard range (10-50). Using {default.upper()}.")
            return logging._nameToLevel[default.upper()]

    except ValueError:
        log_level_str = log_level_str.upper()
        try:
            return getattr(logging, log_level_str)
        except AttributeError:
            logging.error(f"Invalid LOG_LEVEL '{log_level_str}'. Using {default.upper()}.")
            return logging._nameToLevel[default.upper()]


egse_logger = logging.getLogger("egse")
egse_logger.level = get_log_level_from_env()  # We might want to choose another env e.g. CGSE_LOG_LEVEL

# Guard against duplicate handlers: if this module is executed as `__main__`
# (e.g. `python -m egse.log`) and also imported elsewhere by its dotted name
# in the same run, Python loads and executes the file twice under two
# different module identities, but both attach handlers to the same
# singleton loggers below. Naming the handlers and checking for that name
# keeps handler setup idempotent no matter how many times this file runs.

EGSE_HANDLER_NAME = "egse_console_handler"
ROOT_HANDLER_NAME = "root_console_handler"

if not any(h.name == EGSE_HANDLER_NAME for h in egse_logger.handlers):
    egse_handler = logging.StreamHandler()
    egse_handler.name = EGSE_HANDLER_NAME
    if os.getenv("LOG_FORMAT", "").lower() == "full":
        egse_formatter = logging.Formatter(fmt=LOG_FORMAT_FULL, datefmt=LOG_DATE_FORMAT_FULL, style=LOG_FORMAT_STYLE)
    else:
        egse_formatter = logging.Formatter(fmt=LOG_FORMAT_CLEAN, datefmt=LOG_DATE_FORMAT_CLEAN, style=LOG_FORMAT_STYLE)

    egse_handler.setFormatter(egse_formatter)
    egse_handler.addFilter(EGSEFilter())
    egse_handler.addFilter(PackageFilter())

    egse_logger.addHandler(egse_handler)

root_logger = logging.getLogger()
root_logger.level = get_log_level_from_env()

if not any(h.name == ROOT_HANDLER_NAME for h in root_logger.handlers):
    root_handler = logging.StreamHandler()
    root_handler.name = ROOT_HANDLER_NAME
    if os.getenv("LOG_FORMAT", "").lower() == "full":
        root_formatter = logging.Formatter(fmt=LOG_FORMAT_FULL, datefmt=LOG_DATE_FORMAT_FULL, style=LOG_FORMAT_STYLE)
    else:
        root_formatter = logging.Formatter(fmt=LOG_FORMAT_CLEAN, datefmt=LOG_DATE_FORMAT_CLEAN, style=LOG_FORMAT_STYLE)
    root_handler.setFormatter(root_formatter)
    root_handler.addFilter(PackageFilter())
    root_handler.addFilter(NonEGSEFilter())

    root_logger.addHandler(root_handler)

# for handler in root_logger.handlers:
#     rich.print(f"Adding filters to handler {handler} of root logger {root_logger}")
#     if handler != egse_handler:  # Don't filter our new handler
#         handler.addFilter(NonEGSEFilter())
#         handler.addFilter(PackageFilter())

# Optional: integrate with Textual logging if available
#
# try:
#     from textual.logging import TextualHandler

#     root_logger.addHandler(TextualHandler())
# except ImportError:
#     pass


logger = egse_logger

if __name__ == "__main__":
    from egse.env import str_env

    root_logger = logging.getLogger()

    print(
        textwrap.dedent(
            """
            Environment variables:
              - LOG_LEVEL=debug|info|warning|critical
              - LOG_FORMAT=full|clean

            Example logging statements
              - logging level set to INFO
              - logging format set to full
              - fields are separated by a colon ':'
              - fields: date & time: process name : level : logger name : lineno : filename : message
            """
        )
    )

    if str_env("LOG_FORMAT", "clean").strip().lower() == "full":
        rich.print(
            f"[b]{'Date & Time':^23s} : {'Process Name':20s} : {'Level':8s} : {'Logger Name':^25s} : {' Line '} : "
            f"{'Filename':20s} : {'Message'}[/]"
        )
    else:
        rich.print(f"[b]{'Date & Time':^19s} [ Level  ] Message (filename:lineno)[/]")

    rich.print("-" * 150)
    for name, level in logging.getLevelNamesMapping().items():
        logger.log(level, f"{name} logging message")

    root_logger.info("This should come out of the root logger, not the egse logger.")
