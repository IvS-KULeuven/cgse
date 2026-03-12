import subprocess
import sys
import textwrap
import time

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

    # We run a Timer here to log how long it takes to start the dummy device
    try:
        with Timer("dummy dev start"):
            waiting_for(is_dummy_dev_active, timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev should be active by now...")

    dummy_dev_stop = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["stop-dev"])
    dummy_dev_stop.execute()

    # We run a Timer here to log how long it takes to stop the dummy device
    try:
        with Timer("dummy dev stop"):
            waiting_for(lambda: not is_process_running(["egse.dummy", "start-dev"]), timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev should not be running anymore...")


def test_dummy_dev_2():
    print()

    rc = is_process_running(["egse.dummy", "start-dev"])
    logger.info(f"dummy dev is{' ' if rc else ' not '}running...")

    dummy_dev_start_1 = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["start-dev"])
    rc = dummy_dev_start_1.execute()
    logger.info(f"The dummy_dev_start_1 subprocess is{' ' if rc else ' not '}running...")

    logger.info(
        f"Status dummy dev 1: "
        f"{dummy_dev_start_1.returncode()=}, "
        f"{dummy_dev_start_1.exists()=}, "
        f"{dummy_dev_start_1.is_running()=}, "
        f"{dummy_dev_start_1.pid=}"
    )

    # We run a Timer here to log how long it takes to start the dummy device
    try:
        with Timer("dummy dev 1 start"):
            waiting_for(is_dummy_dev_active, timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev 1 should be active by now...")

    # Since the first dummy device is already running, this second start should fail

    dummy_dev_start_2 = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["start-dev"])
    rc = dummy_dev_start_2.execute()
    logger.info(f"The dummy_dev_start_2 subprocess {'started' if rc else 'not started'}.")

    # I cannot test here with is_dummy_dev_active() because the first process is already running
    time.sleep(2.0)  # About the time needed to start the process

    logger.info(
        f"Status dummy dev 2: "
        f"{dummy_dev_start_2.returncode()=}, "
        f"{dummy_dev_start_2.exists()=}, "
        f"{dummy_dev_start_2.is_running()=}, "
        f"{dummy_dev_start_2.pid=}"
    )

    # I cannot test here with is_process_running() because the first process is already running
    if dummy_dev_start_2.is_running():
        logger.info("dummy dev 2 is running...but shouldn't be running!")

    dummy_dev_stop = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["stop-dev"])
    dummy_dev_stop.execute()

    # We run a Timer here to log how long it takes to stop the dummy device
    try:
        with Timer("dummy dev stop"):
            waiting_for(lambda: not is_process_running(["egse.dummy", "start-dev"]), timeout=5.0)
    except TimeoutError:
        pytest.xfail("dummy dev should not be running anymore...")


def test_dummy_dev_3():
    rc = is_process_running(["egse.dummy", "start-dev"])
    logger.info(f"dummy dev is{' ' if rc else ' not '}running...")

    dummy_dev = subprocess.Popen(
        [sys.executable, "-m", "egse.dummy", "start-dev"],
        stdout=None,
        stderr=None,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    logger.info(f"Status dummy dev 3: {dummy_dev.returncode=}, {dummy_dev.pid=}, {dummy_dev.args=}")

    time.sleep(1.0)

    dummy_dev.terminate()

    with Timer("dummy dev wait"):
        rc = dummy_dev.wait()

    rc = is_process_running(["egse.dummy", "start-dev"])
    logger.info(f"dummy dev is{' ' if rc else ' not '}running...")


if __name__ == "__main__":
    # You can run the individual tests with `py -m tests/test_dummy`
    # Add those tests that are missing when you need them.

    print(
        textwrap.dedent(
            """\
            1. start dummy device test 1 - start process, wait until active, stop process
            2. start dummy device test 2 - start process, try to start another, stop process
            3. start dummy device test 3 - start process with Popen, terminate it
            0. Exit
            """
        )
    )
    x = input("Select a number for the test you want to execute: ")

    try:
        match int(x.strip()):
            case 1:
                test_dummy_dev_1()
            case 2:
                test_dummy_dev_2()
            case 3:
                test_dummy_dev_3()
            case _:
                print("Exiting...")

    except Exception as exc:
        logger.error(f"Caught {type(exc).__name__}: {exc}")
