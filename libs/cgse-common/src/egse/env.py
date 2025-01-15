"""
This module provides functionality to work with and check your environment variables.

The module provides functions to get/set the location of the data storage, the configuration data, and the log files.
The locations are determined from the environment variables that are set for the project.

Two important and mandatory environment variables are PROJECT and SITE_ID. The PROJECT environment variable is
used to construct the names of the other environment variables that are specific to the project. The SITE_ID
environment variable is used in the value that is returned for some the of project specific environment variables.

Mandatory environment variables:

- PROJECT: the name of the project, e.g. PLATO, ARIEL. [shall be UPPER case]
- SITE_ID: the site identifier, e.g. the lab name or organisation acronym. [shall be UPPER case]

The following environment variables are used by the project:

- <PROJECT>_DATA_STORAGE_LOCATION: the root of the data storage location.
- <PROJECT>_CONF_DATA_LOCATION: the location of the configuration data.
- <PROJECT>_CONF_REPO_LOCATION: the location of the configuration data GitHub repository.
- <PROJECT>_LOG_FILE_LOCATION: the location of the log files.
- <PROJECT>_LOCAL_SETTINGS: the YAML file that contains site specific local settings.

Do not use the environment variables directly, but use the functions provided by this module to get the locations.

- get_data_storage_location(): returns the full path of the data storage location.
- get_conf_data_location(): returns the full path of the location of the configuration data.
- get_conf_repo_location(): returns the full path of the location of the configuration data repository.
- get_log_file_location(): returns the full path of the location of the log files.
- get_local_settings(): returns the fully qualified filename of the local settings YAML file.

WARNING:

    These environment variables shall not be changed outside the processes that use them and also not using the
    `os.environ` within the code. For the known environment variables, use the dedicated 'setters' that are provided
    by this module. If there is a need to change the environment variables, e.g. in unit tests, make sure to call the
    `egse.env.initialize()` to reset the proper state.

"""
from __future__ import annotations

__all__ = [
    "get_data_storage_location",
    "set_data_storage_location",
    "get_data_storage_location_env_name",
    "get_conf_data_location",
    "set_conf_data_location",
    "get_conf_data_location_env_name",
    "get_conf_repo_location",
    "set_conf_repo_location",
    "get_conf_repo_location_env_name",
    "get_log_file_location",
    "set_log_file_location",
    "get_log_file_location_env_name",
    "get_local_settings",
    "set_local_settings",
    "get_local_settings_env_name",
]

import os
import warnings
from pathlib import Path

from egse.system import all_logging_disabled
from egse.system import ignore_m_warning

# Every project shall have a PROJECT and a SITE_ID environment variable set. This variable will be used to
# create the other environment variables that are specific to the project.

MANDATORY_ENVIRONMENT_VARIABLES = [
    "PROJECT",
    "SITE_ID",
]

# The environment variables that are known to be used by the project. These environment variables shall be set
# as ${PROJECT}_<variable name>, e.g. PLATO_DATA_STORAGE_LOCATION. For each of these variables, there is a
# corresponding function that will return the value of the environment variable. The environment variable is not
# mandatory and if not set, a LookupError will be raised.

KNOWN_PROJECT_ENVIRONMENT_VARIABLES = [
    "DATA_STORAGE_LOCATION",
    "CONF_DATA_LOCATION",
    "CONF_REPO_LOCATION",
    "LOG_FILE_LOCATION",
    "LOCAL_SETTINGS",
]


def initialize():
    """
    Initialize the environment variables that are required for the CGSE to function properly.
    This function will print a warning if any of the mandatory environment variables is not set.

    This function is automatically called on import and can be called whenever the environment
    variables have been changed, e.g. in unit tests.
    """

    global _env

    for name in MANDATORY_ENVIRONMENT_VARIABLES:
        try:
            _env.set(name, os.environ[name])
        except KeyError:
            warnings.warn(
                f"The environment variable {name} is not set. {name} is required to define the project settings and "
                f"environment variables. Please set the environment variable {name} before proceeding."
            )
            _env.set(name, NoValue())

    project = _env.get("PROJECT")

    for gen_var_name in KNOWN_PROJECT_ENVIRONMENT_VARIABLES:
        env_var = f"{project}_{gen_var_name}"
        _env.set(gen_var_name, os.environ.get(env_var, NoValue()))


class _Env:
    """Internal class that keeps track of the environment variables."""

    def __init__(self):
        self._env = {}

    def set(self, key, value):
        self._env[key] = value

    def get(self, key) -> str:
        return self._env.get(key, NoValue())


_env = _Env()


