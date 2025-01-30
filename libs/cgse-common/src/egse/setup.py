"""
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

Second, each of the _keys_ is also available as an attribute of the Setup and that make it
possible to navigate the Setup with dot-notation:

    >>> id = setup.gse.hexapod.ID

In the above example you can see how to navigate from the setup to a device like the PUNA Hexapod.
The Hexapod device is connected to the control server and accepts commands as usual. If you want to
know which keys you can use to navigate the Setup, use the `keys()` method.

    >>> setup.gse.hexapod.keys()
    dict_keys(['ID', 'calibration'])
    >>> setup.gse.hexapod.calibration
    [0, 1, 2, 3, 4, 5]

To get a full printout of the Setup, you can use the `pretty_str()` method. Be careful, because
this can print out a lot of information when a full Setup is loaded.

    >>> print(setup)
    gse:
        hexapod:
            ID: 42
            calibration: [0, 1, 2, 3, 4, 5]
    <BLANKLINE>

### Special Values

Some of the information in the Setup is interpreted in a special way, i.e. some values are
processed before returning. Examples are the device classes and calibration/data files. The
following values are treated special if they start with:

* `class//`: instantiate the class and return the object
* `csv//`: load the CSV file and return a numpy array
* `yaml//`: load the YAML file and return a dictionary
* `enum//`: dynamically create the enumeration and return the Enum object

#### Device Classes

Most of the hardware components in the Setup will have a `device` key that defines the class for
the device controller. The `device` keys have a value that starts with `class//` and it will
return the device object. As an example, the following defines the Hexapod device:

    >>> setup = Setup({
    ...     "gse": {
    ...         "hexapod": {"ID": 42, "device": "class//egse.hexapod.symetrie.puna.PunaSimulator"}
    ...     }
    ... })
    >>> setup.gse.hexapod.device.is_homing_done()
    False
    >>> setup.gse.hexapod.device.info()  # doctest: +ELLIPSIS
    'Info about the PunaSimulator...'

In the above example you see that we can call the `is_homing_done()` and `info()` methodes
directly on the device by navigating the Setup. It would however be better (more performant) to
put the device object in a variable and work with that variable:

    >>> hexapod = setup.gse.hexapod.device
    >>> _ = hexapod.homing()
    >>> hexapod.is_homing_done()
    True
    >>> _ = hexapod.get_user_positions()

If you need, for some reason, to have access to the actual raw value of the hexapod device key,
use the `get_raw_value()` method:

    >>> setup.gse.hexapod.get_raw_value("device")  # doctest: +ELLIPSIS
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

Note: the resource location is always relative to the path defined by the PLATO_CONF_DATA_LOCATION
environment variable.

"""

from __future__ import annotations

__all__ = [
    "Setup",
    "navdict",  # noqa: ignore typo
    "list_setups",
    "load_setup",
    "get_setup",
    "submit_setup",
    "SetupError",
    "load_last_setup_id",
    "save_last_setup_id",
]

import enum
import importlib
import logging
import os
import re
import textwrap
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any
from typing import Optional
from typing import Union

import rich
import yaml
from rich.tree import Tree

from egse.env import get_conf_data_location
from egse.env import get_conf_repo_location
from egse.env import get_conf_repo_location_env_name
from egse.env import get_data_storage_location
from egse.env import has_conf_repo_location
from egse.env import print_env
from egse.response import Failure
from egse.settings import read_configuration_file
from egse.system import format_datetime
from egse.system import sanity_check
from egse.system import walk_dict_tree

MODULE_LOGGER = logging.getLogger(__name__)


class SetupError(Exception):
    """ A setup-specific error."""
    pass


