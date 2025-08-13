import contextlib
import logging
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Annotated

import rich
import typer
from rich.console import Console
from rich.table import Table

from cgse_common import AppState
from egse.config import find_files
from egse.env import get_conf_data_location
from egse.env import get_site_id
from egse.plugin import entry_points
from egse.process import ProcessInfo
from egse.setup import Setup
from egse.system import format_datetime

app = typer.Typer()


@app.command()
def top(ctx: typer.Context):
    """
    A top-like interface for core services and device control servers.

    Not yet implemented.
    """
    state: AppState = ctx.obj

    print(f"The `verbose` flag is {state.verbose}")
    print("This fancy top is not yet implemented.")


@app.command()
def init(project: str = ""):
    """Initialize your project."""
    from rich.prompt import Prompt, Confirm

    project = project.upper()
    site_id = None

    rich.print(r"[light_steel_blue]Please note default values are given between \[brackets].[/]")

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

    if not Path(local_settings_path).expanduser().exists():
        with open(Path(local_settings_path).expanduser(), "w") as fd:
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
        with open(Path("~/.bash_profile").expanduser(), "a") as fd:
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
    else:
        rich.print(
            textwrap.dedent(
                f"""
                # -> Add the following lines to your bash profile or equivalent
                
                export PROJECT={project}
                export SITE_ID={site_id}
                export {project}_DATA_STORAGE_LOCATION={data_storage_location}
                export {project}_CONF_DATA_LOCATION={conf_data_location}
                export {project}_LOG_FILE_LOCATION={log_file_location}
                export {project}_LOCAL_SETTINGS={local_settings_path}
            """
            )
        )


show = typer.Typer(help="Show information about settings, environment, setup, ...")


