import subprocess
import sys

import rich

from egse.system import redirect_output_to_log


def start_rm_cs(log_level: str):
    rich.print("Starting the service registry manager core service...")

    out = redirect_output_to_log("rm_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.registry.server", "start", "--log-level", log_level],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_log_cs():
    rich.print("Starting the logging core service...")

    out = redirect_output_to_log("log_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.logger.log_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_sm_cs():
    rich.print("Starting the storage manager core service...")

    out = redirect_output_to_log("sm_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.storage.storage_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_cm_cs():
    rich.print("Starting the configuration manager core service...")

    out = redirect_output_to_log("cm_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.confman.confman_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_pm_cs():
    rich.print("Starting the process manager core service...")

    out = redirect_output_to_log("pm_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.procman.procman_cs", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def start_notifyhub():
    rich.print("Starting the notification hub core service...")

    out = redirect_output_to_log("nh_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.notifyhub.server", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