def _load_class(class_name: str):
    """
    Find and returns a class based on the fully qualified name.

    A class name can be preceded with the string `class//` or `factory//`. This is used in YAML
    files where the class is then instantiated on load.

    Args:
        class_name (str): a fully qualified name for the class
    """
    if class_name.startswith("class//"):
        class_name = class_name[7:]
    elif class_name.startswith("factory//"):
        class_name = class_name[9:]

    module_name, class_name = class_name.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _load_csv(resource_name: str):
    """Find and return the content of a CSV file."""
    from numpy import genfromtxt  # FIXME: use CSV standard module

    parts = resource_name[5:].rsplit("/", 1)
    [in_dir, fn] = parts if len(parts) > 1 else [None, parts[0]]
    conf_location = get_conf_data_location()
    try:
        csv_location = Path(conf_location) / in_dir / fn
        content = genfromtxt(csv_location, delimiter=",", skip_header=1)
    except TypeError as exc:
        raise ValueError(
            f"Couldn't load resource '{resource_name}' from default {conf_location=}") from exc
    return content


def _load_int_enum(enum_name: str, enum_content):
    """ Dynamically build (and return) and IntEnum.

    Args:
        - enum_name: Enumeration name (potentially prepended with "int_enum//").
        - enum_content: Content of the enumeration, as read from the setup.
    """
    if enum_name.startswith("int_enum//"):
        enum_name = enum_name[10:]

    definition = {}
    for side_name, side_definition in enum_content.items():

        if "alias" in side_definition:
            aliases = side_definition["alias"]
        else:
            aliases = []
        value = side_definition["value"]

        definition[side_name] = value

        for alias in aliases:
            definition[alias] = value
    return enum.IntEnum(enum_name, definition)


def _load_yaml(resource_name: str):
    """Find and return the content of a YAML file."""
    from egse.settings import Settings
    from egse.settings import SettingsError

    parts = resource_name[6:].rsplit("/", 1)
    [in_dir, fn] = parts if len(parts) > 1 else [None, parts[0]]
    conf_location = get_conf_data_location()
    try:
        yaml_location = Path(conf_location) / in_dir
        content = NavigableDict(Settings.load(location=yaml_location, filename=fn, add_local_settings=False))
    except (TypeError, SettingsError) as exc:
        raise ValueError(
            f"Couldn't load resource '{resource_name}' from default {conf_location=}") from exc
    return content


def _load_pandas(resource_name: str, separator: str):
    """
    Find and return the content of the given file as a pandas DataFrame object.

    The file is loaded relative from the location of the configuration data
    as defined by `get_conf_data_location()`.

    Args:
        - resource_name: Filename, preceded by "pandas//".
        - separator: Column separator.
    """
    import pandas

    parts = resource_name[8:].rsplit("/", 1)
    [in_dir, fn] = parts if len(parts) > 1 else [None, parts[0]]
    conf_location = get_conf_data_location()

    try:
        pandas_file_location = Path(conf_location) / in_dir / fn
        return pandas.read_csv(pandas_file_location, sep=separator)
    except TypeError as exc:
        raise ValueError(
            f"Couldn't load resource '{resource_name}' from default {conf_location=}") from exc


def _get_attribute(self, name, default):
    try:
        attr = object.__getattribute__(self, name)
    except AttributeError:
        attr = default
    return attr


def _parse_filename_for_setup_id(filename: str):
    """Returns the setup_id from the filename, or None when no match was found."""

    # match = re.search(r"SETUP_([^_]+)_(\d+)", filename)
    match = re.search(r"SETUP_(\w+)_([\d]{5})_([\d]{6})_([\d]{6})\.yaml", filename)

    # TypeError when match is None

    try:
        return match[2]  # match[2] is setup_id
    except (IndexError, TypeError):
        return None


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
        with last_setup_id_file_path.open('r') as fd:
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
    with last_setup_id_file_path.open('w') as fd:
        fd.write(f"{int(setup_id):d}")


