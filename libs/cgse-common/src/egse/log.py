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


def get_log_level_from_env(env_var: str = "LOG_LEVEL", default: int = logging.INFO):
    """Read the log level from an environment variable."""
    log_level_str = os.getenv(env_var, default)

    # Try to convert to integer first (for numeric levels)
    try:
        log_level = int(log_level_str)

        if 10 <= log_level <= 50:
            return log_level
        else:
            logging.warning(
                f"Log level {log_level} outside standard range (10-50). Using {logging.getLevelName(default)}."
            )
            return default

    except ValueError:
        log_level_str = log_level_str.upper()
        try:
            return getattr(logging, log_level_str)
        except AttributeError:
            logging.error(f"Invalid LOG_LEVEL '{log_level_str}'. Using {logging.getLevelName(default)}.")
            return default


egse_logger = logging.getLogger("egse")
egse_logger.level = get_log_level_from_env()  # We might want to choose another env e.g. CGSE_LOG_LEVEL

root_logger = logging.getLogger()
root_logger.level = get_log_level_from_env()

egse_handler = logging.StreamHandler()
if os.getenv("LOG_FORMAT", "").lower() == "full":
    egse_formatter = logging.Formatter(fmt=LOG_FORMAT_FULL, datefmt=LOG_DATE_FORMAT_FULL, style=LOG_FORMAT_STYLE)
else:
    egse_formatter = logging.Formatter(fmt=LOG_FORMAT_CLEAN, datefmt=LOG_DATE_FORMAT_CLEAN, style=LOG_FORMAT_STYLE)

egse_handler.setFormatter(egse_formatter)
egse_handler.addFilter(EGSEFilter())
egse_handler.addFilter(PackageFilter())

root_logger.addHandler(egse_handler)

for handler in root_logger.handlers:
    if handler != egse_handler:  # Don't filter our new handler
        handler.addFilter(NonEGSEFilter())
        handler.addFilter(PackageFilter())

logger = egse_logger

if __name__ == "__main__":
    root_logger = logging.getLogger()

    rich.print(
        textwrap.dedent(
            """
            Example logging statements
              - logging level set to INFO
              - fields are separated by a colon ':'
              - fields: date & time: process name : level : logger name : lineno : filename : message
            """
        )
    )

    if os.getenv("LOG_FORMAT_FULL") == "true":
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
