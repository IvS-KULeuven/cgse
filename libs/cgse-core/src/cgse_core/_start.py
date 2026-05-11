import subprocess
import sys

import rich
from egse.system import redirect_output_to_log


def start_rm_cs(log_level: str, enforce_unique_service_types: bool | None = None):
    rich.print("Starting the service registry manager core service...")

    out = redirect_output_to_log("rm_cs.start.log")

    command = [sys.executable, "-m", "egse.registry.server", "start", "--log-level", log_level]

    if enforce_unique_service_types is True:
        command.append("--enforce-unique-service-types")
    elif enforce_unique_service_types is False:
        command.append("--no-enforce-unique-service-types")

    subprocess.Popen(
        command,
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


def start_metricshub():
    rich.print("Starting the metrics hub core service...")

    out = redirect_output_to_log("mh_cs.start.log")

    subprocess.Popen(
        [sys.executable, "-m", "egse.metricshub.server", "start"],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
