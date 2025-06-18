# Provide basic information about the egse logger that is of interest to the developer.
# Do not assume the log_cs is running, this function shall also provide the information
# even if the logger is not running.
#
# usage:
#   $ python -m egse.logger
import logging
import sys

import rich

from egse.env import get_log_file_location


def main():
    rich.print(f"Log file location: {get_log_file_location()}")


def test():
    # Any logger name that starts with "egse." will also be logged by the log_cs.

    logger = logging.getLogger("egse.0mq-log-test")
    logger.debug("Hello, ZeroMQ logging: This is a DEBUG message.")
    logger.info("Hello, ZeroMQ logging: This is an INFO message.")
    logger.warning("Hello, ZeroMQ logging: This is a WARNING message.")
    logger.error("Hello, ZeroMQ logging: This is an ERROR message.")
    logger.critical("Hello, ZeroMQ logging: This is a CRITICAL message.")
    try:
        raise ValueError("A fake ValueError, raised for testing.")
    except ValueError:
        logger.exception("Hello, ZeroMQ logging: This is an EXCEPTION message.")

    # The following log messages will not be logged by log_cs.

    logger = logging.getLogger("plain-log-test")

    logger.debug("Vanilla logging: This is a DEBUG message.")
    logger.info("Vanilla logging: This is an INFO message.")
    logger.warning("Vanilla logging: This is a WARNING message.")
    logger.error("Vanilla logging: This is an ERROR message.")
    logger.critical("Vanilla logging: This is a CRITICAL message.")
    try:
        raise ValueError("A fake ValueError, raised for testing.")
    except ValueError:
        logger.exception("Vanilla logging: This is an EXCEPTION message.")


if __name__ == "__main__":
    # test()

    sys.exit(main())
