import logging
import time
from pathlib import Path

import pytest

from egse.env import get_log_file_location
from egse.logger import create_new_zmq_logger
from egse.logger import egse_logger
from egse.logger import get_log_file_name
from egse.logger import send_request
from egse.process import is_process_running
from egse.system import read_last_lines


@pytest.mark.skipif(
    bool(is_process_running(items=["log_cs"])),
    reason="This test starts its own logging server, log_cs can not be running.",
)
def test_logging_messages_of_different_levels(setup_log_service):
    # The egse logger doesn't propagate messages to parent loggers, so we
    # have to add the caplog handler in order to capture logging messages for this test.
    # egse_logger.addHandler(caplog.handler)
    # egse_logger.setLevel(logging.DEBUG)

    egse_logger.debug("This is a DEBUG message.")
    egse_logger.info("This is a INFO message.")
    egse_logger.warning("This is a WARNING message.")
    egse_logger.error("This is a ERROR message.")
    egse_logger.critical("This is a CRITICAL message.")

    time.sleep(1.0)  # give some time for the log messages to be written to file

    status = send_request("status")

    log_location = get_log_file_location() + "/" + get_log_file_name()
    log_location = status.get("file_logger_location", log_location)

    lines = read_last_lines(filename=Path(log_location), num_lines=10)

    # FIXME:
    #    In my setup, lines is [], so nothing has been read from the log file. When I inspect
    #    the log file after the test, the expected line is there!
    #    -> check if the log_cs service is running and writing to the expected location.

    print(f"{log_location = }, {get_log_file_name()=}, {len(lines)=}")
    for line in lines:
        print(line)

    # The DEBUG message should be in the log file that was created by the log_cs, because
    # the log level is set to DEBUG for the log-file.

    assert any([True if "This is a DEBUG message." in x else False for x in lines])


def test_logging_exception(caplog):
    try:
        raise ValueError("incorrect value entered.")
    except ValueError:
        egse_logger.exception("Reporting a ValueError")

    assert "incorrect value entered" in caplog.text
    assert "Reporting a ValueError" in caplog.text


def test_logging_error(caplog):
    try:
        raise ValueError("incorrect value entered.")
    except ValueError:
        egse_logger.error("Reporting a ValueError")
        egse_logger.error("Reporting a ValueError with exc_info", exc_info=True)

    assert "incorrect value entered" in caplog.text
    assert "with exc_info" in caplog.text


def test_create_new_zmq_logger(caplog):
    print()

    camtest_logger = create_new_zmq_logger("camtest")

    camtest_logger.info("First message with ZeroMQ handler in camtest logger")

    assert "camtest:test_logger" in caplog.text
    assert "ZeroMQ" in caplog.text

    print(f"{caplog.text = }")

    caplog.clear()

    logger = logging.getLogger("camtest.sub_level")

    logger.info("Message from sub_level logger should be categorised under camtest_logger")

    assert "camtest.sub_level:test_logger" in caplog.text
    assert "categorised" in caplog.text

    # See what happens if we call the function twice with the same logger

    caplog.clear()

    camtest_logger = create_new_zmq_logger("camtest")

    # If the following message appears twice in the general.log logfile then a second handler
    # was created by the create_new_zmq_logger function.

    camtest_logger.info("Created the zmq handler twice?")

    lines = caplog.text.split("\n")
    lines = [line for line in lines if line.strip()]  # filter out empty lines

    assert len(lines) == 1
