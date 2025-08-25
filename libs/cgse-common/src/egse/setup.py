"""
# Setup

This module defines the Setup, which contains the complete configuration information for a test.

The Setup class contains all configuration items that are specific for a test or observation
and is normally (during nominal operation/testing) loaded automatically from the configuration
manager. The Setup includes type and identification of hardware that is used, calibration files,
software versions, reference frames and coordinate systems that link positions of alignment
equipment, conversion functions for temperature sensors, etc.

The configuration information that is in the Setup can be navigated in two different ways. First,
the Setup is a dictionary, so all information can be accessed by keys as in the following example.

    >>> setup = Setup({"gse": {"hexapod": {"ID": 42, "calibration": [0,1,2,3,4,5]}}})
    >>> setup["gse"]["hexapod"]["ID"]
    42

Second, each of the _keys_ is also available as an attribute of the Setup and that makes it
possible to navigate the Setup with dot-notation:

    >>> id = setup.gse.hexapod.ID

In the above example you can see how to navigate from the setup to a device like the PUNA Hexapod.
The Hexapod device is connected to the control server and accepts commands as usual.

If you want to know which keys you can use to navigate the Setup, use the `keys()` method.

    >>> setup.gse.hexapod.keys()
    dict_keys(['ID', 'calibration'])
    >>> setup.gse.hexapod.calibration
    [0, 1, 2, 3, 4, 5]

To get a full printout of the Setup, you can use the `rich` package and print the Setup. Be careful, because
this can print out a lot of information when a full Setup is loaded.

    >>> from rich import print
    >>> print(setup)
    Setup
    └── gse
        └── hexapod
            ├── ID: 42
            └── calibration: [0, 1, 2, 3, 4, 5]

### Special Values

Some of the information in the Setup is interpreted in a special way, i.e. some values are
processed before returning. Examples are the device classes and calibration/data files. The
following values are treated special if they start with:

* `class//`: instantiate the class and return the object
* `factory//`: instantiates a factory and executes its `create()` method
* `csv//`: load the CSV file and return a numpy array
* `yaml//`: load the YAML file and return a dictionary
* `pandas//`: load a CSV file into a pandas Dataframe
* `int-enum//`: dynamically create the enumeration and return the Enum object

#### Device Classes

Most of the hardware components in the Setup will have a `device` key that defines the class for
the device controller. The `device` keys have a value that starts with `class//` and it will
return the device object. As an example, the following defines the Hexapod device:

    >>> setup = Setup(
    ...   {
    ...     "gse": {
    ...       "hexapod": {"ID": 42, "device": "class//egse.hexapod.symetrie.puna.PunaSimulator"}
    ...     }
    ...   }
    ... )
    >>> setup.gse.hexapod.device.is_homing_done()
    False
    >>> setup.gse.hexapod.device.info()
    'Info about the PunaSimulator...'

In the above example you see that we can call the `is_homing_done()` and `info()` methodes
directly on the device by navigating the Setup. It would however be better (more performant) to
put the device object in a variable and work with that variable:

    >>> hexapod = setup.gse.hexapod.device
    >>> hexapod.homing()
    >>> hexapod.is_homing_done()
    True
    >>> hexapod.get_user_positions()

If you need, for some reason, to have access to the actual raw value of the hexapod device key,
use the `get_raw_value()` method:

    >>> setup.gse.hexapod.get_raw_value("device")
    <egse.hexapod.symetrie.puna.PunaSimulator object at ...

#### Data Files

Some information is too large to add to the Setup as such and should be loaded from a data file.
Examples are calibration files, flat-fields, temperature conversion curves, etc.

The Setup will automatically load the file when you access a key that contains a value that
starts with `csv//` or `yaml//`.

    >>> setup = Setup({
    ...     "instrument": {"coeff": "csv//cal_coeff_1234.csv"}
    ... })
    >>> setup.instrument.coeff[0, 4]
    5.0

Note: the resource location is always relative to the path defined by the *PROJECT*_CONF_DATA_LOCATION
environment variable.

The Setup inherits from a NavigableDict (aka navdict) which is also defined in this module.

---

"""

from __future__ import annotations

