import subprocess
import sys

import rich
import typer

from egse.system import all_logging_disabled
from egse.system import redirect_output_to_log

facility_hk = typer.Typer(name="facility_hk", help="Housekeeping from Facility Database")


@facility_hk.command(name="start")
def start_facility_hk():
    """Starts the extraction of HK from the facility DB into TA-EGSE CSV files."""

    rich.print("Starting the extraction of HK from the facility DB into TA-EGSE CSV files")

    out = redirect_output_to_log("facility_hk.start.log")

    cmd = [sys.executable, "-m", "egse.ariel.facility.hk", "start"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@facility_hk.command(name="stop")
def stop_facility_hk():
    """Stops the extraction of HK from the facility DB into TA-EGSE CSV files."""

    rich.print("Terminating the extraction of HK from the facility DB into TA-EGSE CSV files")

    out = redirect_output_to_log("facility_hk.stop.log")

    cmd = [sys.executable, "-m", "egse.ariel.facility.hk", "stop"]

    subprocess.Popen(cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, close_fds=True)


@facility_hk.command(name="status")
def status_facility_hk():
    """Prints status information the extraction of HK from the facility DB into TA-EGSE CSV files."""

    with all_logging_disabled():
        from egse.ariel.facility import hk

        hk.status()
