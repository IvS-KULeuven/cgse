"""
This module provides functionality to work with and check your Python environment.
"""
from pathlib import Path

from egse.system import all_logging_disabled
from egse.system import ignore_m_warning

ENV_PLATO_COMMON_EGSE = "PLATO_COMMON_EGSE_PATH"
ENV_PLATO_INSTALL = "PLATO_INSTALL_LOCATION"
ENV_PLATO_CONF_DATA = "PLATO_CONF_DATA_LOCATION"
ENV_PLATO_CONF_REPO = "PLATO_CONF_REPO_LOCATION"
ENV_PLATO_STORAGE_DATA = "PLATO_DATA_STORAGE_LOCATION"
ENV_PLATO_LOG_DATA = "PLATO_LOG_FILE_LOCATION"
ENV_PLATO_LOCAL_SETTINGS = "PLATO_LOCAL_SETTINGS"

PLATO_ENV_VARIABLES = [globals()[x] for x in globals() if x.startswith('ENV_PLATO_')]

__all__ = [
    "get_data_storage_location",
    "get_conf_data_location",
    "get_log_file_location",
    *PLATO_ENV_VARIABLES
]


def get_data_storage_location(setup=None, site_id: str = None) -> str:
    """
    Returns the full path of the data storage location for the Site as
    in the given Setup. If the Setup is not given, it is requested from the
    configuration manager unless the `site_id` argument is given.

    Note: when you specify the `site_id` as an argument, it takes precedence
          over the site_id that is specified in the Setup.

    Args:
        setup: the Setup from which the Camera name and Site ID are taken
        site_id: the site identifier (to be used instead of the site_id in the Setup)

    Returns:
        The full path of data storage location as a string.

    Raises:
        A ValueError when no Setup can be loaded.
    """

    # FIXME: this should be made independent of PLATO, maybe use CGSE_STORAGE_LOCATION as environment variable.

    # FIXME: use CGSE_SITE_ID if Setup can not be determined.

    import os

    if site_id is None:

        from egse.setup import Setup
        from egse.state import GlobalState
        setup: Setup = setup or GlobalState.setup

        if setup is None:
            raise ValueError(
                "Could not determine Setup, which is None, even after loading from the configuration manager."
            )

        site = setup.site_id
    else:
        site = site_id

    data_root = os.environ[ENV_PLATO_STORAGE_DATA]
    data_root = data_root.rstrip('/')

    return data_root if data_root.endswith(site) else f"{data_root}/{site}"


def get_conf_data_location(setup=None) -> str:
    """
    Returns the full path of the location of the Setups for the Site.
    If the Setup is not given, it is requested from the configuration manager.

    Args:
        setup: the Setup from which the Camera name and Site ID are taken

    Returns:
        The full path of location of the Setups as a string.

    Raises:
        A ValueError when no Setup can be loaded.
    """

    data_root = get_data_storage_location(setup=setup)

    return f"{data_root}/conf"


def get_log_file_location() -> str:
    """
    Returns the full path of the location of the log files. The log file location is read from the environment
    variable PLATO_LOG_FILE_LOCATION. The location shall be independent of the Setup, Camera ID or any other
    setting that is subject to change.

    If the environment variable is not set, a default log file location is created from the data storage location as
    follows: $PLATO_DATA_STORAGE_LOCATION/<SITE_ID>/log.

    Returns:
        The full path of location of the log files as a string.
    """

    # FIXME: this should be made independent of PLATO, maybe put the log file in the cwd unless an environment
    #        variable CGSE_LOG_FILE_LOCATION is defined and the location exists and is writable.

    import os

    try:
        log_data_root = os.environ[ENV_PLATO_LOG_DATA]
    except KeyError:
        data_root = os.environ[ENV_PLATO_STORAGE_DATA]
        data_root = data_root.rstrip('/')

        from egse.settings import get_site_id
        site = get_site_id()

        log_data_root = f"{data_root}/{site}/log"

    return log_data_root


ignore_m_warning('egse.env')

if __name__ == "__main__":

    import argparse
    import os
    import sys
    import rich

    from egse.config import get_common_egse_root

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

    args = parser.parse_args()

    def check_env_dir(env_var: str):

        value = os.environ.get(env_var)

        if value is None:
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

        value = os.environ.get(env_var)

        if value is None:
            value = "[bold red]not set"
        elif not os.path.exists(value):
            value = f"[default]{value} [bold red](location doesn't exist!)"
        else:
            value = f"[default]{value}"
        return value

    rich.print("Environment variables:")

    for var in PLATO_ENV_VARIABLES:
        if var.endswith("_SETTINGS"):
            rich.print(f"    {var} = {check_env_file(var)}")
        else:
            rich.print(f"    {var} = {check_env_dir(var)}")

    rich.print()
    rich.print("Generated locations and filenames")

    with all_logging_disabled():
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

    if args.full:
        rich.print()
        rich.print(f"    PYTHONPATH=[default]{os.environ.get('PYTHONPATH')}")
        rich.print(f"    PYTHONSTARTUP=[default]{os.environ.get('PYTHONSTARTUP')}")
        rich.print()
        python_path_msg = "\n      ".join(sys.path)
        rich.print(f"    sys.path=[\n      {python_path_msg}\n    ]")
        path_msg = "\n      ".join(os.environ.get("PATH").split(":"))
        rich.print(f"    PATH=[\n      {path_msg}\n    ]")

    help_msg = f"""
[bold]{ENV_PLATO_COMMON_EGSE}[/bold]:
    This variable should point to the root of the working copy of the 'plato-common-egse' 
    project. Its value is usually '~/git/plato-common-egse' which is considered the default 
    location.

[bold]{ENV_PLATO_INSTALL}[/bold]:
    This variable shall point to the location where the CGSE will be installed and is 
    usually set to `/cgse`. The variable is used by the [blue]update_cgse[/blue] script.

[bold]{ENV_PLATO_CONF_DATA}[/bold]:
    This directory is the root folder for all the Setups of the site, the site is part
    of the name. By default, this directory is located in the overall data storage folder.

[bold]{ENV_PLATO_CONF_REPO}[/bold]:
    This variable is the root of the working copy of the 'plato-cgse-conf' project. 
    The value is usually set to `~/git/plato-cgse-conf`.

[bold]{ENV_PLATO_STORAGE_DATA}[/bold]:
    This directory contains all the data files from the control servers and other
    components. This folder is the root folder for all data from all cameras and 
    all sites. Below this folder shall be a folder for each of the cameras and in 
    there a sub-folder for each of the sites where that camera was tested. The 
    hierarchy is therefore: `$PLATO_DATA_STORAGE_LOCATION/<camera name>/<site id>.
    Each of those folder shall contain at least the sub-folder [blue]daily[/blue], and [blue]obs[/blue]. 
    
    There is also a file called [blue]obsid-table-<site id>.txt[/blue] which is maintained by 
    the configuration manager and contains information about the observations that
    were run and the commands to start those observation.

[bold]{ENV_PLATO_LOG_DATA}[/bold]:
    This directory contains the log files with all messages that were sent to the 
    logger control server. The log files are rotated on a daily basis at midnight UTC.
    By default, this directory is also located in the overall data storage folder.

[bold]{ENV_PLATO_LOCAL_SETTINGS}[/bold]:
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