__all__ = [
    "Setup",
    "setup_ctx",
    "navdict",  # noqa: ignore typo
    "list_setups",
    "load_setup_from_disk",
    "load_setup",
    "get_setup",
    "submit_setup_to_disk",
    "submit_setup",
    "SetupError",
    "load_last_setup_id",
    "save_last_setup_id",
]

import re
import textwrap
import warnings
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Optional
from typing import Protocol
from typing import Union
from typing import runtime_checkable

import rich
from navdict import navdict
from navdict.directive import register_directive
from navdict.navdict import NavigableDict
from navdict.navdict import get_resource_location
from rich.tree import Tree

from egse.env import get_conf_data_location
from egse.env import get_conf_repo_location
from egse.env import get_conf_repo_location_env_name
from egse.env import get_data_storage_location
from egse.env import get_site_id
from egse.env import has_conf_repo_location
from egse.env import print_env
from egse.log import logger
from egse.plugin import HierarchicalEntryPoints
from egse.system import format_datetime
from egse.system import sanity_check


setup_ctx: ContextVar[Setup | None] = ContextVar("setup", default=None)


class SetupError(Exception):
    """A setup-specific error."""


# This is a replacement of the standard load_csv() function from the navdict package.
def _load_csv(value: str, parent_location: Path | None, *args, **kwargs):
    """Find and return the content of a CSV file."""
    from numpy import genfromtxt

    parts = value.rsplit("/", 1)
    [in_dir, fn] = parts if len(parts) > 1 else [None, parts[0]]

    csv_location = get_resource_location(parent_location, in_dir)

    try:
        content = genfromtxt(csv_location / fn, delimiter=",", skip_header=1)
    except FileNotFoundError as exc:
        raise ValueError(f"Resource file not found: {value} in {csv_location}")
    except TypeError as exc:
        raise ValueError(f"Couldn't load resource '{value}' from {csv_location}") from exc
    return content


def _load_pandas(value: str, parent_location: Path | None, *args, **kwargs):
    """
    Find and return the content of the given file as a pandas DataFrame object.

    The file is loaded relative from the location of the configuration data
    as defined by `get_conf_data_location()`.

    Args:
        - resource_name: Filename, preceded by "pandas//".
        - separator: Column separator.
    """
    import pandas

    parts = value.rsplit("/", 1)
    [in_dir, fn] = parts if len(parts) > 1 else [None, parts[0]]

    pandas_file_location = get_resource_location(parent_location, in_dir)

    try:
        separator = kwargs["separator"]
    except KeyError:
        separator = ","

    try:
        return pandas.read_csv(pandas_file_location / fn, sep=separator)
    except FileNotFoundError as exc:
        raise ValueError(f"Resource file not found: {value} in {pandas_file_location}")
    except TypeError as exc:
        raise ValueError(f"Couldn't load resource '{value}' from {pandas_file_location}") from exc


def _get_attribute(self, name, default):
    try:
        attr = object.__getattribute__(self, name)
    except AttributeError:
        attr = default
    return attr


def _parse_filename_for_setup_id(filename: str) -> str | None:
    """Returns the setup_id from the filename, or None when no match was found."""

    # match = re.search(r"SETUP_([^_]+)_(\d+)", filename)
    match = re.search(r"SETUP_(\w+)_([\d]{5})_([\d]{6})_([\d]{6})\.yaml", filename)

    # TypeError when match is None

    try:
        return match[2]  # match[2] is setup_id
    except (IndexError, TypeError):
        return None


def disentangle_filename(filename: str) -> tuple:
    """
    Returns the site_id and setup_id (as a tuple) that is extracted from the Setups filename.

    Args:
        filename (str): the filename or fully qualified file path as a string.

    Returns:
        A tuple (site_id, setup_id).
    """
    if filename is None:
        return ()

    match = re.search(r"SETUP_(\w+)_([\d]{5})_([\d]{6})_([\d]{6})\.yaml", filename)

    if match is None:
        return ()

    site_id, setup_id = match[1], match[2]

    return site_id, setup_id


def get_last_setup_id_file_path(site_id: str = None) -> Path:
    """
    Return the fully expanded file path of the file containing the last loaded Setup in the configuration manager.
    The default location for this file is the data storage location.

    Args:
        site_id: The SITE identifier (overrides the SITE_ID environment variable)

    """
    location = get_data_storage_location(site_id=site_id)

    return Path(location).expanduser().resolve() / "last_setup_id.txt"


