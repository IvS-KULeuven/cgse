import logging
import os
import signal
import sys

import typer

from egse.system import SignalCatcher

app = typer.Typer()
logger = logging.getLogger("egse.test.process")


@app.command()
def main(ignore_sigterm: bool = False):
    logging.basicConfig(level=logging.INFO)

    logger.info(f"{sys.version_info = }")
    logger.info(f"{ignore_sigterm = }")

    if ignore_sigterm:
        rc = _ignore_sigterm()
    else:
        rc = _handle_sigterm()

    raise typer.Exit(code=rc)


def _handle_sigterm():
    killer = SignalCatcher()

    while "waiting for a SIGTERM signal":
        if killer.term_signal_received:
            logger.info(f"{killer.signal_number = }")
            if killer.signal_number == signal.SIGTERM:
                logger.info("SIGTERM received, terminating...")
                return 42

    # The following code will never execute
    return 0


def _ignore_sigterm():
    killer = SignalCatcher()

    while "ignoring a SIGTERM signal":
        if killer.term_signal_received:
            logger.info(f"{killer.signal_number = }")
            if killer.signal_number == signal.SIGTERM:
                logger.info("SIGTERM received and ignored.")
                killer.clear(term=True)
                continue

    # The following code will never execute
    return 0


if __name__ == "__main__":
    print(f"{sys.argv=}")
    print(f"pid={os.getpid()}")

    try:
        from egse.logger import replace_zmq_handler
    except (ModuleNotFoundError, ImportError):

        def replace_zmq_handler(): ...

    try:
        app()
    except typer.Exit as e:
        raise SystemExit(e.exit_code)
