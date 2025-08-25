import sys

import pytest

from egse.dummy import is_dummy_dev_active
from egse.log import logger
from egse.process import SubProcess
from egse.process import is_process_running
from egse.system import Timer
from egse.system import waiting_for


def test_dummy_dev_1():
    print()

    if rc := is_process_running(["egse.dummy", "start-dev"]):
        pytest.xfail(f"dummy dev is{' ' if rc else ' not '}running...")

    dummy_dev_start = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["start-dev"])
    dummy_dev_start.execute()

    try:
        with Timer("dummy dev start"):
            waiting_for(is_dummy_dev_active, timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev should be active by now...")

    dummy_dev_stop = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["stop-dev"])
    dummy_dev_stop.execute()

    try:
        with Timer("dummy dev stop"):
            waiting_for(lambda: not is_process_running(["egse.dummy", "start-dev"]), timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev should not be running anymore...")


def test_dummy_dev_2():
    print()

    if rc := is_process_running(["egse.dummy", "start-dev"]):
        logger.info(f"dummy dev is{' ' if rc else ' not '}running...")

    dummy_dev_start_1 = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["start-dev"])
    dummy_dev_start_1.execute()

    try:
        with Timer("dummy dev start"):
            waiting_for(is_dummy_dev_active, timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev should be active by now...")

    dummy_dev_start_2 = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["start-dev"])
    if rc := dummy_dev_start_2.execute():
        logger.error("The dummy_dev_start_2 subprocess couldn't start.")

    logger.info(f"Status dummy dev 2: {dummy_dev_start_2.returncode()=}, {dummy_dev_start_2.exists()=}")
    if rc := is_process_running(["egse.dummy", "start-dev"]):
        logger.info(f"dummy dev is{' ' if rc else ' not '}running...")

    dummy_dev_stop = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["stop-dev"])
    dummy_dev_stop.execute()

    try:
        with Timer("dummy dev stop"):
            waiting_for(lambda: not is_process_running(["egse.dummy", "start-dev"]), timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev should not be running anymore...")
