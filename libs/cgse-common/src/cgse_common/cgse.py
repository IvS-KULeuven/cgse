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

import textwrap

import rich
import typer
from rich.console import Console
from rich.traceback import Traceback
from typer.core import TyperGroup

from cgse_common import AppState
from egse.plugin import HierarchicalEntryPoints
from egse.plugin import entry_points
from egse.system import get_package_description
from egse.system import snake_to_title


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


class SortedCommandGroup(TyperGroup):
    """This class sorts the commands based on the following criteria:

    - a few priority commands come first
    - the rest of the commands are sorted alphabetically

    """

    def list_commands(self, ctx):
        # Get list of all commands
        commands = super().list_commands(ctx)

        # Define priority commands in specific order
        priority_commands = ["init", "version", "show", "top", "core", "registry", "log", "cm", "sm", "pm"]

        # Custom sort:
        # First the priority commands in the given order (their index)
        # Then the rest of the commands, alphabetically
        def get_command_priority(command_name):
            if command_name in priority_commands:
                return 0, priority_commands.index(command_name)
            return 1, command_name  # Using tuple for consistent sorting

        return sorted(commands, key=get_command_priority)


app = typer.Typer(add_completion=True, cls=SortedCommandGroup)


@app.command()
def version(ctx: typer.Context):
    """Prints the version of the cgse-core and other registered packages."""
    from egse.version import get_version_installed

    # This is more of a show-case for using application wide optional arguments and how to pass
    # them into (sub-)commands.

    state: AppState = ctx.obj

    if state.verbose:
        rich.print(
            textwrap.dedent(
                """
                All version of the packages that are part of the monorepo `cgse` will have the same version.

                (Third-party package versions are shown only when the package properly declares its version in its
                packaging metadata.)
                """
            )
        )

    # if installed_version := get_version_installed("cgse-core"):
    #     rich.print(f"CGSE-CORE installed version = [bold default]{installed_version}[/]")

    for ep in sorted(entry_points("cgse.version"), key=lambda x: x.name):
        if installed_version := get_version_installed(ep.name):
            rich.print(
                f"{ep.name.upper()} installed version = [bold default]{installed_version}[/] — "
                f"{get_package_description(ep.name)}"
            )


def subcommand_callback(ctx: typer.Context):
    """Normal callback."""
    if ctx.invoked_subcommand is None:
        typer.echo("No command specified:")
        typer.echo(ctx.get_help())
        raise typer.Exit()


def build_app():
    global app

    # rich.print("Available command groups:", entry_points("cgse.command"))

    for ep in entry_points("cgse.command"):
        try:
            obj = ep.load()
            if isinstance(obj, typer.Typer):
                obj.callback(invoke_without_command=True)(subcommand_callback)
                app.add_typer(obj, name=ep.name)
            else:
                app.command()(obj)
        except Exception as exc:
            app.command()(broken_command(ep.name, ep.module, exc))

    cgse_eps = HierarchicalEntryPoints("cgse.service")

    # rich.print("Available services groups:", cgse_eps.get_all_groups())

    for group in cgse_eps.get_all_groups():
        for ep in entry_points(group):
            try:
                if group == "cgse.service":
                    app.add_typer(ep.load(), name=ep.name)
                else:
                    command_group = snake_to_title(group.split(".")[-1])
                    plugin_app: typer.Typer = ep.load()
                    plugin_app.callback(invoke_without_command=True)(subcommand_callback)
                    app.add_typer(plugin_app, name=ep.name, rich_help_panel=command_group)
            except Exception as exc:
                app.command()(broken_command(ep.name, ep.module, exc))


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, verbose: bool = False):
    """
    The `cgse` command is used to:

    - initialise your project environment

    - visualise and check project and environment settings

    - inspect, configure, monitor the core services and device control servers.
    """

    # This is more of a show-case for using application wide optional arguments and how to pass
    # them into (sub-)commands.

    ctx.obj = AppState(verbose=verbose)

    if ctx.invoked_subcommand is None:
        # print("Try 'cgse --help' for a list of commands.")
        typer.echo(ctx.get_help())


build_app()


if __name__ == "__main__":
    app()
