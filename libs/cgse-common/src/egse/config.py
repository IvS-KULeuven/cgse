"""
This module provides convenience functions to properly configure the Common-EGSE
and to find paths and resources.
"""
from __future__ import annotations

import errno
import fnmatch
import logging
import os
from functools import lru_cache
from os.path import exists
from os.path import join
from pathlib import Path
from pathlib import PurePath
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import git

from egse.decorators import deprecate

_HERE = Path(__file__).parent.resolve()
_LOGGER = logging.getLogger(__name__)


def find_first_occurrence_of_dir(pattern: str, root: Path | str = None) -> Optional[Path]:
    """
    Returns the full path of the directory that first matches the pattern. The directory hierarchy is
    traversed in alphabetical order. The pattern is matched first against all directories in the root
    folder, if there is no match, the first folder in root is traversed until a match is found. If no
    match is found, the second folder in root is traversed.

    Note that the pattern may contain parent directories, like `/egse/data/icons` or `egse/*/icons`,
    in which case the full pattern is matched.

    Args:
        pattern: a filename pattern
        root: the root folder to start the hierarchical search

    Returns:
        The full path of the matched pattern or None if no match could be found.
    """
    import fnmatch

    root = Path(root).resolve() if root else _HERE
    if not root.is_dir():
        root = root.parent

    parts = pattern.rsplit("/", maxsplit=1)
    if len(parts) == 2:
        first_part = parts[0]
        last_part = parts[1]
    else:
        first_part = ""
        last_part = parts[0]

    dirs = sorted([entry.name for entry in root.iterdir() if entry.is_dir()])

    if root.match(f"*{first_part}") and (matches := fnmatch.filter(dirs, last_part)):
        return root / matches[0]

    for d in dirs:
        if match := find_first_occurrence_of_dir(pattern, root / d):
            return match

    return None


def find_dir(pattern: str, root: str = None) -> Optional[Path]:
    """
    Find the first folder that matches the given pattern.

    Note that if there are more folders that match the pattern in the distribution,
    this function only returns the first occurrence that is found, which might
    not be what you want. To be sure only one folder is returned, use the
    `find_dirs()` function and check if there is just one item returned in the list.

    Args:
        pattern (str): pattern to match (use * for wildcard)
        root (str): the top level folder to search [default=common-egse-root]

    Returns:
        the first occurrence of the directory pattern or None when not found.
    """
    for folder in find_dirs(pattern, root):
        return folder

    return None


def find_dirs(pattern: str, root: str = None):
    """
    Generator for returning directory paths from a walk started at `root` and matching pattern.

    The pattern can contain the asterisk '*' as a wildcard.

    The pattern can contain a directory separator '/' which means
    the last part of the path needs to match these folders.

    Examples:
        >>> for folder in find_dirs("/egse/images"):
        ...     assert folder.match('*/egse/images')

        >>> folders = list(find_dirs("/egse/images"))
        >>> assert len(folders)

    Args:
        pattern (str): pattern to match (use * for wildcard)
        root (str): the top level folder to search [default=common-egse-root]

    Returns:
         Paths of folders matching pattern, from root.
    """
    root = Path(root).resolve() if root else get_common_egse_root()
    if not root.is_dir():
        root = root.parent

    parts = pattern.rsplit("/", maxsplit=1)
    if len(parts) == 2:
        first_part = parts[0]
        last_part = parts[1]
    else:
        first_part = ""
        last_part = parts[0]

    for path, folders, files in os.walk(root):
        for name in fnmatch.filter(folders, last_part):
            if path.endswith(first_part):
                yield Path(path) / name