def load_last_setup_id(site_id: str = None) -> int:
    """
    Returns the ID of the last Setup that was used by the configuration manager.
    The file shall only contain the Setup ID which must be an integer on the first line of the file.
    If no such ID can be found, the Setup ID = 0 will be returned.

    Args:
        site_id: The SITE identifier
    """

    last_setup_id_file_path = get_last_setup_id_file_path(site_id=site_id)
    try:
        with last_setup_id_file_path.open("r") as fd:
            setup_id = int(fd.read().strip())
    except FileNotFoundError:
        setup_id = 0
        save_last_setup_id(setup_id)

    return setup_id


def save_last_setup_id(setup_id: int | str, site_id: str = None):
    """
    Makes the given Setup ID persistent, so it can be restored upon the next startup.

    Args:
        setup_id: The Setup identifier to be saved
        site_id: The SITE identifier

    """

    last_setup_id_file_path = get_last_setup_id_file_path(site_id=site_id)
    with last_setup_id_file_path.open("w") as fd:
        fd.write(f"{int(setup_id):d}")


# Replace the default navdict `csv//` directive with one that uses numpy and returns a numpy array
register_directive("csv", _load_csv)

# Register the navdict `pandas//` directive
register_directive("pandas", _load_pandas)


class Setup(NavigableDict):
    """The Setup class represents a version of the configuration of the test facility, the
    test setup and the Camera Under Test (CUT)."""

    def __init__(self, nav_dict: NavigableDict | dict = None, label: str = None):
        try:
            _filename = nav_dict.get_private_attribute("_filename")
        except AttributeError:
            _filename = None
        super().__init__(nav_dict or {}, label=label, _filename=_filename)
        try:
            setup_id = nav_dict.get_private_attribute("_setup_id")
            self.set_private_attribute("_setup_id", setup_id)
        except AttributeError:
            pass

    @staticmethod
    def from_yaml_string(yaml_content: str = None) -> Setup:
        """Loads a Setup from the given YAML string.

        This method is mainly used for easy creation of Setups from strings during unit tests.

        Args:
            yaml_content (str): a string containing YAML

        Returns:
            a Setup that was loaded from the content of the given string.
        """

        if not yaml_content:
            raise ValueError("Invalid argument to function: No input string or None given.")

        setup_dict = navdict.from_yaml_string(yaml_content)

        if "Setup" in setup_dict:
            setup_dict = setup_dict["Setup"]

        return Setup(setup_dict, label="Setup")

    @staticmethod
    @lru_cache(maxsize=300)
    def from_yaml_file(filename: Union[str, Path] = None) -> Setup:
        """Loads a Setup from the given YAML file.

        Args:
            filename (str): the path of the YAML file to be loaded

        Returns:
            a Setup that was loaded from the given location.

        Raises:
            ValueError: when no filename is given.
        """

        setup_navdict = navdict.from_yaml_file(filename)

        try:
            setup_navdict = setup_navdict["Setup"]
        except KeyError:
            warnings.warn(f"Setup file doesn't have a top-level 'Setup' group: {filename!s}")

        if setup_id := _parse_filename_for_setup_id(str(filename)):
            setup_navdict.set_private_attribute("_setup_id", setup_id)

        setup = Setup(setup_navdict, label="Setup")

        return setup

    def to_yaml_file(self, filename: str | Path | None = None, header: str = None, top_level_group: str = None) -> None:
        """Saves a Setup to a YAML file.

        When no filename is provided, this method will look for a 'private' attribute
        `_filename` and use that to save the data.

        Args:
            filename (str|Path): the path of the YAML file where to save the data

        Note:
            This method will **overwrite** the original or given YAML file and therefore you might
            lose proper formatting and/or comments.

        """

        header = textwrap.dedent(
            f"""
            # This Setup file is generated by:
            #
            #    Setup.to_yaml_file(setup, filename="{filename}')
            #
            # Created on {format_datetime()}

            """
        )

        super().to_yaml_file(filename, header, "Setup")

    @staticmethod
    def compare(setup_1: NavigableDict, setup_2: NavigableDict):
        from egse.device import DeviceInterface
        from deepdiff import DeepDiff

        return DeepDiff(setup_1, setup_2, exclude_types=[DeviceInterface])

    @staticmethod
    def find_devices(node: NavigableDict, devices: dict = None) -> dict[str, tuple[str, str, tuple]]:
        """Returns a dictionary with the devices that are included in the setup.

        The keys in the dictionary are taken from the "device_name" entries in the setup file. The corresponding values
        in the dictionary are taken from the "device" entries in the setup file.

        Args:
            node: Dictionary in which to look for the devices (and their names).
            devices: Dictionary in which to include the devices in the setup.

        Returns: Dictionary with the devices that are included in the setup. The keys are the device name, the values
                 are tuples with the 'device' raw value and the device arguments as a tuple.
        """

        devices = devices or {}

        for sub_node in node.values():
            if isinstance(sub_node, NavigableDict):
                if ("device" in sub_node) and ("device_name" in sub_node):
                    device = sub_node.get_raw_value("device")

                    if "device_id" in sub_node:
                        device_id = sub_node.get_raw_value("device_id")
                    else:
                        device_id = None

                    if "device_args" in sub_node:
                        device_args = sub_node.get_raw_value("device_args")
                    else:
                        device_args = ()

                    devices[sub_node["device_name"]] = (device, device_id, device_args)

                else:
                    devices = Setup.find_devices(sub_node, devices=devices)

        return devices

    @staticmethod
    def find_device_ids(node: NavigableDict, device_ids: dict = None) -> dict:
        """Returns a list of identifiers of the devices that are included in the setup.

        Args:
            node: Dictionary in which to look for the device identifiers.
            device_ids: List in which to include the devices in the setup.

        Returns: List with the identifiers of the devices that are included in the given dictionary.
        """

        device_ids = device_ids or {}

        for sub_node in node.values():
            if isinstance(sub_node, NavigableDict):
                if ("device" in sub_node) and ("device_id" in sub_node) and ("device_name" in sub_node):
                    # device_ids[sub_node.get_raw_value("device_id")] = sub_node.get_raw_value("device_name")

                    device_proxy = sub_node.get_raw_value("device")
                    if "device_args" in sub_node:
                        device_args = sub_node.get_raw_value("device_args")
                    else:
                        device_args = ()

                    device_ids[sub_node.get_raw_value("device_id")] = (
                        sub_node.get_raw_value("device_name"),
                        device_proxy,
                        device_args,
                    )
                    # device_ids.append((sub_node.get_raw_value("device_id"), sub_node.get_raw_value("device_name")))
                else:
                    device_ids = Setup.find_device_ids(sub_node, device_ids=device_ids)

        return device_ids

    @staticmethod
    def walk(node: dict, key_of_interest: str, leaf_list: list) -> list:
        """
        Walk through the given dictionary, in a recursive way, appending the leaf with
        the given keyword to the given list.

        Args:
            node: Dictionary in which to look for leaves with the given keyword.
            key_of_interest: Key to look for in the leaves of the given dictionary.
            leaf_list: List to which to add the leaves with the given keyword.

        Returns:
            Given list with the leaves (with the given keyword) in the given dictionary \
            appended to it.
        """

        for key, sub_node in node.items():
            if isinstance(sub_node, dict):
                Setup.walk(sub_node, key_of_interest, leaf_list)

            elif key == key_of_interest:
                leaf_list.append(sub_node)

        return leaf_list

    def __rich__(self) -> Tree:
        tree = super().__rich__()
        if self.has_private_attribute("_setup_id"):
            setup_id = self.get_private_attribute("_setup_id")
            tree.add(f"Setup ID: {setup_id}", style="grey50")
        if self.has_private_attribute("_filename"):
            filename = self.get_private_attribute("_filename")
            tree.add(f"Loaded from: {filename}", style="grey50")
        return tree

    def get_id(self) -> Optional[str]:
        """Returns the Setup ID (as a string) or None when no setup id could be identified."""
        if self.has_private_attribute("_setup_id"):
            return self.get_private_attribute("_setup_id")
        else:
            return None

    def get_filename(self) -> Optional[str]:
        """Returns the filename for this Setup or None when no filename could be determined."""
        if self.has_private_attribute("_filename"):
            return self.get_private_attribute("_filename")
        else:
            return None


