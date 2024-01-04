"""
This module provides convenience functions to use resources in your code without
the need to specify an absolute path or try to locate the resources in your local
installation (which is time-consuming, error-prone, and introduces quite some
redundancy).

Resources can be files of different format that are distributed together with the
source code, e.g.

    * image data
    * icons
    * YAML files
    * binary files, e.g. dynamic libraries
    * style files for GUI applications
    * calibration files distributed with the source code

Each of the resources have a fixed location within the source tree and is identified
with a resource identifier. There are a number of default identifier that are defined
as follows:

    * `icons`: located in the sub-folder 'icons'
    * `images`: located in the sub-folder 'images'
    * `styles`: located in the sub-folder 'data'
    * `data`: located in the sub-folder 'data'
    * `lib`: located in sub-folder 'lib'

Resource shall be initialised by either the process or the library using the function
`initialise_resources()`. The function optionally takes a locations in which it will
search for the default resource ids. The usual way to initialise is:

    >>> initialise_resources(Path(__file__).parent)

Another way to make your resource available is through entry points in the
distribution of your package. In the `pyproject.toml` file, you can specify resources
as follows:

    [project.entry-points."cgse.resource"]
    icons = 'egse.gui.icons'
    styles = 'egse.gui.styles'

This will automatically add these resources during initialisation.

Resources can be accessed from the code without specifying the absolute pathname,
using a `:/resource_id/` that is known by the resource module. A wildcard can be
introduced after the `resource_id` to indicate the resource is in one of the
subdirectories.

Example usage:
    * get_resource(":/icons/open-document.png")
    * get_resource(":/styles/dark.qss")
    * get_resource(":/lib/*/EtherSpaceLink_v34_86.dylib")

A new `resource_id` can be added with the `add_resource_id()` function, specifying a
resource_id string and a location. That location will be added to the list of locations
for that resource id. To add a resource location for e.g. configuration files, do

    >>> from egse.resource import add_resource_id
    >>> add_resource_id('styles', Path(__file__).parent)

Alternatives

The `egse.config` module has a number of alternatives for locating files and resources.

    * find_file(..) and find_files(..)
    * find_dir(..) and find_dirs(..)
    * get_resource_dirs()
    * get_resource_path()

The functions for finding files and directories are more flexible, but take more
time and effort. They are mainly used for dynamically searching for a file or
folder, not necessarily within the source code location.

The resource specific functions in the egse.config module will be deprecated when
their functionality is fully replaced by this `egse.resource` module.

"""

import errno
import logging
import re
from pathlib import Path
from pathlib import PurePath
from typing import Dict
from typing import List
from typing import Union

from os.path import exists
from os.path import join

from egse.config import find_first_occurrence_of_dir
from egse.config import find_files
from egse.exceptions import InternalError
from egse.plugin import entry_points
from egse.system import get_package_location

_LOGGER = logging.getLogger(__name__)


class ResourceError(Exception):
    """Base class, raised when a resource is not defined."""


class AmbiguityError(ResourceError):
    """Raised when more than one option is possible."""


class NoSuchFileError(ResourceError):
    """Raised when no file could be found for the given resource."""


__all__ = [
    "get_resource",
    "get_resource_locations",
    "get_resource_dirs",
    "get_resource_path",
    "add_resource_id",
    "initialise_resources",
    "ResourceError",
    "AmbiguityError",
    "NoSuchFileError",
]

# Testing regex: https://pythex.org

PATTERN = re.compile(r"^:/(\w+)/(\*+/)?(.*)$")

# Default resources will be checked when executing the initialise_resources()
# optionally with a path as root. It is not needed to use add_resource_id()
# for these resources.

DEFAULT_RESOURCES = {
    "icons": "/icons",
    "images": "/images",
    "styles": "/styles",
    "lib": "/lib",
    "data": "/data",
}

_RESOURCE_DIRS = ["resources", "icons", "images", "styles", "data"]

resources = {}


