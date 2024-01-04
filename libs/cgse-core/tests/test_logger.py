import logging
from pathlib import Path

from egse.env import get_log_file_location
from egse.system import read_last_lines

from egse.logger import egse_logger, create_new_zmq_logger
from egse.logger import get_log_file_name


def test_logging_messages_of_different_levels(setup_log_service, caplog):

    egse_logger.debug("This is a DEBUG message.")
    egse_logger.info("This is a INFO message.")
    egse_logger.warning("This is a WARNING message.")
    egse_logger.error("This is a ERROR message.")
    egse_logger.critical("This is a CRITICAL message.")

    log_location = get_log_file_location()

    lines = read_last_lines(filename=Path(log_location) / get_log_file_name(), num_lines=5)

    # The DEBUG message should be in the log file that was created by the log_cs

    assert any([True if "This is a DEBUG message." in x else False for x in lines])


def test_logging_exception(caplog):

    try:
        raise ValueError("incorrect value entered.")
    except ValueError as exc:
        egse_logger.exception("Reporting a ValueError")

    assert "incorrect value entered" in caplog.text
    assert "Reporting a ValueError" in caplog.text


def test_logging_error(caplog):

    try:
        raise ValueError("incorrect value entered.")
    except ValueError as exc:
        egse_logger.error("Reporting a ValueError")
        egse_logger.error("Reporting a ValueError with exc_info", exc_info=True)

    assert "incorrect value entered" in caplog.text
    assert "with exc_info" in caplog.text


def test_create_new_zmq_logger(caplog):

    camtest_logger = create_new_zmq_logger("camtest")

    camtest_logger.info("First message with ZeroMQ handler in camtest logger")

    assert "camtest:test_logger" in caplog.text
    assert "ZeroMQ" in caplog.text

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

    lines = caplog.text.split('\n')
    lines = [line for line in lines if line.strip()]  # filter out empty lines

    assert len(lines) == 1