def find_files(pattern: str, root: PurePath | str = None, in_dir: str = None):
    """
    Generator for returning file paths from a top folder, matching the pattern.

    The top folder can be specified as e.g. `__file__` in which case the parent of that file
    will be used as the top root folder. Note that when you specify '.' as the root argument
    the current working directory will be taken as the root folder, which is probably not what
    you intended.

    When the file shall be in a specific directory, use the `in_dir` keyword. This requires
    that the path ends with the given string in `in_dir`.

        >>> file_pattern = 'EtherSpaceLink*.dylib'
        >>> in_dir = 'lib/CentOS-7'
        >>> for file in find_files(file_pattern, in_dir=in_dir):
        ...     assert file.match("*lib/CentOS-7/EtherSpaceLink*")

    Args:
        pattern (str) : sorting pattern (use * for wildcard)
        root (str): the top level folder to search [default=common-egse-root]
        in_dir (str): the 'leaf' directory in which the file shall be

    Returns:
        Paths of files matching pattern, from root.
    """
    root = Path(root).resolve() if root else get_common_egse_root()
    if not root.is_dir():
        root = root.parent

    exclude_dirs = ("venv", "venv38", ".git", ".idea", ".DS_Store")

    for path, folders, files in os.walk(root):
        folders[:] = list(filter(lambda x: x not in exclude_dirs, folders))
        if in_dir and not path.endswith(in_dir):
            continue
        for name in fnmatch.filter(files, pattern):
            yield Path(path) / name


def find_file(name: str, root: str = None, in_dir: str = None) -> Optional[Path]:
    """
    Find the path to the given file starting from the root directory of the
    distribution.

    Note that if there are more files with the given name found in the distribution,
    this function only returns the first file that is found, which might not be
    what you want. To be sure only one file is returned, use the `find_files()`
    function and check if there is just one file returned in the list.

    When the file shall be in a specific directory, use the `in_dir` keyword.
    This requires that the path ends with the given string in `in_dir`.

        >>> file_pattern = 'EtherSpaceLink*.dylib'
        >>> in_dir = 'lib/CentOS-7'
        >>> file = find_file(file_pattern, in_dir=in_dir)
        >>> assert file.match("*/lib/CentOS-7/EtherSpace*")

    Args:
        name (str): the name of the file
        root (str): the top level folder to search [default=common-egse-root]
        in_dir (str): the 'leaf' directory in which the file shall be

    Returns:
        the first occurrence of the file or None when not found.
    """
    for file_ in find_files(name, root, in_dir):
        return file_

    return None


def find_root(
    path: Union[str, PurePath] | None, tests: Tuple[str, ...] = (), default: str = None
) -> Union[PurePath, None]:
    """
    Find the root folder based on the files in ``tests``.

    The algorithm crawls backward over the directory structure until one of the
    items in ``tests`` is matched. and it will return that directory as a ``Path``.

    When no root folder can be determined, the ``default``
    parameter is returned as a Path (or None).

    When nothing is provided in ``tests``, all matches will
    fail and the ``default`` parameter will be returned.

    Args:
        path: folder from which the search is started
        tests: names (files or dirs) to test for existence
        default: returned when no root is found

    Returns:
        a Path which is the root folder.
    """

    if path is None:
        return None
    if not Path(path).exists():
        return None

    prev, test = None, Path(path)
    while prev != test:
        if any(test.joinpath(file_).exists() for file_ in tests):
            return test.resolve()
        prev, test = test, test.parent

    return Path(default) if default is not None else None


@lru_cache(maxsize=16)
@deprecate(reason="the concept of CGSE root doesn't exist in a monorepo.",
           alternative="a case-by-case alternative.")