class NavigableDict(dict):
    """
    A NavigableDict is a dictionary where all keys in the original dictionary are also accessible
    as attributes to the class instance. So, if the original dictionary (setup) has a key
    "site_id" which is accessible as `setup['site_id']`, it will also be accessible as
    `setup.site_id`.

    Examples:
        >>> setup = NavigableDict({'site_id': 'KU Leuven', 'version': "0.1.0"})
        >>> assert setup['site_id'] == setup.site_id
        >>> assert setup['version'] == setup.version

    .. note::
        We always want **all** keys to be accessible as attributes, or none. That means all
        keys of the original dictionary shall be of type `str`.

    """

    def __init__(self, head: dict = None, label: str = None):
        """
        Args:
            head (dict): the original dictionary
        """
        head = head or {}
        super().__init__(head)
        self.__dict__["_memoized"] = {}
        self.__dict__["_label"] = label

        # By agreement, we only want the keys to be set as attributes if all keys are strings.
        # That way we enforce that always all keys are navigable, or none.

        if any(True for k in head.keys() if not isinstance(k, str)):
            return

        for key, value in head.items():
            if isinstance(value, dict):
                setattr(self, key, NavigableDict(head.__getitem__(key)))
            else:
                setattr(self, key, head.__getitem__(key))

    def add(self, key: str, value: Any):
        """Set a value for the given key.

        If the value is a dictionary, it will be converted into a NavigableDict and the keys
        will become available as attributes provided that all the keys are strings.

        Args:
            key (str): the name of the key / attribute to access the value
            value (Any): the value to assign to the key
        """
        if isinstance(value, dict) and not isinstance(value, NavigableDict):
            value = NavigableDict(value)
        setattr(self, key, value)

    def clear(self) -> None:
        for key in list(self.keys()):
            self.__delitem__(key)

    def __repr__(self):
        return f"{self.__class__.__name__}({super()!r})"

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        object.__delattr__(self, key)

    def __setattr__(self, key, value):
        # MODULE_LOGGER.info(f"called __setattr__({self!r}, {key}, {value})")
        if isinstance(value, dict) and not isinstance(value, NavigableDict):
            value = NavigableDict(value)
        self.__dict__[key] = value
        super().__setitem__(key, value)
        try:
            del self.__dict__["_memoized"][key]
        except KeyError:
            pass

    def __getattribute__(self, key):
        # MODULE_LOGGER.info(f"called __getattribute__({key})")
        value = object.__getattribute__(self, key)
        if isinstance(value, str) and value.startswith("class//"):
            try:
                dev_args = object.__getattribute__(self, 'device_args')
            except AttributeError:
                dev_args = ()
            return _load_class(value)(*dev_args)
        if isinstance(value, str) and value.startswith("factory//"):
            factory_args = _get_attribute(self, f'{key}_args', {})
            return _load_class(value)().create(**factory_args)
        if isinstance(value, str) and value.startswith("int_enum//"):
            content = object.__getattribute__(self, "content")
            return _load_int_enum(value, content)
        if isinstance(value, str) and value.startswith("csv//"):
            if key in self.__dict__["_memoized"]:
                return self.__dict__["_memoized"][key]
            content = _load_csv(value)
            self.__dict__["_memoized"][key] = content
            return content
        if isinstance(value, str) and value.startswith("yaml//"):
            if key in self.__dict__["_memoized"]:
                return self.__dict__["_memoized"][key]
            content = _load_yaml(value)
            self.__dict__["_memoized"][key] = content
            return content
        if isinstance(value, str) and value.startswith("pandas//"):
            separator = object.__getattribute__(self, 'separator')
            return _load_pandas(value, separator)
        else:
            return value

    def __delattr__(self, item):
        # MODULE_LOGGER.info(f"called __delattr__({self!r}, {item})")
        object.__delattr__(self, item)
        dict.__delitem__(self, item)

    def __setitem__(self, key, value):
        # MODULE_LOGGER.info(f"called __setitem__({self!r}, {key}, {value})")
        if isinstance(value, dict) and not isinstance(value, NavigableDict):
            value = NavigableDict(value)
        super().__setitem__(key, value)
        self.__dict__[key] = value
        try:
            del self.__dict__["_memoized"][key]
        except KeyError:
            pass

    def __getitem__(self, key):
        # MODULE_LOGGER.info(f"called __getitem__({self!r}, {key})")
        value = super().__getitem__(key)
        if isinstance(value, str) and value.startswith("class//"):
            try:
                dev_args = object.__getattribute__(self, 'device_args')
            except AttributeError:
                dev_args = ()
            return _load_class(value)(*dev_args)
        if isinstance(value, str) and value.startswith("csv//"):
            return _load_csv(value)
        if isinstance(value, str) and value.startswith("int_enum//"):
            content = object.__getattribute__(self, "content")
            return _load_int_enum(value, content)
        else:
            return value

    def set_private_attribute(self, key: str, value) -> None:
        """Sets a private attribute for this object.

        The name in key will be accessible as an attribute for this object, but the key will not
        be added to the dictionary and not be returned by methods like keys().

        The idea behind this private attribute is to have the possibility to add status information
        or identifiers to this classes object that can be used by save() or load() methods.

        Args:
            key (str): the name of the private attribute (must start with an underscore character).
            value: the value for this private attribute

        Returns:
            None.

        Examples:
            >>> setup = NavigableDict({'a': 1, 'b': 2, 'c': 3})
            >>> setup.set_private_attribute("_loaded_from_dict", True)
            >>> assert "c" in setup
            >>> assert "_loaded_from_dict" not in setup
            >>> assert setup.get_private_attribute("_loaded_from_dict") == True

        """
        if key in self:
            raise ValueError(
                f"Invalid argument key='{key}', this key already exists in dictionary."
            )
        if not key.startswith("_"):
            raise ValueError(
                f"Invalid argument key='{key}', must start with underscore character '_'."
            )
        self.__dict__[key] = value

    def get_private_attribute(self, key: str):
        """Returns the value of the given private attribute.

        Args:
            key (str): the name of the private attribute (must start with an underscore character).

        Returns:
            the value of the private attribute given in `key`.

        .. note::
            Because of the implementation, this private attribute can also be accessed as a 'normal'
            attribute of the object. This use is however discouraged as it will make your code less
            understandable. Use the methods to access these 'private' attributes.
        """
        if not key.startswith("_"):
            raise ValueError(
                f"Invalid argument key='{key}', must start with underscore character '_'."
            )
        return self.__dict__[key]

    def has_private_attribute(self, key):
        """
        Check if the given key is defined as a private attribute.

        Args:
            key (str): the name of a private attribute (must start with an underscore)
        Returns:
            True if the given key is a known private attribute.
        Raises:
            ValueError: when the key doesn't start with an underscore.
        """
        if not key.startswith("_"):
            raise ValueError(f"Invalid argument key='{key}', must start with underscore character '_'.")

        try:
            _ = self.__dict__[key]
            return True
        except KeyError:
            return False

    def get_raw_value(self, key):
        """
        Returns the raw value of the given key.

        Some keys have special values that are interpreted by the AtributeDict class. An example is
        a value that starts with 'class//'. When you access these values, they are first converted
        from their raw value into their expected value, e.g. the instantiated object in the above
        example. This method allows you to access the raw value before conversion.
        """
        try:
            return object.__getattribute__(self, key)
        except AttributeError:
            raise KeyError(f"The key '{key}' is not defined.")

    def __str__(self):
        return self.pretty_str()

    def pretty_str(self, indent: int = 0):
        """
        Returns a pretty string representation of the dictionary.

        Args:
            indent (int): number of indentations (of four spaces)

        .. note::
            The indent argument is intended for the recursive call of this function.
        """
        msg = ""

        for k, v in self.items():
            if isinstance(v, NavigableDict):
                msg += f"{'    '*indent}{k}:\n"
                msg += v.pretty_str(indent + 1)
            else:
                msg += f"{'    '*indent}{k}: {v}\n"

        return msg

    def __rich__(self) -> Tree:
        tree = Tree(self.__dict__["_label"] or "NavigableDict", guide_style="dim")
        walk_dict_tree(self, tree, text_style="dark grey")
        return tree

    def _save(self, fd, indent: int = 0):
        """
        Recursive method to write the dictionary to the file descriptor.

        Indentation is done in steps of four spaces, i.e. `'    '*indent`.

        Args:
            fd: a file descriptor as returned by the open() function
            indent (int): indentation level of each line [default = 0]

        """
        from egse.device import DeviceInterface

        # Note that the .items() method returns the actual values of the keys and doesn't use the
        # __getattribute__ or __getitem__ methods. So the raw value is returned and not the
        # _processed_ value.

        for k, v in self.items():

            # history shall be saved last, skip it for now

            if k == "history":
                continue

            # make sure to escape a colon in the key name

            if isinstance(k, str) and ":" in k:
                k = '"' + k + '"'

            if isinstance(v, NavigableDict):
                fd.write(f"{'    '*indent}{k}:\n")
                v._save(fd, indent + 1)
                fd.flush()
                continue

            if isinstance(v, DeviceInterface):
                v = f"class//{v.__module__}.{v.__class__.__name__}"
            if isinstance(v, float):
                v = f"{v:.6E}"
            fd.write(f"{'    '*indent}{k}: {v}\n")
            fd.flush()

        # now save the history as the last item

        if "history" in self:
            fd.write(f"{'    ' * indent}history:\n")
            self.history._save(fd, indent + 1)

    def get_memoized_keys(self):
        return list(self.__dict__["_memoized"].keys())


