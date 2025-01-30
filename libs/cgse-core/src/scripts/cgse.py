"""
This script is as an administration script for the CGSE. The script provides commands to start, stop, and
get the status of the core services and any other service that is registered as a plugin.

The following main commands have been implemented:

$ cgse version

    Prints the installed version of the cgse-core and any other package that is registered under
    the entry points group 'cgse.version'.

$ cgse core {start,stop,status}

    Starts, stops, or prints the status of the core services.

Other main commands can be added from external packages when they are provided as entry points with
the group name 'cgse.command.plugins'.

Commands can be added as single commands or as a group containing further sub-commands. To add a group,
the entry point shall contain 'group' in its extras.
"""

import rich
import typer
from rich.console import Console
from rich.traceback import Traceback

from egse.plugin import entry_points
from scripts import services

app = typer.Typer(add_completion=True)
app.add_typer(services.app, name="core")


@app.command()
def version():
    """Prints the version of the cgse-core and other registered packages."""
    from egse.version import get_version_installed

    # if installed_version := get_version_installed("cgse-core"):
    #     rich.print(f"CGSE-CORE installed version = [bold default]{installed_version}[/]")

    for ep in sorted(entry_points("cgse.version"), key=lambda x: x.name):
        if installed_version := get_version_installed(ep.name):
            rich.print(f"{ep.name.upper()} installed version = [bold default]{installed_version}[/]")


def broken_command(name: str, module: str, exc: Exception):
    """
    Rather than completely crash the CLI when a broken plugin is loaded, this
    function provides a modified help message informing the user that the plugin is
    broken and could not be loaded.  If the user executes the plugin and specifies
    the `--traceback` option a traceback is reported showing the exception the
    plugin loader encountered.
    """
    def broken_plugin(traceback: bool = False):
        rich.print(f"[red]ERROR: Couldn't load this plugin command: {name} ⟶ reason: {exc}[/]")
        if traceback:
            console = Console(width=100)
            tb = Traceback.from_exception(type(exc), exc, exc.__traceback__)
            console.print(tb)

    broken_plugin.__doc__ = f"ERROR: Couldn't load plugin '{name}' from {module}"
    broken_plugin.__name__ = name
    return broken_plugin


# Load the known plugins for the `cgse` command. Plugins are added as commands to the `cgse`.

for ep in entry_points("cgse.command.plugins"):
    try:
        if not ep.extras or 'command' in ep.extras:
            app.command()(ep.load())
        elif 'group' in ep.extras:
            app.add_typer(ep.load(), name=ep.name)
        else:
            rich.print(f"\n[red]ERROR: don't know what to do with {ep.extras} for {ep.name}, command not added.[/]\n")
    except Exception as exc:
        app.command()(broken_command(ep.name, ep.module, exc))


for ep in entry_points("cgse.service.plugins"):
    try:
        app.add_typer(ep.load(), name=ep.name)
    except Exception as exc:
        app.command()(broken_command(ep.name, ep.module, exc))


@app.callback(no_args_is_help=True, invoke_without_command=True)
def main():
    """
    The main cgse command to inspect, configure, monitor the core services
    and device control servers.
    """


if __name__ == "__main__":
    app()