@show.command(name="settings")
def show_settings():
    """Show the settings that are defined by the installed packages."""
    proc = subprocess.Popen([sys.executable, "-m", "egse.settings"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    rich.print(stdout.decode(), end="")
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


@show.command(name="env")
def show_env(
    mkdir: Annotated[bool, typer.Option(help="Create the missing folder")] = None,
    full: Annotated[bool, typer.Option(help="Provide additional info")] = None,
    doc: Annotated[bool, typer.Option(help="Provide documentation on environment variables")] = None,
):
    """Show the environment variables that are defined for the project."""
    options = [opt for opt, flag in [("--mkdir", mkdir), ("--full", full), ("--doc", doc)] if flag]

    cmd = [sys.executable, "-m", "egse.env"]
    cmd += options if options else []

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    rich.print(stdout.decode(), end="")
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


@show.command(name="procs")
def show_processes():
    """Show the processes that are running for the installed packages."""
    processes: list[ProcessInfo] = []

    for ep in entry_points("cgse.explore"):
        # print(f"{ep.name = }, {ep.module = }, {ep.load() = }, {ep.extras = }")
        explore = ep.load()
        with contextlib.suppress(AttributeError):
            show_procs = getattr(explore, "show_processes")
            processes.extend(show_procs())

    console = Console()
    console.print(create_rich_table(processes))


def create_rich_table(processes: list[ProcessInfo]):
    """Create a rich table with the processes from all registered packages."""

    table = Table(title="Process Information")

    table.add_column("PID", style="cyan", no_wrap=True)
    table.add_column("Name", style="magenta")
    table.add_column("User", style="green")
    table.add_column("CPU%", justify="right", style="yellow")
    # table.add_column("Memory%", justify="right", style="blue")
    table.add_column("Memory MB", justify="right", style="blue")
    table.add_column("Status", style="red")
    table.add_column("Command", style="white")

    # Sort by CPU usage
    processes.sort(key=lambda x: x.cpu_percent, reverse=True)

    for proc in processes:
        proc = proc.as_dict()
        cmd = re.sub(r"^.*/?python(?:\d+(?:\.\d+)?)?\s+(?:-m)?\s*", "python -m ", proc["command"])
        table.add_row(
            str(proc["pid"]),
            proc["name"],
            proc.get("username", "N/A"),
            f"{proc.get('cpu_percent', 0):.1f}",
            # f"{proc.get('memory_percent', 0):.1f}",
            f"{proc.get('memory_mb', 0):.1f}",
            proc.get("status", "unknown"),
            cmd[:100] + "..." if len(cmd) > 100 else cmd,
        )

    return table


@show.command(name="setup")
def show_setup(
    use_cm: Annotated[bool, typer.Option(help="Get the current setup from the configuration manager")] = True,
    list_all: Annotated[bool, typer.Option(help="Print a list of all available setups")] = False,
    setup_id: Annotated[int, typer.Option(help="Show the setup with this id")] = -1,
):
    if use_cm:
        try:
            from egse.confman import ConfigurationManagerProxy
        except ImportError:
            rich.print("[dark_orange3]WARNING: package 'cgse-core' is not installed, service not available.[/]")
            return

        with ConfigurationManagerProxy() as cm:
            if list_all:
                rich.print(cm.list_setups())
            else:
                rich.print(cm.get_setup())
        return

    location = get_conf_data_location()
    site_id = get_site_id()

    if list_all:
        files = find_files(f"SETUP_{site_id}_*_*.yaml", root=location)
        files = list(files)
        if files:
            location = files[0].parent.resolve()
        rich.print(sorted([f.name for f in files]))
        rich.print(f"Loaded from [purple]{location}.")
    else:
        if setup_id == -1:
            setup_files = find_files(f"SETUP_{site_id}_*_*.yaml", root=location)
        else:
            setup_files = find_files(f"SETUP_{site_id}_{setup_id:05d}_*.yaml", root=location)
        setup_files = list(setup_files)
        if len(setup_files) > 0:
            setup_file = sorted(setup_files)[-1]
            setup = Setup.from_yaml_file(setup_file)
            rich.print(setup)
        else:
            rich.print("[red]No setup files were found.[/]")


check = typer.Typer(help="Check installation, settings, required files, etc.")


@check.command(name="setups")
def check_setups(verbose: bool = False):
    """Perform a number of checks on the SETUP files."""

    logging.basicConfig(
        level=logging.CRITICAL,
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-20s %(lineno)5d:%(module)-20s %(message)s",
    )

    # What can we check with respect to the setups?
    #
    # - CONF_DATA_LOCATION

    from egse.env import get_conf_data_location
    from egse.env import get_site_id
    from egse.config import find_files

    any_errors = 0
    error_messages = []

    try:
        conf_data_location = get_conf_data_location()
    except ValueError:
        conf_data_location = None

    site_id = get_site_id()

    # ---------- check if the Site_ID is set

    verbose and rich.print("Checking site id ...")

    if not site_id:
        any_errors += 1
        error_messages.append(
            "[red]The environment variable SITE_ID is not set. "
            "SITE_ID is required to define the project settings and environment variables.[/]"
        )

    # ---------- check if the <PROJECT>_CONF_DATA_LOCATION is set

    verbose and rich.print("Checking configuration data location ...")

    if not conf_data_location:
        any_errors += 1
        error_messages.append(
            "[red]The location of the configuration data can not be determined, check your environment using `cgse "
            "show env`.[/]"
        )
    elif not Path(conf_data_location).exists():
        any_errors += 1
        error_messages.append(f"[red]The location of the configuration data doesn't exist: {conf_data_location!s}[/]")

    if any_errors:
        print_error_messages(error_messages)
        return

    # ---------- check if there is at least one SETUP in the configuration data folder

    verbose and rich.print("Checking available SETUP files ...")

    files = list(find_files("SETUP*.yaml", root=conf_data_location))

    if not files:
        any_errors += 1
        error_messages.append(f"[red]No SETUP files were found at {conf_data_location}[/]")
    else:
        verbose and rich.print(f":arrow_forward: Found {len(files)} Setup files.")

    regex = re.compile(f"SETUP_{site_id}_00000_.*.yaml")

    if not any(True for file in files if regex.search(str(file))):
        any_errors += 1
        error_messages.append(f"[red]There is no 'Zero' SETUP for {site_id} in {conf_data_location}[/]")
    else:
        verbose and rich.print(f":arrow_forward: Found the 'Zero' Setup file: SETUP_{site_id}_00000_*.yaml")

    if any_errors:
        print_error_messages(error_messages)
        return

    # ---------- check for each SETUP file if the site_id matches the SITE_ID

    verbose and rich.print("Checking site_id in setup files ...")

    for file in files:
        setup = Setup.from_yaml_file(file)
        this_site_id = setup.get("site_id")
        if this_site_id is None:
            any_errors += 1
            error_messages.append(f"There is no 'site_id' defined in '{file!s}'")
        elif this_site_id != site_id:
            any_errors = 1
            error_messages.append(
                f"[red]The site_id ('{this_site_id}') in '{file!s}' doesn't match the environment "
                f"variable SITE_ID={site_id}[/]"
            )

    if any_errors:
        print_error_messages(error_messages)
    else:
        rich.print("[green]everything seems to be ok.[/]")


def print_error_messages(messages: list[str]):
    from rich.panel import Panel

    content = "\n"

    for msg in messages:
        content += f":arrow_forward: {msg}\n"
    content += "\n[orange1]Fix the above errors before proceeding.[/]"

    rich.print(Panel(content, title="Errors found during analysis"))