navdict = NavigableDict  # noqa: ignore typo
"""Shortcut for NavigableDict and more Pythonic."""


class Setup(NavigableDict):
    """The Setup class represents a version of the configuration of the test facility, the
    test setup and the Camera Under Test (CUT)."""

    def __init__(self, nav_dict: NavigableDict | dict = None, label: str = None):
        super().__init__(nav_dict or {}, label=label)

    @staticmethod
    def from_dict(my_dict):
        """Create a Setup from a given dictionary.

        Remember that all keys in the given dictionary shall be of type 'str' in order to be
        accessible as attributes.

        Examples:
            >>> setup = Setup.from_dict({"ID": "my-setup-001", "version": "0.1.0"})
            >>> assert setup["ID"] == setup.ID == "my-setup-001"

        """
        return Setup(my_dict, label="Setup")

    @staticmethod
    def from_yaml_string(yaml_content: str = None):
        """Loads a Setup from the given YAML string.

        This method is mainly used for easy creation of Setups from strings during unit tests.

        Args:
            yaml_content (str): a string containing YAML

        Returns:
            a Setup that was loaded from the content of the given string.
        """

        if not yaml_content:
            raise ValueError("Invalid argument to function: No input string or None given.")

        setup_dict = yaml.safe_load(yaml_content)

        if "Setup" in setup_dict:
            setup_dict = setup_dict["Setup"]

        return Setup(setup_dict, label="Setup")

    @staticmethod
    @lru_cache
    def from_yaml_file(filename: Union[str, Path] = None, add_local_settings: bool = True):
        """Loads a Setup from the given YAML file.

        Args:
            filename (str): the path of the YAML file to be loaded
            add_local_settings (bool): if local settings shall be loaded and override the settings from the YAML file.

        Returns:
            a Setup that was loaded from the given location.
        """

        if not filename:
            raise ValueError("Invalid argument to function: No filename or None given.")

        # MODULE_LOGGER.info(f"Loading {filename}...")

        setup_dict = read_configuration_file(filename, force=True)
        if setup_dict == {}:
            warnings.warn(f"Empty Setup file: {filename!s}")

        try:
            setup_dict = setup_dict["Setup"]
        except KeyError:
            warnings.warn(f"Setup file doesn't have a 'Setup' group: {filename!s}")

        setup = Setup(setup_dict, label="Setup")
        setup.set_private_attribute("_filename", filename)
        if setup_id := _parse_filename_for_setup_id(str(filename)):
            setup.set_private_attribute("_setup_id", setup_id)

        return setup

    def to_yaml_file(self, filename=None):
        """Saves a NavigableDict to a YAML file.

        When no filename is provided, this method will look for a 'private' attribute
        `_filename` and use that to save the data.

        Args:
            filename (str): the path of the YAML file where to save the data

        .. note::
            This method will **overwrite** the original or given YAML file and therefore you might
            lose proper formatting and/or comments.

        """
        if not filename:
            try:
                filename = self.get_private_attribute("_filename")
            except KeyError:
                raise ValueError("No filename given or known, can not save Setup.")

        print(f"Saving Setup to {filename}")

        with Path(filename).open("w") as fd:

            fd.write(
                f"# Setup generated by:\n"
                f"#\n"
                f"#    Setup.to_yaml_file(setup, filename='{filename}')\n#\n"
            )
            fd.write(f"# Created on {format_datetime()}\n\n")
            fd.write("Setup:\n")

            self._save(fd, indent=1)

        self.set_private_attribute("_filename", filename)

    @staticmethod
    def compare(setup_1: NavigableDict, setup_2: NavigableDict):
        from egse.device import DeviceInterface
        from deepdiff import DeepDiff

        return DeepDiff(setup_1, setup_2, exclude_types=[DeviceInterface])

    # def get_devices(self):
    #     """Returns a list of devices for the current setup.

    #     Returns:
    #         - List of devices for the current setup.
    #     """

    #     devices = []

    #     Setup.walk(self, "device", devices)

    #     return devices

    @staticmethod
    def find_devices(node: NavigableDict, devices: dict = None):
        """
        Returns a dictionary with the devices that are included in the setup.  The keys
        in the dictionary are taken from the "device_name" entries in the setup file. The
        corresponding values in the dictionary are taken from the "device" entries in the
        setup file.

        Args:
            - node: Dictionary in which to look for the devices (and their names).
            - devices: Dictionary in which to include the devices in the setup.

        Returns:
            - Dictionary with the devices that are included in the setup.
        """
        devices = devices or {}

        for sub_node in node.values():

            if isinstance(sub_node, NavigableDict):

                if ("device" in sub_node) and ("device_name" in sub_node):

                    device = sub_node.get_raw_value("device")

                    if "device_args" in sub_node:
                        device_args = sub_node.get_raw_value("device_args")
                    else:
                        device_args = ()

                    devices[sub_node["device_name"]] = (device, device_args)

                else:

                    Setup.find_devices(sub_node, devices=devices)

        return devices

    @staticmethod
    def walk(node: dict, key_of_interest, leaf_list):

        """
        Walk through the given dictionary, in a recursive way, appending the leaf with
        the given keyword to the given list.

        Args:
            - node: Dictionary in which to look for leaves with the given keyword.
            - key_of_interest: Key to look for in the leaves of the given dictionary.
            - leaf_list: List to which to add the leaves with the given keyword.

        Returns:
            - Given list with the leaves (with the given keyword) in the given dictionary
              appended to it.
        """

        for key, sub_node in node.items():

            if isinstance(sub_node, dict):

                Setup.walk(sub_node, key_of_interest, leaf_list)

            elif key == key_of_interest:

                leaf_list.append(sub_node)

    def __rich__(self) -> Tree:
        tree = super().__rich__()
        if self.has_private_attribute("_setup_id"):
            setup_id = self.get_private_attribute('_setup_id')
            tree.add(f"Setup ID: {setup_id}", style="grey50")
        if self.has_private_attribute("_filename"):
            filename = self.get_private_attribute('_filename')
            tree.add(f"Loaded from: {filename}", style="grey50")
        return tree

    def get_id(self) -> Optional[str]:
        """Returns the Setup ID (as a string) or None when no setup id could be identified."""
        if self.has_private_attribute("_setup_id"):
            return self.get_private_attribute('_setup_id')
        else:
            return None

    def get_filename(self) -> Optional[str]:
        """Returns the filename for this Setup or None when no filename could be determined."""
        if self.has_private_attribute("_filename"):
            return self.get_private_attribute('_filename')
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