def list_setups(**attr):
    """
    This is a function to be used for interactive use, it will print to the terminal (stdout) a
    list of Setups known at the Configuration Manager. This list is sorted with the most recent (
    highest) value last.

    The list can be restricted with key:value pairs (keyword arguments). This _search_ mechanism
    allows us to find all Setups that adhere to the key:value pairs, e.g. to find all Setups for
    CSL at position 2, use:

        >>> list_setups(site_id="CSL", position=2)

    To have a nested keyword search (i.e. search by `gse.hexapod.ID`) then pass in
    `gse__hexapod__ID` as the keyword argument. Replace the '.' notation with double underscores
    '__'.

        >>> list_setups(gse__hexapod__ID=4)
    """

    try:
        from egse.confman import ConfigurationManagerProxy
    except ImportError:
        print("WARNING: package 'cgse-core' is not installed, service not available.")
        return

    try:
        with ConfigurationManagerProxy() as proxy:
            setups = proxy.list_setups(**attr)
        if setups:
            # We want to have the most recent (highest id number) last, but keep the site together
            setups = sorted(setups, key=lambda x: (x[1], x[0]))
            print("\n".join(f"{setup}" for setup in setups))
        else:
            print("no Setups found")
    except ConnectionError:
        print("Could not make a connection with the Configuration Manager, no Setup to show you.")


