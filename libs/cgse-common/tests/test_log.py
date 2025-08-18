import logging

from egse.log import logger


def test_log_levels(caplog):
    orig_level = logger.level

    # The egse logger doesn't propagate messages to parent loggers, so we
    # have to add the caplog handler in order to capture logging messages for this test.
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.INFO)

    level = logger.getEffectiveLevel()
    assert level == logging.INFO

    caplog.clear()

    try:
        for name, level_ in (
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
        ):
            logger.log(level_, f"{name} logging message")

        if level <= logging.DEBUG:
            assert "DEBUG logging message" in caplog.text
        else:
            assert "DEBUG logging message" not in caplog.text

        if level <= logging.INFO:
            assert "INFO logging message" in caplog.text
        else:
            assert "INFO logging message" not in caplog.text

        if level <= logging.WARNING:
            assert "WARNING logging message" in caplog.text
        else:
            assert "WARNING logging message" not in caplog.text

    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(orig_level)

    caplog.clear()
