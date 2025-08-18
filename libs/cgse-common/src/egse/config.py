"""
This module provides convenience functions to properly configure the CGSE
and to find paths and resources.
"""

import fnmatch
import os
from pathlib import Path
from pathlib import PurePath
from typing import Generator
from typing import Tuple
from typing import Union

from egse.log import logger


def find_first_occurrence_of_dir(pattern: str, root: Path | str) -> Path | None:
    """
    Returns the full path of the directory that first matches the pattern. The directory hierarchy is
    traversed in alphabetical order. The pattern is matched first against all directories in the root
    folder, if there is no match, the first folder in root is traversed until a match is found. If no
    match is found, the second folder in root is traversed.

    Note that the pattern may contain parent directories, like `/egse/data/icons` or `egse/*/icons`,
    in which case the full pattern is matched.

    In the case that you pass an empty string for the root argument, it will resolve into
    the current working directory.

    Args:
        pattern: a filename pattern
        root: the root folder to start the hierarchical search

    Returns:
        The full path of the matched pattern or None if no match could be found.
    """
    import fnmatch

    root_arg = root

    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"The root argument is not a valid directory: {root_arg}.")

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


def find_dir(pattern: str, root: Path | str) -> Path | None:
    """
    Find the first folder that matches the given pattern.

    Note that if there are more folders that match the pattern in the distribution,
    this function only returns the first occurrence that is found, which might
    not be what you want. To be sure only one folder is returned, use the
    `find_dirs()` function and check if there is just one item returned in the list.

    Args:
        pattern: pattern to match (use * for wildcard)
        root: the top level folder to search

    Returns:
        the first occurrence of the directory pattern or None when not found.
    """
    for folder in find_dirs(pattern, root):
        return folder

    return None


def find_dirs(pattern: str, root: Path | str) -> Generator[Path, None, None]:
    """
    Generator for returning directory paths from a walk started at `root` and matching pattern.

    The pattern can contain the asterisk '*' as a wildcard.

    The pattern can contain a directory separator '/' which means
    the last part of the path needs to match these folders.

    Args:
        pattern (str): pattern to match (use * for wildcard)
        root (str): the top level folder to search

    Returns:
         Generator: Paths of folders matching pattern, from root.

    Example:
        ```python
        >>> for folder in find_dirs("/egse/images"):
        ...     assert folder.match('*/egse/images')

        >>> folders = list(find_dirs("/egse/images"))
        >>> assert len(folders)
        ```

    """
    root_arg = root
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"The root argument is not a valid directory: {root_arg}.")

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


def find_files(pattern: str, root: Path | str, in_dir: str = None) -> Generator[Path, None, None]:
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
        >>> for file in find_files(file_pattern, root='.', in_dir=in_dir):
        ...     assert file.match("*lib/CentOS-7/EtherSpaceLink*")

    Args:
        pattern (str) : sorting pattern (use * for wildcard)
        root (Path | str): the top level folder to search
        in_dir (str): the 'leaf' directory in which the file shall be

    Returns:
        Paths of files matching pattern, from root.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        root = root.parent
    if not root.exists():
        raise ValueError(f"The root argument didn't resolve into a valid directory: {root}.")

    exclude_dirs = ("venv", "venv38", ".venv", ".nox", ".git", ".idea", ".DS_Store")

    for path, folders, files in os.walk(root):
        folders[:] = list(filter(lambda x: x not in exclude_dirs, folders))
        if in_dir and not path.endswith(in_dir):
            continue
        for name in fnmatch.filter(files, pattern):
            yield Path(path) / name


def find_file(name: str, root: Path | str, in_dir: str = None) -> Path | None:
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
        >>> file = find_file(file_pattern, root='.', in_dir=in_dir)
        >>> assert file.match("*/lib/CentOS-7/EtherSpace*")

    Args:
        name (str): the name of the file
        root (Path | str): the top level folder to search
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


class WorkingDirectory:
    """
    WorkingDirectory is a context manager to temporarily change the working directory while
    executing some code.

    This context manager has a property `path` which returns the absolute path of the
    current directory.

    Args:
        path (str, Path): the folder to change to within this context

    Raises:
        ValueError: when the given path doesn't exist.

    Example:
        ```python
        with WorkingDirectory(find_dir("/egse/images")) as wdir:
            for file in wdir.path.glob('*'):
                assert file.exists()  # do something with the image files
        ```
    """

    def __init__(self, path):
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
            logger.warning(f"Change back to previous directory failed: {exc}")

    @property
    def path(self):
        """Resolve and return the current Path of the context."""
        return self._temporary_path.resolve()
