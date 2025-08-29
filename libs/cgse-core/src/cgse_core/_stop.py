import logging
import subprocess
import sys
from pathlib import Path

import rich

from egse.log import logger
from egse.process import is_process_running
from egse.system import Timer
from egse.system import waiting_for


def stop_rm_cs():
    rich.print("Terminating the service registry manager core service...")

    out = open(Path("~/.rm_cs.stop.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.registry.server", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    try:
        with Timer("rm_cs stop timer", log_level=logging.DEBUG):
            waiting_for(lambda: not is_process_running(["egse.registry.server", "start"]), timeout=5.0)
    except TimeoutError:
        logger.warning("rm_cs should not be running anymore...")


def stop_log_cs():
    rich.print("Terminating the logging core service...")

    out = open(Path("~/.log_cs.stop.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.logger.log_cs", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def stop_sm_cs():
    rich.print("Terminating the storage manager core service...")

    out = open(Path("~/.sm_cs.stop.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.storage.storage_cs", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    try:
        with Timer("sm_cs stop timer", log_level=logging.DEBUG):
            waiting_for(lambda: not is_process_running(["storage_cs", "start"]), timeout=5.0)
    except TimeoutError:
        logger.warning("sm_cs should not be running anymore...")


def stop_cm_cs():
    rich.print("Terminating the configuration manager core service...")

    out = open(Path("~/.cm_cs.stop.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.confman.confman_cs", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    try:
        with Timer("cm_cs stop timer", log_level=logging.DEBUG):
            waiting_for(lambda: not is_process_running(["confman_cs", "start"]), timeout=5.0)
    except TimeoutError:
        logger.warning("cm_cs should not be running anymore...")


def stop_pm_cs():
    rich.print("Terminating the process manager core service...")

    out = open(Path("~/.pm_cs.stop.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.procman.procman_cs", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    try:
        with Timer("pm_cs stop timer", log_level=logging.DEBUG):
            waiting_for(lambda: not is_process_running(["procman_cs", "start"]), timeout=5.0)
    except TimeoutError:
        logger.warning("pm_cs should not be running anymore...")


def stop_notifyhub():
    rich.print("Terminating the notification hub core service...")

    out = open(Path("~/.notifyhub.stop.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.notifyhub.server", "stop"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )

    try:
        with Timer("notifyhub stop timer", log_level=logging.DEBUG):
            waiting_for(lambda: not is_process_running(["egse.notifyhub.server", "start"]), timeout=5.0)
    except TimeoutError:
        logger.warning("notifyhub should not be running anymore...")