def get_setup(setup_id: int = None):
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
        return

    try:
        with ConfigurationManagerProxy() as proxy:
            setup = proxy.get_setup(setup_id)
        return setup
    except ConnectionError:
        print("Could not make a connection with the Configuration Manager, no Setup returned.")


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
    setup_location = repo_location / 'data' / site_id / 'conf'

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
        LookupError when the environment variable is not set.

        NotADirectoryError when either the repository folder or the Setups folder doesn't exist.

        FileNotFound when no Setup file can be found for the given arguments.

    """

    if not has_conf_repo_location():
        setup_location = Path(get_conf_data_location(site_id))
    else:
        setup_location = _check_conditions_for_get_path_of_setup_file(site_id)

    if setup_id:
        files = list(setup_location.glob(f'SETUP_{site_id}_{setup_id:05d}_*.yaml'))

        if not files:
            raise FileNotFoundError(f"No Setup found for {setup_id=} and {site_id=}.")

        file_path = Path(setup_location) / files[-1]
    else:
        files = setup_location.glob('SETUP*.yaml')

        last_file_parts = sorted([file.name.split('_') for file in files])[-1]
        file_path = Path(setup_location) / "_".join(last_file_parts)

    sanity_check(file_path.is_file(), f"The expected Setup file doesn't exist: {file_path!s}")

    return file_path


def load_setup(
        setup_id: int = None,
        site_id: str = None, from_disk: bool = False):
    """
    This function loads the Setup corresponding with the given `setup_id`.

    Loading a Setup means:

    * that this Setup will also be loaded and activated in the configuration manager,
    * that this Setup will be available from the `GlobalState.setup`

    When no setup_id is provided, the current Setup is loaded from the configuration manager.

    Args:
        setup_id (int): the identifier for the Setup
        site_id (str): the name of the test house
        from_disk (bool): True if the Setup needs to be loaded from disk

    Returns:
        The requested Setup or None when the Setup could not be loaded from the
        configuration manager.

    """
    from egse.state import GlobalState

    if from_disk:
        if site_id is None:
            raise ValueError(
                "The site_id argument can not be empty when from_disk is given and True")

        setup_file_path = get_path_of_setup_file(setup_id, site_id)

        rich.print(
            f"Loading {'' if setup_id else 'the latest '}Setup {f'{setup_id} ' if setup_id else ''}for {site_id}..."
        )

        return Setup.from_yaml_file(setup_file_path)

    # When we arrive here the Setup shall be loaded from the Configuration manager

    try:
        from egse.confman import ConfigurationManagerProxy
    except ImportError:
        print("WARNING: package 'cgse-core' is not installed, service not available. Returning an empty Setup.")
        return Setup()

    if setup_id is not None:
        try:
            with ConfigurationManagerProxy() as proxy:
                proxy.load_setup(setup_id)

        except ConnectionError:
            MODULE_LOGGER.warning(
                "Could not make a connection with the Configuration Manager, no Setup to show you."
            )
            rich.print(
                "\n"
                "If you are not running this from an operational machine, do not have a CM "
                "running locally or don't know what this means, then: \n"
                "  (1) define the environment variable 'PLATO_CONF_REPO_LOCATION' and \n"
                "      it points to the location of the plato-cgse-conf repository,\n"
                "  (2) try again using the argument 'from_disk=True'.\n"
            )

    return GlobalState.load_setup()


def submit_setup(setup: Setup, description: str):
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
    # We have not yet decided if this option should be made available. Therefore, we
    # leave it here as hardcoded True.

    # replace (bool): True if the current Setup in the configuration manager shall
    #                 be replaced by this new Setup. [default=True]
    replace: bool = True

    try:
        from egse.confman import ConfigurationManagerProxy
    except ImportError:
        print("WARNING: package 'cgse-core' is not installed, service not available.")
        return

    try:
        with ConfigurationManagerProxy() as proxy:
            setup = proxy.submit_setup(setup, description, replace)

        if setup is None:
            rich.print("[red]Submit failed for given Setup, no reason given.[/red]")
        elif isinstance(setup, Failure):
            rich.print(f"[red]Submit failed for given Setup[/red]: {setup}")
            setup = None
        elif replace:
            rich.print(textwrap.dedent("""\
                [green]
                Your new setup has been submitted and pushed to GitHub. The new setup is also
                activated in the configuration manager. Load the new setup in your session with:

                    setup = load_setup()
                [/]
                """
            ))
        else:
            rich.print(
                textwrap.dedent(
                    """[dark_orange]
                    Your new setup has been submitted and pushed to GitHub, but has not been
                    activated in the configuration manager. To activate this setup, use the
                    following command:

                        setup = load_setup({str(setup.get_id())})
                    [/]
                    """
                )
            )

        return setup.get_id() if setup is not None else None

    except ConnectionError:
        rich.print("Could not make a connection with the Configuration Manager, no Setup was submitted.")
    except NotImplementedError:
        rich.print(
            textwrap.dedent(
                """\
                Caught a NotImplementedError. That usually means the configuration manager is not running or
                can not be reached. Check on the egse-server if the `cm_cs` process is running. If not you will
                need to be restart the core services.
                """
            )
        )


def main(args: list = None):  # pragma: no cover
    import argparse

    from rich import print

    from egse.config import find_files
    from egse.settings import Settings

    SITE = Settings.load("SITE")
    location = os.environ.get("PLATO_CONF_DATA_LOCATION")
    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Print out the Setup for the given setup-id. The Setup will
            be loaded from the location given by the environment variable
            PLATO_CONF_DATA_LOCATION. If this env is not set, the Setup
            will be searched from the current directory."""
        ),
        epilog=f"PLATO_CONF_DATA_LOCATION={location}"
    )
    parser.add_argument(
        "--setup-id", type=int, default=-1,
        help="the Setup ID. If not given, the last Setup will be selected.")
    parser.add_argument("--list", "-l", action="store_true", help="list available Setups.")
    parser.add_argument("--use-cm", action="store_true", help="use the configuration manager.")
    args = parser.parse_args(args or [])

    if args.use_cm:
        try:
            from egse.confman import ConfigurationManagerProxy
        except ImportError:
            print("WARNING: package 'cgse-core' is not installed, service not available.")
            return

        with ConfigurationManagerProxy() as cm:
            if args.list:
                print(cm.list_setups())
            else:
                print(cm.get_setup())
        return

    if args.list:
        files = find_files(f"SETUP_{SITE.ID}_*_*.yaml", root=location)
        files = list(files)
        if files:
            location = files[0].parent.resolve()
        print(sorted([f.name for f in files]))
        print(f"Loaded from [purple]{location}.")
    else:
        setup_id = args.setup_id
        if setup_id == -1:
            setup_files = find_files(f"SETUP_{SITE.ID}_*_*.yaml", root=location)
        else:
            setup_files = find_files(f"SETUP_{SITE.ID}_{setup_id:05d}_*.yaml", root=location)
        setup_files = list(setup_files)
        if len(setup_files) > 0:
            setup_file = sorted(setup_files)[-1]
            setup = Setup.from_yaml_file(setup_file)
            print(setup)
        else:
            print("[red]No setup files were found.[/]")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
