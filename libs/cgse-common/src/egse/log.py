import logging

logger = logging.getLogger("egse")


def set_logger_levels(logger_levels: list[tuple[str, str]] = None) -> None:
    """
    Set the logging level for the given loggers.

    Args:
        logger_levels: a list of tuples of logger names and logger levels/
    """
    logger_levels = logger_levels or []

    for name, level in logger_levels:
        logging.getLogger(name).setLevel(level)
