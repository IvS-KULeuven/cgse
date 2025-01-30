import subprocess
import sys
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
