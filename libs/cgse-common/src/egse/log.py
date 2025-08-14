__all__ = [
    "LOG_FORMAT_FULL",
    "logger",
    "set_logger_levels",
]

import logging
import textwrap

import rich

logger = logging.getLogger("egse")

LOG_FORMAT_FULL = "%(asctime)23s:%(processName)20s:%(levelname)8s:%(name)-25s:%(lineno)5d:%(filename)-20s:%(message)s"


def set_logger_levels(logger_levels: list[tuple[str, str]] = None) -> None:
    """
    Set the logging level for the given loggers.

    Args:
        logger_levels: a list of tuples of logger names and logger levels/
    """
    logger_levels = logger_levels or []

    for name, level in logger_levels:
        logging.getLogger(name).setLevel(level)


if __name__ == '__main__':

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT_FULL,
    )

    rich.print(
        textwrap.dedent(
            """
            Example logging statements
              - logging level set to INFO
              - fields are separated by a colon ':'
              - fields: date : time: process name : level : logger name : lineno : filename : message
            """
        )
    )

    for name, level in logging.getLevelNamesMapping().items():
        logger.log(level, f"{name} logging message")
