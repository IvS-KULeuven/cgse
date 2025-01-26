import logging
import os
import sys
import textwrap
import traceback
from importlib.metadata import EntryPoint

import click
import rich

from egse.settings import Settings
from egse.system import get_module_location

_LOGGER = logging.getLogger(__name__)


def entry_points(name: str) -> set[EntryPoint]:
    """
    Returns a set with all entry-points for the given group name.

    When the name is not known as an entry-point group, an empty set will be returned.
    """

    import importlib.metadata

    try:
        x = importlib.metadata.entry_points()[name]
        return {ep for ep in x}  # use of set here to remove duplicates
    except KeyError:
        return set()


def load_plugins(entry_point: str) -> dict:
    """
    Returns a dictionary with plugins loaded. The keys are the names of the entry-points,
    the values are the loaded modules or objects.
    """
    eps = {}
    for ep in entry_points(entry_point):
        try:
            eps[ep.name] = ep.load()
        except Exception as exc:
            eps[ep.name] = None
            _LOGGER.error(f"Couldn't load entry point: {exc}")

    return eps


def load_settings(entry_point: str, force: bool = False) -> dict:
    """
    Returns a dictionary with all known settings for the given entry-point name.

    The entry-points are interpreted as follows: <name> = "<module>:<filename>" where

    - <name> is the name of the entry-point given in the pyproject.toml file
    - <module> is a valid module name that can be imported
    - <filename> is the name of settings YAML file that is located

    As an example, for the `cgse-common` settings, the following entry in the `pyproject.toml`:

        [project.entry-points."cgse.settings"]
        cgse-common = "cgse_common:settings.yaml"

    Note that the module name for this entry point has an underscore instead of a dash.

    Return:
        A dictionary with the entry point name as the key and a dictionary (attrdict) as the value.
    """
    eps = {}

    for ep in entry_points(entry_point):
        try:
            module = ep.module
            filename = ep.attr  # by convention, we put the settings YAML filename in attr
            path = get_module_location(module)
            if path is None:
                _LOGGER.error(
                    f"The entry-point '{ep.name}' is ill defined. The module part doesn't exist or is a "
                    f"namespace. No settings are loaded for this entry-point."
                )
                eps[ep.name] = None
            else:
                eps[ep.name] = Settings.load(location=path, filename=filename, add_local_settings=False, force=force)
        except Exception as exc:
            eps[ep.name] = None
            _LOGGER.error(f"Couldn't load entry point: {exc}")

    return eps


# The following code was adapted from the inspiring package click-plugins
# at https://github.com/click-contrib/click-plugins/

def handle_click_plugins(plugins):
    def decorator(group):
        if not isinstance(group, click.Group):
            raise TypeError("Plugins can only be attached to an instance of click.Group()")

        for entry_point in plugins or ():
            try:
                group.add_command(entry_point.load())
            except Exception:
                # Catch this so a busted plugin doesn't take down the CLI.
                # Handled by registering a dummy command that does nothing
                # other than explain the error.
                group.add_command(BrokenCommand(entry_point.name))

        return group

    return decorator


class BrokenCommand(click.Command):
    """
    Rather than completely crash the CLI when a broken plugin is loaded, this
    class provides a modified help message informing the user that the plugin is
    broken, and they should contact the owner.  If the user executes the plugin
    or specifies `--help` a traceback is reported showing the exception the
    plugin loader encountered.
    """

    def __init__(self, name):
        """
        Define the special help messages after instantiating a `click.Command()`.
        """

        click.Command.__init__(self, name)

        util_name = os.path.basename(sys.argv and sys.argv[0] or __file__)
        icon = u'\u2020'

        self.help = textwrap.dedent(
            f"""\
            Warning: entry point could not be loaded. Contact its author for help.

            {traceback.format_exc()}
            """
        )

        self.short_help = f"{icon} Warning: could not load plugin. See `{util_name} {self.name} --help`."

    def invoke(self, ctx):
        """
        Print the traceback instead of doing nothing.
        """

        rich.print()
        rich.print(self.help)
        ctx.exit(1)

    def parse_args(self, ctx, args):
        return args