def get_setup(setup_id: int = None) -> Setup | None:
    """
    Retrieve the currently active Setup from the configuration manager.

    When a setup_id is provided, that setup will be returned, but not loaded in the configuration
    manager. This function does NOT change the configuration manager.

    This function is for interactive use and consults the configuration manager server. Don't use
    this within the test script, but use the `GlobalState.setup` property instead.
    """
    try:
        from egse.confman import ConfigurationManagerProxy
    except ImportError:
        print("WARNING: package 'cgse-core' is not installed, service not available.")
        return None

    try:
        with ConfigurationManagerProxy() as proxy:
            setup = proxy.get_setup(setup_id)
        return setup
    except ConnectionError:
        print("Could not make a connection with the Configuration Manager, no Setup returned.")
        return None


def _check_conditions_for_get_path_of_setup_file(site_id: str) -> Path:
    """
    Check some pre-conditions that need to be met before we try to determine the
    file path for the requested Setup file.

    The following checks are performed:

    * if the environment variable '{PROJECT}_CONF_REPO_LOCATION' is set
    * if the directory specified in the env variable actually exists
    * if the folder with the Setups exists for the given site_id

    Args:
        site_id (str): the name of the test house

    Returns:
        The location of the Setup files for the given test house.

    Raises:
        LookupError when the environment variable is not set.

        NotADirectoryError when either the repository folder or the Setups folder doesn't exist.

    """
    repo_location_env = get_conf_repo_location_env_name()

    if not (repo_location := get_conf_repo_location()):
        raise LookupError(
            f"Environment variable doesn't exist or points to an invalid location, please (re-)define"
            f" {repo_location_env} and try again."
        )

    print_env()

    repo_location = Path(repo_location)
    setup_location = repo_location / "data" / site_id / "conf"

    if not repo_location.is_dir():
        raise NotADirectoryError(
            f"The location of the repository for Setup files doesn't exist: {repo_location!s}. "
            f"Please check the environment variable {repo_location_env}."
        )

    if not setup_location.is_dir():
        raise NotADirectoryError(
            f"The location of the Setup files doesn't exist: {setup_location!s}. "
            f"Please check if the given {site_id=} is correct."
        )

    return setup_location


def get_path_of_setup_file(setup_id: int, site_id: str) -> Path:
    """
    Returns the Path to the last Setup file for the given site_id. The last Setup
    file is the file with the largest setup_id number.

    This function needs the environment variable <PROJECT>_CONF_REPO_LOCATION to
    be defined as the location of the repository with configuration data on your
    disk. If the repo is not defined, the configuration data location will be used
    instead.

    Args:
        setup_id (int): the identifier for the requested Setup
        site_id (str): the test house name, one of CSL, SRON, IAS, INTA

    Returns:
        The full path to the requested Setup file.

    Raises:
        LookupError: when the environment variable is not set.

        NotADirectoryError: when either the repository folder or the Setups folder doesn't exist.

        FileNotFoundError: when no Setup file can be found for the given arguments.

    """

    if not has_conf_repo_location():
        setup_location = Path(get_conf_data_location(site_id))
    else:
        setup_location = _check_conditions_for_get_path_of_setup_file(site_id)

    site_id = site_id or get_site_id()

    logger.info(f"{setup_location=}, {setup_id=}, {site_id=}")

    if setup_id is not None and site_id is not None:
        files = list(setup_location.glob(f"SETUP_{site_id}_{setup_id:05d}_*.yaml"))

        if not files:
            raise FileNotFoundError(f"No Setup found for {setup_id=} and {site_id=}.")

        file_path = Path(setup_location) / files[-1]
    else:
        files = setup_location.glob("SETUP*.yaml")

        last_file_parts = sorted([file.name.split("_") for file in files])[-1]
        file_path = Path(setup_location) / "_".join(last_file_parts)

    sanity_check(file_path.is_file(), f"The expected Setup file doesn't exist: {file_path!s}")

    return file_path


