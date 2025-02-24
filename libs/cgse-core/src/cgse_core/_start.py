import subprocess
import sys
from pathlib import Path

import rich


def start_log_cs():
    rich.print("Starting the logging core service...")

    out = open(Path('~/.log_cs.start.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'egse.logger.log_cs', 'start'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


def start_sm_cs():
    rich.print("Starting the storage manager core service...")

    out = open(Path('~/.sm_cs.start.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'egse.storage.storage_cs', 'start'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )


def start_cm_cs():
    rich.print("Starting the configuration manager core service...")

    out = open(Path('~/.cm_cs.start.out').expanduser(), 'w')

    subprocess.Popen(
        [sys.executable, '-m', 'egse.confman.confman_cs', 'start'],
        stdout=out, stderr=out, stdin=subprocess.DEVNULL,
        close_fds=True
    )