def check_if_file_exists(filename: Union[Path, str], resource_id: str = None) -> Path:
    """
    Check if the given filename exists. If the filename exists, return the filename, else raise a
    NoSuchFileError.

    Args:
        filename (Path|str): an absolute filename
        resource_id (str): a resource identifier

    Return:
        The given filename if it exists.

    Raises:
        NoSuchFileError if the given filename doesn't exist.
    """
    filename = Path(filename)
    if filename.is_file():
        return filename

    if resource_id:
        raise NoSuchFileError(
            f"The file '{filename.name}' could not be found for the given resource '{resource_id}'")
    else:
        raise NoSuchFileError(f"The file '{filename.name}' doesn't exist.")


def contains_wildcard(filename: str):
    """
    Returns True if the filename contains a wildcard, otherwise False.
    A wildcard is an asterisk '*' or a question mark '?' character.
    """
    if '*' in filename:
        return True
    if '?' in filename:
        return True

    return False


def get_resource_locations() -> Dict[str, List[Path]]:
    """
    Returns a dictionary of names that can be used as resource location.
    The keys are strings that are recognised as valid resource identifiers, the
    values are a list of their actual absolute path names.
    """
    return resources.copy()


def get_resource_dirs(root_dir: Union[str, PurePath]) -> List[Path]:
    """
    Define directories that contain resources like images, icons, and data files.

    Resource directories can have the following names: `resources`, `data`, `icons`, or `images`.
    This function checks if any of the resource directories exist in the `root_dir` that is given as an argument.

    For all existing directories the function returns the absolute path.

    If the argument root_dir is None, an empty list will be returned and a warning message will be issued.

    Args:
        root_dir (str): the directory to search for resource folders

    Returns:
        a list of absolute Paths.
    """

    if root_dir is None:
        _LOGGER.warning("The argument root_dir can not be None, an empty list is returned.")
        return []

    root_dir = Path(root_dir).resolve()
    if not root_dir.is_dir():
        root_dir = root_dir.parent

    result = []
    for dir_ in _RESOURCE_DIRS:
        if (root_dir / dir_).is_dir():
            result.append(Path(root_dir, dir_).resolve())

    return result


def get_resource_path(name: str, resource_root_dir: Union[str, PurePath] = None) -> PurePath:
    """
    Searches for a data file (resource) with the given name.

    When `resource_root_dir` is not given, the search for resources will start at the root
    folder of the project (using the function `get_common_egse_root()`). Any other root
    directory can be given, e.g. if you want to start the search from the location of your
    source code file, use `Path(__file__).parent` as the `resource_root_dir` argument.

    Args:
        name (str): the name of the resource that is requested
        resource_root_dir (str): the root directory w_HERE the search for resources should be started

    Returns:
        the absolute path of the data file with the given name. The first name that matches
        is returned. If no file with the given name or path exists, a FileNotFoundError is raised.

    """
    for resource_dir in get_resource_dirs(resource_root_dir):
        resource_path = join(resource_dir, name)
        if exists(resource_path):
            return Path(resource_path).absolute()
    raise FileNotFoundError(errno.ENOENT, f"Could not locate resource '{name}'")


def initialise_resources(root: Union[Path, str] = Path(__file__).parent):
    """
    Initialise the default resources and any resource published by a package entry point.

    The argument `root` specifies the root location for the resources. If not specified,
    the location of this module is taken as the root location. So, if you have installed
    this package with `pip install`, you should give the location of your project's source
    code as the root argument.

    When you have specified entry points for the group 'cgse.resource' in your project,
    these resources will also be initialised. Check the global documentation of this module
    for an example entry point.

    Args:
        root (Path|str): the root location for the resources.

    Returns:
        None.
    """

    #  the resources with their absolute path names

    for resource_id in DEFAULT_RESOURCES:
        folder = find_first_occurrence_of_dir(DEFAULT_RESOURCES[resource_id], root=root)
        if folder is not None:
            x = resources.setdefault(resource_id, [])
            if folder not in x:
                x.append(folder)

    for ep in entry_points("cgse.resource"):
        for location in get_package_location(ep.value):
            x = resources.setdefault(ep.name, [])
            if location not in x:
                x.append(location)

    _LOGGER.debug(f"Resources have been initialised: {resources = }")


def print_resources():
    """Prints the currently defined resources."""

    if resources:
        print("Available resources:")
    else:
        print("No resources defined.")
        return

    for resource_id, locations in resources.items():
        print(f"  {resource_id}:")
        for location in locations:
            print(f"    {location}")