def load_setup_from_disk(setup_id: int, **kwargs) -> Setup:
    """
    This function loads the Setup corresponding with the given `setup_id` from your local disk.

    Loading a Setup means:

    * that this Setup will be available from the `GlobalState.setup`

    When no setup_id is provided, the current Setup is loaded from the configuration manager.

    When `from_disk` is True, the Setup will not be loaded from the configuration manager, but it
    will be loaded from disk. No interaction with the configuration manager happens in this case.

    Args:
        setup_id (int): the identifier for the Setup
        site_id (str): the name of the test house

    Returns:
        The requested Setup or None when the Setup could not be loaded from the \
        configuration manager.

    """

    site_id = kwargs.get("site_id") or get_site_id()

    setup_file_path = get_path_of_setup_file(setup_id, site_id)

    if setup_id is None:
        rich.print(f"Loading the latest Setup for {site_id}...")
    else:
        rich.print(f"Loading Setup {setup_id} for {site_id}...")

    return Setup.from_yaml_file(setup_file_path)


def submit_setup_to_disk(setup: Setup, description: str, **kwargs) -> str | None:
    """
    Submit the given Setup to the Configuration Manager.

    When you submit a Setup, the Configuration Manager will save this Setup with the
    next (new) setup id and make this Setup the current Setup in the Configuration manager
    unless you have explicitly set `replace=False` in which case the current Setup will
    not be replaced with the new Setup.

    Args:
        setup (Setup): a (new) Setup to submit to the configuration manager
        description (str): one-liner to help identifying the Setup afterwards

    Returns:
        The Setup ID of the newly created Setup or None.
    """

    rich.print(
        textwrap.dedent(
            f"""\
            Saving setup to disk, a new setup identifier will be assigned. 
            To finalise the submit, reload the setup:

            setup = load_setup() 
            """
        )
    )

    return "00000"


@runtime_checkable
class SetupProvider(Protocol):
    def load_setup(self, setup_id: int, **kwargs) -> Setup | None: ...
    def submit_setup(self, setup: Setup, description: str, **kwargs) -> str | None: ...
    # def list_setups(self): ...
    def can_handle(self, source: str) -> bool: ...


class LocalSetupProvider:
    def load_setup(self, setup_id: int, **kwargs) -> Setup | None:
        logger.info(f"Loading Setup from disk, {setup_id=}, {kwargs=}")
        return load_setup_from_disk(setup_id, **kwargs)

    def submit_setup(self, setup: Setup, description: str, **kwargs) -> str | None:
        logger.info(f"Submitting Setup to disk, {setup=}, {description=}, {kwargs=}")
        return submit_setup_to_disk(setup, description, **kwargs)

    def can_handle(self, source: str):
        return source in ["file", "local"]


def load_setup(setup_id: int = None, **kwargs):
    """
    Loads a Setup.

    Args:
        - setup_id: identifier for the requested Setup
        - site_id:
    """
    setup = _setup_manager.load_setup(setup_id, **kwargs)

    setup_ctx.set(setup)

    return setup


def submit_setup(setup: Setup, description: str, **kwargs) -> str | None:
    return _setup_manager.submit_setup(setup, description, **kwargs)