class NoValue:
    """
    Represents a no value object, an environment variable that was not set.

    The truth value of this object is always False, and it is equal to any other NoValue object.
    """

    def __eq__(self, other):
        if isinstance(other, NoValue):
            return True
        return False

    def __bool__(self):
        return False

    def __repr__(self):
        return f"{self.__class__.__name__}"


# The module needs to be initialized before it can be used.
initialize()


def _check_no_value(var_name, value):
    """Raise a ValueError when the value for the variable is NoValue."""
    if value == NoValue():
        project = _env.get("PROJECT")
        env_name = var_name if var_name == "SITE_ID" else f"{project}_{var_name}"
        raise ValueError(
            f"The environment variable {env_name} is not set. "
            f"Please set the environment variable before proceeding."
        )


def get_data_storage_location_env_name() -> str:
    """Returns the name of the environment variable for the project."""
    project = _env.get("PROJECT")
    return f"{project}_DATA_STORAGE_LOCATION"


def set_data_storage_location(location: str | Path):
    """
    Sets the environment variable and the internal representation to the given value.

    Warnings:
        Issues a warning when the given location doesn't exist.
    """
    env_name = get_data_storage_location_env_name()

    # Check if location exists and is readable
    if not Path(location).exists():
        warnings.warn(
            f"The location you provided for the environment variable {env_name} doesn't exist: {location}."
        )

    os.environ[env_name] = location
    _env.set('DATA_STORAGE_LOCATION', location)


def get_data_storage_location(site_id: str = None) -> str:
    """
    Returns the full path of the data storage location for the given site_id.

    If the site_id is None, it is determined from the environment variable SITE_ID.

    If the ${PROJECT}_DATA_STORAGE_LOCATION environment variable does not end with
    the site_id, the site_id will be appended to the path on return. That means
    the actual data storage location will always be site specific.

    Note: when you specify the `site_id` as an argument, it takes precedence
          over the SITE_ID environment variable.

    Args:
        site_id: the site identifier (to be used instead of the SITE_ID environment variable)

    Returns:
        The full path of data storage location as a string.

    Raises:
        A ValueError when the SITE_ID or the ${PROJECT}_DATA_STORAGE_LOCATION is not set.
    """
    global _env

    site_id = site_id or _env.get("SITE_ID")
    _check_no_value("SITE_ID", site_id)

    data_root = _env.get("DATA_STORAGE_LOCATION")
    _check_no_value("DATA_STORAGE_LOCATION", data_root)

    data_root = data_root.rstrip('/')

    return data_root if data_root.endswith(site_id) else f"{data_root}/{site_id}"


def get_conf_data_location_env_name() -> str:
    """Returns the name of the environment variable for the project."""
    project = _env.get("PROJECT")
    return f"{project}_CONF_DATA_LOCATION"


def set_conf_data_location(location: str | Path):
    """
    Sets the environment variable and the internal representation to the given value.

    Warnings:
        Issues a warning when the given location doesn't exist.
    """

    env_name = get_conf_data_location_env_name()

    # Check if location exists and is readable
    if not Path(location).exists():
        warnings.warn(
            f"The location you provided for the environment variable {env_name} doesn't exist: {location}."
        )

    os.environ[env_name] = location
    _env.set('CONF_DATA_LOCATION', location)


def get_conf_data_location(site_id: str = None) -> str:
    """
    Returns the full path of the location of the configuration data for the Site.

    If the site_id is None, it is determined from the environment variable SITE_ID.

    When the ${PROJECT}_CONF_DATA_LOCATION environment variable is not set, the configuration data
    location will be the ${PROJECT}_DATA_STORAGE_LOCATION + '/conf'.

    Args:
        site_id: the site identifier (to be used instead of the SITE_ID environment variable)

    Returns:
        The full path of location of the configuration data as a string.

    Raises:
        A ValueError when the SITE_ID or the ${PROJECT}_DATA_STORAGE_LOCATION is not set.
    """

    conf_data_root = _env.get("CONF_DATA_LOCATION")

    if not conf_data_root:
        try:
            data_root = get_data_storage_location(site_id=site_id)
        except ValueError:
            raise ValueError(
                f"Could not determine the location of the configuration files. "
                f"The environment variable {get_conf_data_location_env_name()} is not set and also the "
                f"data storage location is unknown."
            )

        data_root = data_root.rstrip('/')
        conf_data_root = f"{data_root}/conf"

    return conf_data_root


def get_log_file_location_env_name():
    """Returns the name of the environment variable for the project."""
    project = _env.get("PROJECT")
    return f"{project}_LOG_FILE_LOCATION"


