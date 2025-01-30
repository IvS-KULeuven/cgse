import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import rich
import typer

app = typer.Typer()


@app.command()
def top():
    """
    A top-like interface for core services and device control servers.

    Not yet implemented.
    """
    print("This fancy top is not yet implemented.")


show = typer.Typer(help="Show information about settings, environment, setup, ...", no_args_is_help=True)


@show.command(name="settings")
def show_settings():
    proc = subprocess.Popen(
        [sys.executable, "-m", "egse.settings"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    rich.print(stdout.decode(), end='')
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


@show.command(name="env")
def show_env(
        mkdir: Annotated[bool, typer.Option(help="Create the missing folder")] = None,
        full: Annotated[bool, typer.Option(help="Provide additional info")] = None,
        doc: Annotated[bool, typer.Option(help="Provide documentation on environment variables")] = None,
):
    options = [opt for opt, flag in [("--mkdir", mkdir), ("--full", full), ("--doc", doc)] if flag]

    cmd = [sys.executable, "-m", "egse.env"]
    cmd += options if options else []

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    rich.print(stdout.decode(), end='')
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


check = typer.Typer(help="Check installation, settings, required files, etc.", no_args_is_help=True)


@check.command(name="setups")
def check_setups():
    """Perform a number of checks on the SETUP files."""

    # What can we check with respect to the setups?
    #
    # - CONF_DATA_LOCATION

    from egse.env import get_conf_data_location
    from egse.env import get_site_id
    from egse.config import find_files

    any_errors = 0

    conf_data_location = get_conf_data_location()
    site_id = get_site_id()

    # ---------- check if the <PROJECT>_CONF_DATA_LOCATION is set

    if not conf_data_location:
        any_errors += 1
        rich.print("[red]The location of the configuration data can not be determined, check your environment.[/]")

    if not Path(conf_data_location).exists():
        any_errors += 1
        rich.print(f"[red]The location of the configuration data doesn't exist: {conf_data_location!s}[/]")

    # ---------- check if there is at least one SETUP in the configuration data folder

    files = list(find_files("SETUP*.yaml", root=conf_data_location))

    if not files:
        any_errors += 1
        rich.print(f"[red]No SETUP files were found at {conf_data_location}[/]")

    regex = re.compile(f"SETUP_{site_id}_00000_.*.yaml")

    if not any(True for file in files if regex.search(str(file))):
        any_errors += 1
        rich.print(f"[red]The is no Zero SETUP for {site_id} in {conf_data_location}[/]")

    if not any_errors:
        rich.print("[green]everything seems to be ok.[/]")