def add_resource_id(resource_id: str, location: Union[Path, str]):
    """
    Adds a resource identifier with the given location. Resources can then be specified
    using this resource id.

    The location can be an absolute or relative pathname. In the latter case the path
    will be expanded against the current working directory.

    Args:
        resource_id (str): a resource identifier
        location (Path|str): an absolute or relative pathname

    Returns:
        ValueError if the location can not be determined or is not a directory.
    """

    # Check if location exists and is a directory.

    location = Path(location).expanduser().resolve()

    if not location.exists():
        raise ValueError(f"Unknown location '{location}'")

    if location.is_dir():
        x = resources.setdefault(resource_id, [])
        if location not in x:
            x.append(location)
    else:
        raise ValueError(f"Location is not a directory: {location=}")


def get_resource(resource_locator: str) -> Path:
    """
    Returns the absolute Path for the given resource_locator. The resource_locator consists of
    a resource_id, an optional wildcard and a filename separated by a forward slash '/' and
    started by a colon ':'.

        ':/<resource_id>/[*/]<filename>'

    If the resource_locator starts with a colon ':', the name will be interpreted as a resource_id
    and filename combination and parsed as such

    If the resource_locator doesn't start with a colon ':', then the string will be interpreted as a
    Path name and returned if that path exists, otherwise a ResourceError is raised.

    The filename can contain the wildcard '*' and/or '?', however the use of a wildcard in the
    filename can still only match one unique filename. This can be useful e.g. if you know the
    filename except for one part of it like a timestamp. Used, e.g., for matching Setup files which
    are unique filenames with a timestamp.

    Args:
        resource_locator (str): a special resource name or a filename

    Returns:
        a Path with the absolute filename for the resource.

    Raises:
        ResourceError when no file could be found or the search is ambiguous.

    """
    # Try to match the special resource syntax `:/resource_id/` or `:/resource_id/*/`

    if resource_locator.startswith(':'):

        match = PATTERN.fullmatch(resource_locator)
        resource_id = match[1]
        filename = match[3]
        try:
            resource_locations = resources[resource_id]
        except KeyError:
            raise ResourceError(f"Resource not defined: {resource_id}")

        # Match can be only three things
        #   - None in which case the file must be in the resource location directly
        #   - '*/' in which case the file must be in a sub-folder of the resource
        #   - '**/' to find the file in any sub-folder below the given resource

        if match[2] is None:

            # This will return the first occurrence of the filename

            for resource_location in resource_locations:
                if contains_wildcard(filename):
                    files = list(find_files(filename, root=resource_location))

                    if len(files) == 1:
                        filename = files[0]
                    elif len(files) == 0:
                        raise NoSuchFileError(f"No file found that matches {filename=} for the given "
                                              f"resource '{resource_id}'.")
                    else:
                        raise AmbiguityError(f"The {filename=} found {len(files)} matches for "
                                             f"the given resource '{resource_id}'.")

                return check_if_file_exists(resource_location / filename, resource_id)

        elif match[2] == "*/":
            # This will return the first occurrence of the filename

            for resource_location in resource_locations:

                files = list(find_files(filename, root=resource_location))

                if len(files) == 1:
                    return files[0]
                elif len(files) == 0:
                    raise NoSuchFileError(
                        f"The {filename=} could not be found for the given resource '{resource_id}'."
                    )
                else:
                    raise AmbiguityError(f"The {filename=} was found {len(files)} times for "
                                         f"the given resource location '{resource_location}'.")
        elif match[2] == '**/':
            raise NotImplementedError("The '**' to walk the tree is not yet implemented.")
        else:
            raise InternalError(
                f"This shouldn't happen, the match is {match[2]=} for {resource_locator=}")
    else:
        return check_if_file_exists(Path(resource_locator))


# Now initialise the resources, this will
#
#   * Add resource locations in this project (cgse-core) for the default resource ids
#   * Add any other resource locations for the rentry points 'cgse.resource'

initialise_resources()


if __name__ == "__main__":

    import rich

    rich.print("Default resources:")
    rich.print(get_resource_locations())