def set_log_file_location(location: str | Path):
    """
    Sets the environment variable and the internal representation to the given value.

    Warnings:
        Issues a warning when the given location doesn't exist.
    """

    env_name = get_log_file_location_env_name()

    # Check if location exists and is readable
    if not Path(location).exists():
        warnings.warn(
            f"The location you provided for the environment variable {env_name} doesn't exist: {location}."
        )

    os.environ[env_name] = location
    _env.set('LOG_FILE_LOCATION', location)


def get_log_file_location(site_id: str = None) -> str:
    """
    Returns the full path of the location of the log files. The log file location is read from the environment
    variable ${PROJECT}_LOG_FILE_LOCATION. The location shall be independent of any setting that is subject to change.

    If the environment variable is not set, a default log file location is created from the data storage location as
    follows: <PROJECT>_DATA_STORAGE_LOCATION/<SITE_ID>/log.

    Args:
        site_id: the site identifier

    Returns:
        The full path of location of the log files as a string.

    Raises:
        A ValueError when the SITE_ID or the ${PROJECT}_DATA_STORAGE_LOCATION is not set.

    """

    log_data_root = _env.get("LOG_FILE_LOCATION")

    if not log_data_root:
        try:
            data_root = get_data_storage_location(site_id=site_id)
        except ValueError:
            raise ValueError(
                f"Could not determine the location of the log files. "
                f"The environment variable {get_log_file_location_env_name()} is not set and also the "
                f"data storage location is unknown."
            )
        data_root = data_root.rstrip('/')
        log_data_root = f"{data_root}/log"

    return log_data_root


def get_local_settings_env_name() -> str:
    """Returns the name of the environment variable for the project."""
    project = _env.get("PROJECT")
    return f"{project}_LOCAL_SETTINGS"


def set_local_settings(path: str | Path):
    """
    Sets the environment variable and the internal representation to the given value.

    Warnings:
        Issues a warning when the given path doesn't exist.
    """

    env_name = get_local_settings_env_name()

    # Check if location exists and is readable
    if not Path(path).exists():
        warnings.warn(
            f"The location you provided for the environment variable {env_name} doesn't exist: {path}."
        )

    os.environ[env_name] = path
    _env.set('LOCAL_SETTINGS', path)


def get_local_settings() -> str:
    """Returns the fully qualified filename of the local settings YAML file."""

    local_settings = _env.get("LOCAL_SETTINGS")

    if local_settings and not Path(local_settings).exists():
        warnings.warn(
            f"The local settings '{local_settings}' doesn't exist. As a result, "
            f"the local settings for your project will not be loaded."
        )

    return local_settings or None


def get_conf_repo_location_env_name() -> str:
    """Returns the name of the environment variable for the project."""
    project = _env.get("PROJECT")
    return f"{project}_CONF_REPO_LOCATION"


def get_conf_repo_location() -> str:
    """Returns the fully qualified name of the location of the repository with configuration and calibration data."""

    location = _env.get("CONF_REPO_LOCATION")

    if location and not Path(location).exists():
        warnings.warn(f"The location of the configuration data repository doesn't exist: {location}.")

    return location or None


def set_conf_repo_location(location: str):
    """
    Sets the environment variable and the internal representation to the given value.

    Warnings:
        Issues a warning when the given location doesn't exist.
    """

    env_name = get_conf_repo_location_env_name()

    # Check if location exists and is readable
    if not Path(location).exists():
        warnings.warn(
            f"The location you provided for the environment variable {env_name} doesn't exist: {location}."
        )

    os.environ[env_name] = location
    _env.set('CONF_REPO_LOCATION', location)


ignore_m_warning('egse.env')


