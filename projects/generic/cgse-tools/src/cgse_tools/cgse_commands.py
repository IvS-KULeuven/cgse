import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Annotated

import rich
import typer

from egse.system import format_datetime

app = typer.Typer()


@app.command()
def top():
    """
    A top-like interface for core services and device control servers.

    Not yet implemented.
    """
    print("This fancy top is not yet implemented.")


@app.command()
def init(project: str = ""):
    """Initialize your project."""
    from rich.prompt import Prompt, Confirm

    project = project.upper()
    site_id = None

    rich.print("[light_steel_blue]Please note default values are given between \[brackets].[/]")

    answer = Prompt.ask(f"What is the name of the project [{project}] ?")
    if answer:
        project = answer.upper()
    while not site_id:
        answer = Prompt.ask("What is the site identifier ?")
        if answer:
            site_id = answer.upper()
        else:
            answer = Confirm.ask("Abort?")
            if answer:
                return

    data_storage_location = f"~/data/{project}/{site_id}/"
    answer = Prompt.ask(f"Where can the project data be stored [{data_storage_location}] ?")
    if answer:
        data_storage_location = answer

    conf_data_location = f"~/data/{project}/{site_id}/conf/"
    answer = Prompt.ask(f"Where will the configuration data be located [{conf_data_location}] ?")
    if answer:
        conf_data_location = answer

    log_file_location = f"~/data/{project}/{site_id}/log/"
    answer = Prompt.ask(f"Where will the logging messages be stored [{log_file_location}] ?")
    if answer:
        log_file_location = answer

    local_settings_path = f"~/data/{project}/{site_id}/local_settings.yaml"
    answer = Prompt.ask(f"Where shall I create a local settings YAML file [{local_settings_path}] ?")
    if answer:
        local_settings_path = answer

    Path(data_storage_location).expanduser().mkdir(exist_ok=True, parents=True)
    (Path(data_storage_location).expanduser() / "daily").mkdir(exist_ok=True, parents=True)
    (Path(data_storage_location).expanduser() / "obs").mkdir(exist_ok=True, parents=True)
    Path(conf_data_location).expanduser().mkdir(exist_ok=True, parents=True)
    Path(log_file_location).expanduser().mkdir(exist_ok=True, parents=True)

    with open(Path(local_settings_path).expanduser(), 'w') as fd:
        fd.write(
            textwrap.dedent(
                f"""\
                SITE:
                    ID:  {site_id}
                """
            )
        )

    answer = Confirm.ask("Shall I add the environment to your ~/bash_profile ?")
    if answer:
        with open(Path("~/.bash_profile").expanduser(), 'a') as fd:
            fd.write(
                textwrap.dedent(
                    f"""
                    # Environment for project {project} added by `cgse init` at {format_datetime()}
                    export PROJECT={project}
                    export SITE_ID={site_id}
                    export {project}_DATA_STORAGE_LOCATION={data_storage_location}
                    export {project}_CONF_DATA_LOCATION={conf_data_location}
                    export {project}_LOG_FILE_LOCATION={log_file_location}
                    export {project}_LOCAL_SETTINGS={local_settings_path}
                    """
                )
            )


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
