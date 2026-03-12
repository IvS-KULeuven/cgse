"""
This module manages files that have a counter in their filename.
"""

__all__ = [
    "counter_exists",
    "counter_filename",
    "get_next_counter",
    "new_counter",
]

from pathlib import Path

from egse.config import find_files
from egse.log import logger


def counter_filename(location: Path, filename: Path | str) -> Path:
    """
    Creates an absolute filename to be used as a counter file. A counter file usually has a 'count' extension
    but that is not enforced by this module. The location can be a relative path, even '.' or '..' are accepted.

    Args:
        location: the location of the counter file.
        filename: the name of the counter file, use the '.count' extension.

    Returns:
         An absolute filename.

    Note:
        If the file doesn't exist, it is NOT created.

    """
    return (location / filename).resolve()


def counter_exists(filename: Path) -> bool:
    """
    Returns True if the given file exists, False otherwise.

    Args:
        filename: path of the counter file

    Returns:
        True if the given filename exists, False otherwise.

    Raises:
        OSError: might be raised by Path.

    Note:
        No checking is done if the file is indeed a counter file, i.e. if it contains the correct content.
          So, this function basically only checks if the given Path exists and if it is a regular file.

    """
    return filename.exists() if filename.is_file() else False


def new_counter(filename: Path, pattern: str) -> int:
    """
    Create a counter based on the files that already exist for the given pattern.

    Args:
        filename: the name of the counter file
        pattern: a pattern to match the filenames

    Returns:
        The next counter value as an integer.
    """
    if not counter_exists(filename):
        location = filename.parent
        counter = determine_counter_from_dir_list(location, pattern)
        _write_counter(counter, filename)
    else:
        counter = get_next_counter(filename)

    return counter


def _write_counter(counter: int, filename: Path):
    """
    Overwrites the given counter in the given file. The file contains nothing else then the counter.
    If the file didn't exist before, it will be created.

    Args:
        counter: the counter to save
        filename: the file to which the counter shall be saved
    """
    with filename.open("w") as fd:
        fd.write(f"{counter:d}")


def _read_counter(filename: Path) -> int:
    """
    Reads a counter from the given file. The file shall only contain the counter which must
    be an integer on the first line of the file. If the given file doesn't exist, 0 is returned.

    Args:
        filename: the full path of the file containing the counter

    Returns:
        The counter that is read from the file or 0 if file doesn't exist.
    """
    try:
        with filename.open("r") as fd:
            counter = fd.read().strip()
    except FileNotFoundError:
        counter = 0
    return int(counter or 0)


def get_next_counter(filename: Path) -> int:
    """
    Read the counter from a dedicated file, add one and save the counter back to the file.

    Args:
        filename: full pathname of the file that contains the required counter

    Returns:
        The value of the next counter, 1 if no previous files were found or if an error occurred.

    Note:
        This will create the counter file if it doesn't exist.
    """

    counter = _read_counter(filename)
    counter += 1
    _write_counter(counter, filename)

    return counter


def determine_counter_from_dir_list(location: Path | str, pattern: str, index: int = -1) -> int:
    """
    Determine counter for a new file at the given location and with the given pattern.
    The next counter is determined from the sorted list of files that match the given pattern.

    Args:
        location: Location where the file should be stored.
        pattern: Pattern for the filename.
        index: the location of the counter in the filename after it is split on '_' [default=-1]

    Returns:
        The value of the next counter, 1 if no previous files were found or if an error occurred.
    """

    files = sorted(find_files(pattern=pattern, root=location))

    # No filenames found showing the given pattern -> start counting at 1

    if len(files) == 0:
        return 1

    last_file = files[-1]

    parts = last_file.name.split("_")

    try:
        # Observation files have the following pattern:
        #  <test ID>_<lab ID>_<setup ID>_<storage mnemonic>_<day YYYYmmdd>_<time HHMMSS>[_<counter>]
        #
        # Daily files:
        #  <day>_<site ID>_<storage mnemonic>[_<counter>]
        #
        # Any file:
        #  the counter is assumed to be the last part before the file extension and is preceded by an underscore.
        #  <anything here>_counter>.<extension>

        counter = int(parts[index].split(".")[0]) + 1
        logger.debug(f"{counter = }")
        return counter

    except ValueError:
        logger.warning("ValueError", exc_info=True)
        return 1