def get_common_egse_root(path: Union[str, PurePath] = None) -> Optional[PurePath]:
    """
    Returns the absolute path to the installation directory for the Common-EGSE.

    The algorithm first tries to determine the path from the environment variable
    ``PLATO_COMMON_EGSE_PATH``. If this environment variable doesn't exist, the algorithm
    tries to determine the path automatically from (1) the git root if it is a git repository,
    or (2) from the location of this module assuming the installation is done from the
    GitHub distribution.

    When the optional argument ``path`` is given, that directory will be used to start the
    search for the root folder.

    At this moment the algorithm does not cache the ``egse_path`` in order to speed up
    the successive calls to this function.

    Args:
        path (str or Path): a directory as a Path or str [optional]

    Returns:
        Path: the absolute path to the Common-EGSE installation directory or None
    """
    _TEST_NAMES = ("pyproject.toml", "setup.py")
    if path is not None:
        return find_root(path, tests=_TEST_NAMES)

    egse_path: Union[str, PurePath, None] = os.getenv("COMMON_EGSE_PATH")

    if egse_path is None:

        # The root of the plato-common-egse installation shall be determined from the location
        # of this config module using git commands to find the git root folder.
        # This assumes the user has installed from git/GitHub (which is not always true)!
        #
        # Alternatively, the root directory can be determined from the location of this module
        # by going back in the directory structure until the ``setup.py`` module is found.

        _THIS_FILE_PATH = Path(__file__).resolve()
        _THIS_FILE_LOCATION = _THIS_FILE_PATH.parent

        try:
            git_repo = git.Repo(_THIS_FILE_PATH, search_parent_directories=True)
            git_root = git_repo.git.rev_parse("--show-toplevel")
            egse_path = git_root
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            _LOGGER.info("no git repository found, assuming installation from distribution.")
            egse_path = find_root(_THIS_FILE_LOCATION, tests=_TEST_NAMES)

        _LOGGER.debug(f"Common-EGSE location is automatically determined: {egse_path}.")

    else:
        _LOGGER.debug(
            f"Common-EGSE location determined from environment variable "
            f"PLATO_COMMON_EGSE_PATH: {egse_path}"
        )

    return Path(egse_path)


def get_resource_dirs(root_dir: Union[str, PurePath] = None) -> List[Path]:
    """
    Define directories that contain resources like images, icons, and data files.

    Resource directories can have the following names: `resources`, `data`, `icons`, or `images`.
    This function checks if any of the resource directories exist in the project root directory,
    in the `root_dir` that is given as an argument or in the `src/egse` sub-folder.

    So, the directories that are searched for the resource folders are:

    * `root_dir` or the project's root directory
    * the `src/egse` sub-folder of one of the above

    For all existing directories the function returns the absolute path.

    Args:
        root_dir (str): the directory to search for resource folders

    Returns:
        a list of absolute Paths.
    """
    project_dir = Path(root_dir).resolve() if root_dir else get_common_egse_root()
    result = []
    for dir_ in ["resources", "data", "icons", "images"]:
        if (project_dir / dir_).is_dir():
            result.append(Path(project_dir, dir_).resolve())
        if (project_dir / "src" / "egse" / dir_).is_dir():
            result.append(Path(project_dir, "src", "egse", dir_).resolve())
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
        resource_root_dir (str): the root directory where the search for resources should be started

    Returns:
        the absolute path of the data file with the given name. The first name that matches
        is returned. If no file with the given name or path exists, a FileNotFoundError is raised.

    """
    for resource_dir in get_resource_dirs(resource_root_dir):
        resource_path = join(resource_dir, name)
        if exists(resource_path):
            return Path(resource_path).absolute()
    raise FileNotFoundError(errno.ENOENT, f"Could not locate resource '{name}'")


def set_logger_levels(logger_levels: List[Tuple] = None):
    """
    Set the logging level for the given loggers.

    """
    logger_levels = logger_levels or []

    for name, level in logger_levels:
        a_logger = logging.getLogger(name)
        a_logger.setLevel(level)


class WorkingDirectory:
    """
    WorkingDirectory is a context manager to temporarily change the working directory while
    executing some code.

    This context manager has a property `path` which returns the absolute path of the
    current directory.

    Examples:
        >>> with WorkingDirectory(find_dir("/egse/images")) as wdir:
        ...     for file in wdir.path.glob('*'):
        ...         assert file.exists()  # do something with the image files

    """

    def __init__(self, path):
        """
        Args:
            path (str, Path): the folder to change to within this context
        Raises:
            ValueError when the given path doesn't exist.
        """
        self._temporary_path = Path(path)
        if not self._temporary_path.exists():
            raise ValueError(f"The given path ({path}) doesn't exist.")
        self._current_dir = None

    def __enter__(self):
        self._current_dir = os.getcwd()
        os.chdir(self._temporary_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            os.chdir(self._current_dir)
        except OSError as exc:
            _LOGGER.warning(f"Change back to previous directory failed: {exc}")

    @property
    def path(self):
        """Resolve and return the current Path of the context."""
        return self._temporary_path.resolve()