def main(args: list | None = None):  # pragma: no cover

    import argparse
    import sys
    import rich

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        default=False,
        action="store_true",
        help="Print a full report on environment variables and paths.",
    )
    parser.add_argument(
        "--doc",
        default=False,
        action="store_true",
        help="Print help on the environment variables and paths.",
    )

    args = parser.parse_args(args or [])

    def check_env_dir(env_var: str):

        value = _env.get(env_var)

        if value == NoValue():
            value = "[bold red]not set"
        elif not value.startswith('/'):
            value = f"[default]{value} [bold orange3](this is a relative path!)"
        elif not os.path.exists(value):
            value = f"[default]{value} [bold red](location doesn't exist!)"
        elif not os.path.isdir(value):
            value = f"[default]{value} [bold red](location is not a directory!)"
        else:
            value = f"[default]{value}"
        return value

    def check_env_file(env_var: str):

        value = _env.get(env_var)

        if not value:
            value = "[bold red]not set"
        elif not os.path.exists(value):
            value = f"[default]{value} [bold red](location doesn't exist!)"
        else:
            value = f"[default]{value}"
        return value

    rich.print("Environment variables:")

    project = _env.get("PROJECT")

    for var in MANDATORY_ENVIRONMENT_VARIABLES:
        rich.print(f"    {var} = {_env.get(var)}")
    for var in KNOWN_PROJECT_ENVIRONMENT_VARIABLES:
        if var.endswith("_SETTINGS"):
            rich.print(f"    {project}_{var} = {check_env_file(var)}")
        else:
            rich.print(f"    {project}_{var} = {check_env_dir(var)}")

    rich.print()
    rich.print("Generated locations and filenames")

    with all_logging_disabled():
        warnings.filterwarnings("ignore", category=UserWarning)
        try:
            rich.print(f"    {get_data_storage_location() = }", flush=True)
            location = get_data_storage_location()
            if not Path(location).exists():
                rich.print("[red]ERROR: The generated data storage location doesn't exist![/]")
        except ValueError as exc:
            rich.print(f"    get_data_storage_location() = [red]{exc}[/]")

        try:
            rich.print(f"    {get_conf_data_location() = }", flush=True)
            location = get_conf_data_location()
            if not Path(location).exists():
                rich.print("[red]ERROR: The generated configuration data location doesn't exist![/]")
        except ValueError as exc:
            rich.print(f"    get_conf_data_location() = [red]{exc}[/]")

        try:
            rich.print(f"    {get_log_file_location() = }", flush=True)
            location = get_log_file_location()
            if not Path(location).exists():
                rich.print("[red]ERROR: The generated log files location doesn't exist![/]")
        except ValueError as exc:
            rich.print(f"    get_log_file_location() = [red]{exc}[/]")

        try:
            rich.print(f"    {get_local_settings() = }", flush=True)
            location = get_local_settings()
            if location is None or not Path(location).exists():
                rich.print("[red]ERROR: The local settings file doesn't exist![/]")
        except ValueError as exc:
            rich.print(f"    get_local_settings() = [red]{exc}[/]")

    if args.full:
        rich.print()
        rich.print(f"    PYTHONPATH=[default]{os.environ.get('PYTHONPATH')}")
        rich.print(f"    PYTHONSTARTUP=[default]{os.environ.get('PYTHONSTARTUP')}")
        rich.print()
        python_path_msg = "\n      ".join(sys.path)
        rich.print(f"    sys.path=[\n      {python_path_msg}\n    ]")
        path_msg = "\n      ".join(os.environ.get("PATH").split(":"))
        rich.print(f"    PATH=[\n      {path_msg}\n    ]")

    help_msg = """
[bold]PROJECT_INSTALL_LOCATION[/bold]:
    This variable shall point to the location where the CGSE will be installed and is
    usually set to `/cgse`. The variable is used by the [blue]update_cgse[/blue] script.

[bold]PROJECT_CONF_DATA_LOCATION[/bold]:
    This directory is the root folder for all the Setups of the site, the site is part
    of the name. By default, this directory is located in the overall data storage folder.

[bold]PROJECT_CONF_REPO_LOCATION[/bold]:
    This variable is the root of the working copy of the 'plato-cgse-conf' project.
    The value is usually set to `~/git/plato-cgse-conf`.

[bold]PROJECT_DATA_STORAGE_LOCATION[/bold]:
    This directory contains all the data files from the control servers and other
    components. This folder is the root folder for all data from all cameras and
    all sites. Below this folder shall be a folder for each of the cameras and in
    there a sub-folder for each of the sites where that camera was tested. The
    hierarchy is therefore: `$PLATO_DATA_STORAGE_LOCATION/<camera name>/<site id>.
    Each of those folder shall contain at least the sub-folder [blue]daily[/blue], and [blue]obs[/blue].

    There is also a file called [blue]obsid-table-<site id>.txt[/blue] which is maintained by
    the configuration manager and contains information about the observations that
    were run and the commands to start those observation.

[bold]PROJECT_LOG_FILE_LOCATION[/bold]:
    This directory contains the log files with all messages that were sent to the
    logger control server. The log files are rotated on a daily basis at midnight UTC.
    By default, this directory is also located in the overall data storage folder.

[bold]PROJECT_LOCAL_SETTINGS[/bold]:
    This file is used for local site-specific settings. When the environment
    variable is not set, no local settings will be loaded. By default, this variable
    is assumed to be '/cgse/local_settings.yaml'.
"""

    if args.doc:
        rich.print(help_msg)

    if not args.full:
        rich.print()
        rich.print("use the '--full' flag to get a more detailed report, '--doc' for help on the variables.")

    # Do we still use these environment variables?
    #
    # PLATO_WORKDIR
    # PLATO_COMMON_EGSE_PATH - YES


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
