"""
The Settings class handles user and configuration settings that are provided in
a [`YAML`](http://yaml.org) file.

The idea is that settings are grouped by components or any arbitrary grouping that makes sense for
the application or for the user. Settings are also modular and provided by each package by means
of entry-points.The Settings class can read from different YAML files.

By default, settings are loaded from a file called `settings.yaml`, but this can be changed in the entry-point
definition.

The yaml configuration files are provided as entry-points by the packages that provided an entry-point
group 'cgse.settings'. The Settings dictionary (attrdict) is constructed from the configuration YAML
files from each of the packages. Settings can be overwritten by the next package configuration file.
So, make sure the group names in each package configuration file are unique.

The YAML file is read and the configuration parameters for the given group are
available as instance variables of the returned class.

The intended use is as follows:

    from egse.settings import Settings

    dsi_settings = Settings.load("DSI")

    if (dsi_settings.RMAP_BASE_ADDRESS
        <= addr
        < dsi_settings.RMAP_BASE_ADDRESS + dsi_settings.RMAP_MEMORY_SIZE):
        # do something here
    else:
        raise RMAPError("Attempt to access outside the RMAP memory map.")

The above code reads the settings from the default YAML file for a group called `DSI`.
The settings will then be available as variables of the returned class, in this case
`dsi_settings`. The returned class is and behaves also like a dictionary, so you can
check if a configuration parameter is defined like this:

    if "DSI_FEE_IP_ADDRESS" not in dsi_settings:
        # define the IP address of the DSI

The YAML section for the above code looks like this:

    DSI:

        # DSI Specific Settings

        DSI_FEE_IP_ADDRESS  10.33.178.144   # IP address of the DSI EtherSpaceLink interface
        LINK_SPEED:                   100   # SpW link speed used for both up- and downlink

        # RMAP Specific Settings

        RMAP_BASE_ADDRESS:     0x00000000   # The start of the RMAP memory map managed by the FEE
        RMAP_MEMORY_SIZE:            4096   # The size of the RMAP memory map managed by the FEE

When you want to read settings from another YAML file, specify the `filename=` keyword.
If that file is located at a specific location, also use the `location=` keyword.

    my_settings = Settings.load(filename="user.yaml", location="/Users/JohnDoe")

The above code will read the YAML file from the given location and not from the entry-points.

"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml  # This module is provided by the pip package PyYaml - pip install pyyaml

from egse.env import get_local_settings_env_name
from egse.env import get_local_settings_path
from egse.system import attrdict
from egse.system import recursive_dict_update

_LOGGER = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent


class SettingsError(Exception):
    pass


# Fix the problem: YAML loads 5e-6 as string and not a number
# https://stackoverflow.com/questions/30458977/yaml-loads-5e-6-as-string-and-not-a-number

SAFE_LOADER = yaml.SafeLoader
SAFE_LOADER.add_implicit_resolver(
    u'tag:yaml.org,2002:float',
    re.compile(u"""^(?:
     [-+]?(?:[0-9][0-9_]*)\\.[0-9_]*(?:[eE][-+]?[0-9]+)?
    |[-+]?(?:[0-9][0-9_]*)(?:[eE][-+]?[0-9]+)
    |\\.[0-9_]+(?:[eE][-+][0-9]+)?
    |[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\\.[0-9_]*
    |[-+]?\\.(?:inf|Inf|INF)
    |\\.(?:nan|NaN|NAN))$""", re.X),
    list(u'-+0123456789.'))


def load_settings_file(path: Path, filename: str, force: bool = False) -> attrdict:
    """
    Loads the YAML configuration file that is located at `path / filename`.

    Args:
        - path (PATH): the folder where the YAML file is located
        - filename (str): the name of the YAML configuration file
        - force (bool): force reloading, i.e. don't use the cached information

    Raises:
        A SettingsError when the configuration file doesn't exist or cannot be found.

        A SettingsError when there was an error reading the configuration file.

    Returns:
         A dictionary (attrdict) with all the settings from the given file.

         Note that, in case of an empty configuration file, and empty dictionary
         is returned and a warning message is issued.
    """
    try:
        yaml_document = read_configuration_file(path / filename, force=force)
        settings = attrdict(
            {name: value for name, value in yaml_document.items()}
        )
    except FileNotFoundError as exc:
        raise SettingsError(
            f"The Settings YAML file '{filename}' is not found at {path!s}. "
        ) from exc

    if not settings:
        _LOGGER.warning(
            f"The Settings YAML file '{filename}' at {path!s} is empty. "
            f"No local settings were loaded, an empty dictionary is returned.")

    return settings


def load_global_settings(entry_point: str = 'cgse.settings', force: bool = False) -> attrdict:
    """
    Loads the settings that are defined by the given entry_point. The entry-points are defined in the
    `pyproject.toml` files of the packages that export their global settings.

    Args:
         - entry_point (str): the name of the entry-point group [default: 'cgse.settings']
         - force (bool): force reloading the settings, i.e. ignore the cache

    Returns:
        A dictionary (attrdict) containing a collection of all the settings exported by the packages
        through the given entry-point.

    """
    from egse.plugin import get_file_infos

    ep_settings = get_file_infos(entry_point)

    global_settings = attrdict(label="Settings")

    for ep_name, (path, filename) in ep_settings.items():
        settings = load_settings_file(path, filename, force)
        recursive_dict_update(global_settings, settings)

    return global_settings


def load_local_settings(force: bool = False) -> attrdict:
    """
    Loads the local settings file that is defined from the environment variable <PROJECT>_LOCAL_SETTINGS.

    This function might return an empty dictionary when

      - the local settings YAML file is empty
      - the local settings environment variable is not defined.

    in both cases a warning message is logged.

    Returns:
        A dictionary (attrdict) with all local settings.

    Raises:
        A SettingsError when the local settings YAML file is not found. Check the <PROJECT>_LOCAL_SETTINGS
        environment variable.
    """
    local_settings = attrdict()

    local_settings_path = get_local_settings_path()

    if local_settings_path:
        path = Path(local_settings_path)
        local_settings = load_settings_file(path.parent, path.name, force)

    return local_settings


def read_configuration_file(filename: Path, *, force=False):
    """
    Read the YAML input configuration file. The configuration file is only read
    once and memoized as load optimization.

    Args:
        filename (Path): the fully qualified filename of the YAML file
        force (bool): force reloading the file, even when it was memoized

    Raises:
        A SettingsError when there was an error reading the YAML file.

    Returns:
        a dictionary containing all the configuration settings from the YAML file.
    """
    filename = str(filename)

    if force or not Settings.is_memoized(filename):

        _LOGGER.debug(f"Parsing YAML configuration file {filename}.")

        with open(filename, "r") as stream:
            try:
                yaml_document = yaml.load(stream, Loader=SAFE_LOADER)
            except yaml.YAMLError as exc:
                _LOGGER.error(exc)
                raise SettingsError(f"Error loading YAML document {filename}") from exc

        Settings.add_memoized(filename, yaml_document)

    return Settings.get_memoized(filename) or {}


class Settings:
    """
    The Settings class provides a load() method that loads configuration settings for a group
    into a dynamically created class as instance variables.
    """

    __memoized_yaml = {}  # Memoized settings yaml files
    __profile = False  # Used for profiling methods and functions

    LOG_FORMAT_DEFAULT = "%(levelname)s:%(module)s:%(lineno)d:%(message)s"
    LOG_FORMAT_FULL = "%(asctime)23s:%(levelname)8s:%(lineno)5d:%(name)-20s: %(message)s"
    LOG_FORMAT_THREAD = (
        "%(asctime)23s:%(levelname)7s:%(lineno)5d:%(name)-20s(%(threadName)-15s): %(message)s"
    )
    LOG_FORMAT_PROCESS = (
        "%(asctime)23s:%(levelname)7s:%(lineno)5d:%(name)20s.%(funcName)-31s(%(processName)-20s): "
        "%(message)s"
    )
    LOG_FORMAT_DATE = "%d/%m/%Y %H:%M:%S"

    @classmethod
    def get_memoized_locations(cls) -> list:
        return list(cls.__memoized_yaml.keys())

    @classmethod
    def is_memoized(cls, filename: str) -> bool:
        return filename in cls.__memoized_yaml

    @classmethod
    def add_memoized(cls, filename: str, yaml_document: Any):
        cls.__memoized_yaml[filename] = yaml_document

    @classmethod
    def get_memoized(cls, filename: str):
        return cls.__memoized_yaml.get(filename)

    @classmethod
    def clear_memoized(cls):
        cls.__memoized_yaml.clear()

    @classmethod
    def set_profiling(cls, flag):
        cls.__profile = flag

    @classmethod
    def profiling(cls):
        return cls.__profile

    @staticmethod
    def _load_all(
            entry_point: str = 'cgse.settings',
            add_local_settings: bool = False,
            force: bool = False
    ) -> attrdict:
        """
        Loads all settings from all package with the entry point 'cgse.settings'
        """
        global_settings = load_global_settings(entry_point, force)

        # Load the LOCAL settings YAML file

        if add_local_settings:
            local_settings = load_local_settings(force)
            recursive_dict_update(global_settings, local_settings)

        return global_settings

    @staticmethod
    def _load_group(
            group_name: str,
            entry_point: str = 'cgse.settings',
            add_local_settings: bool = False,
            force: bool = False
    ) -> attrdict:

        global_settings = load_global_settings(entry_point, force)

        group_settings = attrdict(label=group_name)

        if group_name in global_settings:
            group_settings = attrdict(
                {name: value for name, value in global_settings[group_name].items()},
                label=group_name
            )

        if add_local_settings:
            local_settings = load_local_settings(force)
            if group_name in local_settings:
                recursive_dict_update(group_settings, local_settings[group_name])

        if not group_settings:
            raise SettingsError(
                f"Group name '{group_name}' is not defined in the global nor in the local settings."
            )

        return group_settings

    @staticmethod
    def _load_one(location: str, filename: str, force=False) -> attrdict:

        return load_settings_file(Path(location).expanduser(), filename, force)

    @classmethod
    def load(
            cls,
            group_name=None, filename="settings.yaml", location=None,
            *, add_local_settings=True, force=False
    ):
        """
        Load the settings for the given group. When no group is provided, the
        complete configuration is returned.

        The Settings are loaded from entry-points that are defined in each of the
        packages that provide a Settings file.

        If a location is explicitly provided, the Settings will be loaded from that
        location, using the given filename or the default (which is settings.yaml).

        Args:
            group_name (str): the name of one of the main groups from the YAML file
            filename (str): the name of the YAML file to read [default=settings.yaml]
            location (str, Path): the path to the location of the YAML file
            force (bool): force reloading the file
            add_local_settings (bool): update the Settings with site specific local settings

        Returns:
            a dynamically created class with the configuration parameters as instance variables.

        Raises:
            a SettingsError when the group is not defined in the YAML file.
        """
        if group_name:
            return cls._load_group(group_name, add_local_settings=add_local_settings, force=force)
        elif location:
            return cls._load_one(location=location, filename=filename, force=force)
        else:
            return cls._load_all(add_local_settings=add_local_settings, force=force)

    @classmethod
    def to_string(cls):
        """
        Returns a simple string representation of the cached configuration of this Settings class.
        """
        memoized = cls.__memoized_yaml

        msg = ""
        for key in memoized.keys():
            msg += f"YAML file: {key}\n"
            for field in memoized[key].keys():
                length = 60
                line = str(memoized[key][field])
                trunc = line[:length]
                if len(line) > length:
                    trunc += " ..."
                msg += f"   {field}: {trunc}\n"

        return msg.rstrip()


def main(args: list | None = None):  # pragma: no cover
    # We provide convenience to inspect the settings by calling this module directly from Python.
    #
    # python -m egse.settings
    #
    # Use the '--help' option to see what your choices are.

    logging.basicConfig(level=20)

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            f"Print out the default Settings, updated with local settings if the "
            f"{get_local_settings_env_name()} environment variable is set."
        ),
    )
    parser.add_argument("--local", action="store_true", help="print only the local settings.")
    parser.add_argument("--global", action="store_true",
                        help="print only the global settings, don't include local settings.")
    parser.add_argument("--group", help="print only settings for this group")
    args = parser.parse_args(args or [])

    # The following import will activate the pretty printing of the AttributeDict
    # through the __rich__ method.

    from rich import print

    if args.local:
        location = get_local_settings_path()
        if location:
            location = str(Path(location).expanduser().resolve())
            settings = Settings.load(filename=location)
            print(settings)
            print(f"Loaded from [purple]{location}.")
        else:
            print("[red]No local settings defined.")
    else:
        # if the global option is given we don't want to include local settings
        add_local_settings = False if vars(args)["global"] else True

        if args.group:
            settings = Settings.load(args.group, add_local_settings=add_local_settings)
        else:
            settings = Settings.load(add_local_settings=add_local_settings)
        print(settings)
        print("[blue]Memoized locations:")
        locations = Settings.get_memoized_locations()
        print([str(loc) for loc in locations])


def get_site_id() -> str:

    site = Settings.load("SITE")
    return site.ID


# ignore_m_warning('egse.settings')

if __name__ == "__main__":
    main()
