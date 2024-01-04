"""
The Settings class handles user and configuration settings that are provided in
a [`YAML`](http://yaml.org) file.

The idea is that settings are grouped by components or any arbitrary grouping that makes sense for
the application or for the user. The Settings class can read from different YAML files. By default,
settings are loaded from a file called ``settings.yaml``. The default yaml configuration file is
located in the same directory as this module.

The YAML file is read and the configuration parameters for the given group are
made available as instance variables of the returned class.

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

import logging
import os
import pathlib
import re

import yaml  # This module is provided by the pip package PyYaml - pip install pyyaml

from egse.env import ENV_PLATO_LOCAL_SETTINGS
from egse.exceptions import FileIsEmptyError
from egse.system import AttributeDict
from egse.system import get_caller_info
from egse.system import ignore_m_warning
from egse.system import recursive_dict_update

logger = logging.getLogger(__name__)


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


class Settings:
    """
    The Settings class provides a load() method that loads configuration settings for a group
    into a dynamically created class as instance variables.
    """

    __memoized_yaml = {}  # Memoized settings yaml files

    __profile = False  # Used for profiling methods and functions
    __simulation = False  # Use simulation mode where applicable and possible

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
    def read_configuration_file(cls, filename: str, *, force=False):
        """
        Read the YAML input configuration file. The configuration file is only read
        once and memoized as load optimization.

        Args:
            filename (str): the fully qualified filename of the YAML file
            force (bool): force reloading the file

        Returns:
            a dictionary containing all the configuration settings from the YAML file.
        """
        if force or filename not in cls.__memoized_yaml:

            logger.debug(f"Parsing YAML configuration file {filename}.")

            with open(filename, "r") as stream:
                try:
                    yaml_document = yaml.load(stream, Loader=SAFE_LOADER)
                except yaml.YAMLError as exc:
                    logger.error(exc)
                    raise SettingsError(f"Error loading YAML document {filename}") from exc

            cls.__memoized_yaml[filename] = yaml_document

        return cls.__memoized_yaml[filename]

    @classmethod
    def get_memoized_locations(cls):
        return cls.__memoized_yaml.keys()

    @classmethod
    def load(cls, group_name=None, filename="settings.yaml", location=None, *, force=False,
             add_local_settings=True):
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
            location (str): the path to the location of the YAML file
            force (bool): force reloading the file
            add_local_settings (bool): update the Settings with site specific local settings

        Returns:
            a dynamically created class with the configuration parameters as instance variables.

        Raises:
            a SettingsError when the group is not defined in the YAML file.
        """

        _THIS_FILE_LOCATION = pathlib.Path(__file__).resolve().parent

        if location is None:

            # Check if the yaml file is located at the location of the caller,
            # if not, use the file that is located where the Settings module is located.

            caller_dir = get_caller_info(level=2).filename
            caller_dir = pathlib.Path(caller_dir).resolve().parent

            if (caller_dir / filename).is_file():
                yaml_location = caller_dir
            else:
                yaml_location = _THIS_FILE_LOCATION
        else:

            # The location was given as an argument

            yaml_location = pathlib.Path(location).resolve()

        logger.log(5, f"yaml_location in Settings.load(location={location}) is {yaml_location}")

        # Load the YAML global document

        try:
            yaml_document_global = cls.read_configuration_file(
                yaml_location / filename, force=force
            )
        except FileNotFoundError as exc:
            raise SettingsError(
                f"Filename {filename} not found at location {yaml_location}."
            ) from exc

        # Check if there were any groups defined in the YAML document

        if not yaml_document_global:
            raise SettingsError(f"Empty YAML document {filename} at {yaml_location}.")

        # Load the LOCAL settings YAML file

        if add_local_settings:
            try:
                local_settings_location = os.environ[ENV_PLATO_LOCAL_SETTINGS]
                logger.log(5, f"Using {ENV_PLATO_LOCAL_SETTINGS} to update global settings.")
                try:
                    yaml_document_local = cls.read_configuration_file(
                        local_settings_location, force=force
                    )
                    if yaml_document_local is None:
                        raise FileIsEmptyError()
                    local_settings = AttributeDict(
                        {name: value for name, value in yaml_document_local.items()}
                    )
                except FileNotFoundError as exc:
                    raise SettingsError(
                        f"Local settings YAML file '{local_settings_location}' not found. "
                        f"Check your environment variable {ENV_PLATO_LOCAL_SETTINGS}."
                    ) from exc
                except FileIsEmptyError:
                    logger.warning(f"Local settings YAML file '{local_settings_location}' is empty. "
                                   f"No local settings were loaded.")
                    local_settings = {}
            except KeyError:
                logger.debug(f"The environment variable {ENV_PLATO_LOCAL_SETTINGS} is not defined.")
                local_settings = {}

        if group_name in (None, ""):
            global_settings = AttributeDict(
                {name: value for name, value in yaml_document_global.items()}
            )
            if add_local_settings:
                recursive_dict_update(global_settings, local_settings)
            return global_settings

        # Check if the requested group is defined in the YAML document

        if group_name not in yaml_document_global:
            raise SettingsError(
                f"Group name '{group_name}' is not defined in the YAML "
                f"document '{filename}' at '{yaml_location}."
            )

        # Check if the group has any settings

        if not yaml_document_global[group_name]:
            raise SettingsError(f"Empty group in YAML document {filename} at {yaml_location}.")

        group_settings = AttributeDict(
            {name: value for name, value in yaml_document_global[group_name].items()}
        )

        if add_local_settings and group_name in local_settings:
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

        return msg

    @classmethod
    def set_profiling(cls, flag):
        cls.__profile = flag

    @classmethod
    def profiling(cls):
        return cls.__profile

    @classmethod
    def set_simulation_mode(cls, flag: bool) -> bool:
        cls.__simulation = flag

    @classmethod
    def simulation_mode(cls) -> bool:
        return cls.__simulation


ignore_m_warning('egse.settings')

if __name__ == "__main__":

    # We provide convenience to inspect the settings by calling this module directly from Python.
    #
    # python -m egse.settings
    #
    # Use the '--help' option to see the what your choices are.

    logging.basicConfig(level=20)

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            f"Print out the default Settings, updated with local settings if the "
            f"{ENV_PLATO_LOCAL_SETTINGS} environment variable is set."
        ),
    )
    parser.add_argument("--local", action="store_true", help="print only the local settings.")
    args = parser.parse_args()

    # The following import will activate the pretty printing of the AttributeDict
    # through the __rich__ method.

    from rich import print

    if args.local:
        location = os.environ.get(ENV_PLATO_LOCAL_SETTINGS)
        if location:
            settings = Settings.load(filename=location)
            print(settings)
            print(f"Loaded from [purple]{location}.")
        else:
            print("[red]No local settings defined.")
    else:
        settings = Settings.load()
        print(settings)
        print("[blue]Memoized locations:")
        locations = Settings.get_memoized_locations()
        print([str(loc) for loc in locations])


def get_site_id() -> str:

    site = Settings.load("SITE")
    return site.ID
