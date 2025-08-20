"""
This module provides function to load plugins and settings from entry-points.
"""

__all__ = [
    "load_plugins_ep",
    "load_plugins_fn",
    "get_file_infos",
    "entry_points",
    "HierarchicalEntryPoints",
]

import importlib.util
import os
import sys
import textwrap
import traceback
import types
from functools import lru_cache
from pathlib import Path

import click
import rich

from egse.log import logger
from egse.system import type_name

if sys.version_info >= (3, 12):  # Use the standard library version (Python 3.10+)
    from importlib.metadata import entry_points as lib_entry_points
    from importlib.metadata import EntryPoint
else:
    # Fall back to the backport for Python 3.9
    from importlib_metadata import entry_points as lib_entry_points
    from importlib_metadata import EntryPoint


HERE = Path(__file__).parent


def entry_points(group: str) -> set[EntryPoint]:
    """
    Returns a set with all entry-points for the given group name.

    When the name is not known as an entry-point group, an empty set will be returned.
    """

    try:
        x = lib_entry_points().select(group=group)
        return {ep for ep in x}  # use of set here to remove duplicates
    except KeyError:
        return set()


def load_plugins_ep(entry_point: str) -> dict:
    """
    Returns a dictionary with plugins loaded. The keys are the names of the entry-points,
    the values are the loaded modules or objects.

    Note:
        When an entry point cannot be loaded, an error is logged and the value for that
        entry point in the returned dictionary will be None.
    """
    eps = {}
    for ep in entry_points(entry_point):
        try:
            eps[ep.name] = ep.load()
        except Exception as exc:
            eps[ep.name] = None
            logger.error(f"Couldn't load entry point {entry_point}: {type_name(exc)} – {exc}")

    return eps


@lru_cache
def load_plugins_fn(pattern: str, package_name: str = None) -> dict[str, types.ModuleType]:
    """
    Returns a dictionary with plugins loaded for the filenames that match the given pattern.
    The keys are the names of the modules, the values are the loaded modules.

    If no package_name is provided, the pattern is relative to the location of this module
    (which is in the top-level module `egse`).

    If the pattern results in two or more modules with the same name, a warning will be logged
    and only the last imported module will be returned in the dictionary.

    Plugins are usually located in the `egse.plugins` module. Remember that `egse.plugins`
    is a namespace and external packages can also deliver plugin modules in that location.

    Note:
        When a plugin cannot be loaded, an error is logged.

        This function uses an LRU cache to avoid reloading modules. If you need to reload,
        use `load_plugins_fn.cache_clear()` to reset the cache.

    Raises:
        ImportError when the given package_name cannot be imported as a module.

    Examples:

        # Loading the InfluxDB plugin for time series metrics
        >>> influxdb = load_plugins_fn("influxdb.py", "egse.plugins.metrics")

        # Loading the HDF5 storage plugin for PLATO
        >>> hdf5 = load_plugins_fn("hdf5.py", "egse.plugins.storage")

        # Loading all plugins
        >>> x = load_plugins_fn("**/*.py", "egse.plugins")

    """
    loaded_modules = {}
    failed_modules = {}  # we keep failed modules for housekeeping only

    if package_name is None:
        package_path = [HERE]
    else:
        try:
            package = importlib.import_module(package_name)
        except ImportError as exc:
            raise ImportError(f"Cannot import package '{package_name}': {exc}")

        if hasattr(package, "__path__"):
            package_path = package.__path__
        else:
            package_path = [package.__file__.replace("__init__.py", "")]

    # rich.print(package_path)

    for path_entry in map(Path, package_path):
        # rich.print(path_entry)
        for plugin_file in path_entry.rglob(pattern):
            # rich.print("    ", plugin_file)
            module_name = plugin_file.stem
            try:
                spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if module_name in loaded_modules:
                    logger.warning(
                        f"Overwriting module '{module_name}' from {loaded_modules[module_name].__file__} "
                        f"with {plugin_file}."
                    )
                loaded_modules[module_name] = module
            except Exception as exc:
                error_msg = f"Couldn't load module '{module_name}' from {plugin_file}: {type_name(exc)} – {exc}"
                logger.error(error_msg)
                if module_name in failed_modules:
                    logger.warning(f"Overwriting previously unloaded module '{module_name}' with {plugin_file}.")
                failed_modules[module_name] = error_msg

    return loaded_modules


def get_file_infos(entry_point: str) -> dict[str, tuple[Path, str]]:
    """
    Returns a dictionary with location and filename of all the entries found for
    the given entry-point name.

    The entry-points are interpreted as follows: `<name> = "<module>:<filename>"` where

    - `<name>` is the name of the entry-point given in the pyproject.toml file
    - `<module>` is a valid module name that can be imported and from which the location can be determined.
    - `<filename>` is the name of the target file, e.g. a YAML file

    As an example, for the `cgse-common` settings, the following entry in the `pyproject.toml`:

        [project.entry-points."cgse.settings"]
        cgse-common = "cgse_common:settings.yaml"

    Note that the module name for this entry point has an underscore instead of a dash.

    Return:
        A dictionary with the entry point name as the key and a tuple (location, filename) as the value.
    """
    from egse.system import get_module_location

    eps = dict()

    for ep in entry_points(entry_point):
        try:
            path = get_module_location(ep.module)

            if path is None:
                logger.error(
                    f"The entry-point '{ep.name}' is ill defined. The module part doesn't exist or is a "
                    f"namespace. No settings are loaded for this entry-point."
                )
            else:
                eps[ep.name] = (path, ep.attr)

        except Exception as exc:
            logger.error(f"The entry point '{ep.name}' is ill defined: {exc}")

    return eps


class HierarchicalEntryPoints:
    def __init__(self, base_group: str):
        self.base_group = base_group
        self._discover_groups()

    def _discover_groups(self):
        """Discover all groups that match the base group pattern."""
        all_eps = lib_entry_points()
        # print(f"{type(all_eps) = }")

        self.groups = {}
        self.flat_entries = []

        for ep in all_eps:
            # rich.print(f"{type(ep) = }, {dir(ep) = }")
            if ep.group == self.base_group or ep.group.startswith(f"{self.base_group}."):
                # print(f"{ep.group = }, {ep = }")
                if ep.group in self.groups:
                    self.groups[ep.group].append(ep)
                else:
                    self.groups[ep.group] = [ep]
                self.flat_entries.append(ep)

    def get_all_entry_points(self) -> list:
        """Get all entry points as a flat list."""
        return self.flat_entries

    def get_by_subgroup(self, subgroup=None) -> list:
        """Get entry points from a specific subgroup."""
        if subgroup is None:
            return self.groups.get(self.base_group, [])

        full_group = f"{self.base_group}.{subgroup}"
        return self.groups.get(full_group, [])

    def get_all_groups(self) -> list:
        """Get all discovered group names."""
        return list(self.groups.keys())

    def get_by_type(self, entry_type) -> list:
        """Get entry points by type (assuming type is the subgroup name)."""
        return self.get_by_subgroup(entry_type)


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


# This class is filtered and will not be included in the API docs, see `mkdocs.yml`.


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
        icon = "\u2020"

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
