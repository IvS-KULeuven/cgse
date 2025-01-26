"""
The Settings class handles user and configuration settings that are provided in
a [`YAML`](http://yaml.org) file.

The idea is that settings are grouped by components or any arbitrary grouping that makes sense for
the application or for the user. The Settings class can read from different YAML files. By default,
settings are loaded from a file called ``settings.yaml``. The default yaml configuration file is
located in the same directory as this module.

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


The above code reads the settings from the default YAML file for a group called ``DSI``.
The settings will then be available as variables of the returned class, in this case
``dsi_settings``. The returned class is and behaves also like a dictionary, so you can check
if a configuration parameter is defined like this:

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

When you want to read settings from another YAML file, specify the ``filename=`` keyword.
If that file is located at a specific location, also use the ``location=`` keyword.

    my_settings = Settings.load(filename="user.yaml", location="/Users/JohnDoe")

The above code will read the complete YAML file, i.e. all the groups into a dictionary.

"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml  # This module is provided by the pip package PyYaml - pip install pyyaml

from egse.env import get_local_settings
from egse.env import get_local_settings_env_name
from egse.exceptions import FileIsEmptyError
from egse.system import attrdict
from egse.system import get_package_location
from egse.system import recursive_dict_update

_LOGGER = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent


class SettingsError(Exception):
    pass


def is_defined(cls, name):
    return hasattr(cls, name)


def get_attr_value(cls, name, default=None):
    try:
        return getattr(cls, name)
    except AttributeError:
        return default


def set_attr_value(cls, name, value):
    if hasattr(cls, name):
        raise KeyError(f"Overwriting setting {name} with {value}, was {hasattr(cls, name)}")


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


def get_settings_locations(location: str | Path = None, filename: str = "settings.yaml") -> list[Path]:

    yaml_locations: set[Path] = set()

    if location is None:
        package_locations = get_package_location("egse")  # `egse` is a namespace

        for package_location in package_locations:
            if (package_location / filename).exists():
                yaml_locations.add(package_location)

        yaml_locations.add(_HERE)
        _LOGGER.debug(f"yaml_locations in Settings.load():  {yaml_locations}")

    else:

        package_location = Path(location).resolve()
        if (package_location / filename).exists():
            yaml_locations.add(package_location)
        else:
            _LOGGER.warning(f"No '{filename}' file found at {package_location}.")

    return list(yaml_locations)


def load_global_settings(locations, filename: str = "settings.yaml", force: bool = False) -> attrdict:

    global_settings = attrdict()

    for yaml_location in locations:
        try:
            yaml_document = read_configuration_file(str(yaml_location / filename), force=force)
            recursive_dict_update(global_settings, yaml_document)
        except FileNotFoundError as exc:
            raise SettingsError(
                f"Filename {filename} not found at location {locations}."
            ) from exc

    return global_settings


def load_local_settings(force: bool = False):

    local_settings = {}
    try:
        local_settings_location = get_local_settings()

        if local_settings_location:
            _LOGGER.debug(f"Using {local_settings_location} to update global settings.")
            try:
                yaml_document_local = read_configuration_file(local_settings_location, force=force)
                if yaml_document_local is None:
                    raise FileIsEmptyError()
                local_settings = attrdict(
                    {name: value for name, value in yaml_document_local.items()}
                )
            except FileNotFoundError as exc:
                raise SettingsError(
                    f"Local settings YAML file '{local_settings_location}' not found. "
                    f"Check your environment variable {get_local_settings_env_name()}."
                ) from exc
            except FileIsEmptyError:
                _LOGGER.warning(
                    f"Local settings YAML file '{local_settings_location}' is empty. "
                    f"No local settings were loaded.")

    except KeyError as exc:
        _LOGGER.warning(f"The environment variable {get_local_settings_env_name()} is not defined. (from "
                        f"{exc.__class__.__name__}: {exc})")

    return local_settings


def read_configuration_file(filename: str, *, force=False):
    """
    Read the YAML input configuration file. The configuration file is only read
    once and memoized as load optimization.

    Args:
        filename (str): the fully qualified filename of the YAML file
        force (bool): force reloading the file

    Returns:
        a dictionary containing all the configuration settings from the YAML file.
    """
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

    @classmethod
    def load_from_entry_points(
            cls,
            entry_point: str = 'cgse.settings',
            add_local_settings: bool = False,
            force: bool = False
    ):
        from egse.plugin import load_settings

        ep_settings = load_settings(entry_point, force)

        global_settings = attrdict(label="Settings")

        for name, settings in ep_settings.items():
            recursive_dict_update(global_settings, settings)

        # Load the LOCAL settings YAML file

        if add_local_settings:
            local_settings = load_local_settings(force)
            recursive_dict_update(global_settings, local_settings)

        return global_settings


    @classmethod
    def load(cls, group_name=None, filename="settings.yaml", location=None, *, force=False, add_local_settings=True):
        """
        Load the settings for the given group from YAML configuration file.
        When no group is provided, the complete configuration is returned.

        The default YAML file is 'settings.yaml' and is located in the same directory
        as the settings module.

        About the ``location`` keyword several options are available.

        * when no location is given, i.e. ``location=None``, the YAML settings file is searched for
          at the same location as the settings module.

        * when a relative location is given, the YAML settings file is searched for relative to the
          current working directory.

        * when an absolute location is given, that location is used 'as is'.

        Args:
            group_name (str): the name of one of the main groups from the YAML file
            filename (str): the name of the YAML file to read
            location (str, Path): the path to the location of the YAML file
            force (bool): force reloading the file
            add_local_settings (bool): update the Settings with site specific local settings

        Returns:
            a dynamically created class with the configuration parameters as instance variables.

        Raises:
            a SettingsError when the group is not defined in the YAML file.
        """

        # Load all detected YAML documents, these are considered global settings

        yaml_locations = get_settings_locations(location, filename)
        global_settings = load_global_settings(yaml_locations, filename, force)

        if not global_settings:
            raise SettingsError(f"There were no global settings defined for {filename} at {yaml_locations}.")

        # Load the LOCAL settings YAML file

        if add_local_settings:
            local_settings = load_local_settings(force)
        else:
            local_settings = {}

        if group_name in (None, ""):
            global_settings = attrdict(
                {name: value for name, value in global_settings.items()},
                label="Settings"
            )
            if add_local_settings:
                recursive_dict_update(global_settings, local_settings)
            return global_settings

        if group_name in global_settings:
            include_global_settings = True
        else:
            include_global_settings = False
        if group_name in local_settings:
            include_local_settings = True
        else:
            include_local_settings = False

        if not include_global_settings and not include_local_settings:
            raise SettingsError(
                f"Group name '{group_name}' is not defined in the global nor in the local settings."
            )

        # Check if the group has any settings

        if include_global_settings and not global_settings[group_name]:
            _LOGGER.warning(f"Empty group in YAML document {filename} for {group_name}.")

        if include_global_settings:
            group_settings = attrdict(
                {name: value for name, value in global_settings[group_name].items()},
                label=group_name
            )
        else:
            group_settings = attrdict(label=group_name)

        if add_local_settings and include_local_settings:
            recursive_dict_update(group_settings, local_settings[group_name])

        return group_settings

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
        location = get_local_settings()
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