def main(args: list = None):  # pragma: no cover
    import argparse

    from rich import print

    from egse.config import find_files

    site_id = get_site_id()
    location = get_conf_data_location()
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Print out the Setup for the given setup-id. The Setup will
            be loaded from the location given by the environment variable
            PLATO_CONF_DATA_LOCATION. If this env is not set, the Setup
            will be searched from the current directory."""),
        epilog=f"PLATO_CONF_DATA_LOCATION={location}",
    )
    parser.add_argument(
        "--setup-id", type=int, default=-1, help="the Setup ID. If not given, the last Setup will be selected."
    )
    parser.add_argument("--list", "-l", action="store_true", help="list available Setups.")
    parser.add_argument("--use-cm", action="store_true", help="use the configuration manager.")
    args = parser.parse_args(args or [])

    # if args.use_cm:
    #     try:
    #         from egse.confman import ConfigurationManagerProxy
    #     except ImportError:
    #         print("WARNING: package 'cgse-core' is not installed, service not available.")
    #         return
    #
    #     with ConfigurationManagerProxy() as cm:
    #         if args.list:
    #             print(cm.list_setups())
    #         else:
    #             print(cm.get_setup())
    #     return

    if args.list:
        files = find_files(f"SETUP_{site_id}_*_*.yaml", root=location)
        files = list(files)
        if files:
            location = files[0].parent.resolve()
        print(sorted([f.name for f in files]))
        print(f"Loaded from [purple]{location}.")
    else:
        setup_id = args.setup_id
        if setup_id == -1:
            setup_files = find_files(f"SETUP_{site_id}_*_*.yaml", root=location)
        else:
            setup_files = find_files(f"SETUP_{site_id}_{setup_id:05d}_*.yaml", root=location)
        setup_files = list(setup_files)
        if len(setup_files) > 0:
            setup_file = sorted(setup_files)[-1]
            setup = Setup.from_yaml_file(setup_file)
            print(setup)
        else:
            print("[red]No setup files were found.[/]")


class SetupManager:
    """Unified manager that routes Setup access to appropriate providers.

    Providers are loaded from the `cgse.extension.setup_providers` entrypoints.
    Providers serve different purposes, the default provider accesses Setups from
    your local disk, while other providers might access a Setup through the core
    services or any other way, e.g. from a website API.

    The default provider handles access to Setups locally, from disk, unless the
    `cgse-core` package is installed which provides access to the Setups in the
    configuration manager.
    """

    def __init__(self):
        self._providers: list | None = None
        self._default_source = "local"
        self._discovery_lock = Lock()

    @property
    def providers(self):
        """Lazy provider discovery - only runs when first accessed to prevent circular import problems."""
        if self._providers is None:
            with self._discovery_lock:
                if self._providers is None:  # Double-check locking
                    self._providers = self._discover_providers()
        return self._providers

    def _discover_providers(self):
        """
        Initialise the Setup provider.

        Find and save all 'setup_provider' extensions. The extensions shall adhere to the
        SetupProvider protocol. If a provider can handle 'core-services', that will become
        the default when accessing the Setups, otherwise the default will be 'local'.
        """
        providers = []

        cgse_eps = HierarchicalEntryPoints("cgse.extension")

        for ep in cgse_eps.get_by_subgroup("setup_provider"):
            provider_class = ep.load()
            provider = provider_class()
            if isinstance(provider, SetupProvider):
                providers.append(provider)
                if provider.can_handle("core-services"):
                    self._default_source = "core-services"

        providers.append(LocalSetupProvider())

        return providers

    def set_default_source(self, source: str):
        self._default_source = source

    def load_setup(self, setup_id: int = None, **kwargs):
        source = kwargs.get("source") or self._default_source

        for provider in self.providers:
            if provider.can_handle(source):
                return provider.load_setup(setup_id, **kwargs)

        logger.warning(f"Couldn't find a suitable Setup provider for handling '{source}', using 'local'.")
        return LocalSetupProvider().load_setup(setup_id, **kwargs)

    def submit_setup(self, setup: Setup, description: str, **kwargs):
        source = kwargs.get("source") or self._default_source
        for provider in self.providers:
            if provider.can_handle(source):
                return provider.submit_setup(setup, description, **kwargs)
        logger.warning(f"Couldn't find a suitable Setup provider for handling '{source}', using 'local'.")
        return LocalSetupProvider().submit_setup(setup, description, **kwargs)


_setup_manager = SetupManager()


if __name__ == "__main__":
    # main(sys.argv[1:])
    #
    rich.print(load_setup(site_id=get_site_id()))
