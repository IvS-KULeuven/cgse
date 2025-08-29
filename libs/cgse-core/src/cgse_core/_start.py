import subprocess
import sys
from pathlib import Path

import rich


def start_rm_cs(log_level: str):
    rich.print("Starting the service registry manager core service...")

    out = open(Path("~/.rm_cs.start.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.registry.server", "start", "--log-level", log_level],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_log_cs():
    rich.print("Starting the logging core service...")

    out = open(Path("~/.log_cs.start.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.logger.log_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_sm_cs():
    rich.print("Starting the storage manager core service...")

    out = open(Path("~/.sm_cs.start.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.storage.storage_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_cm_cs():
    rich.print("Starting the configuration manager core service...")

    out = open(Path("~/.cm_cs.start.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.confman.confman_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_pm_cs():
    rich.print("Starting the process manager core service...")

    out = open(Path("~/.pm_cs.start.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.procman.procman_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_notifyhub():
    rich.print("Starting the notification hub core service...")

    out = open(Path("~/.notifyhub.start.out").expanduser(), "w")

    subprocess.Popen(
        [sys.executable, "-m", "egse.notifyhub.server", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
