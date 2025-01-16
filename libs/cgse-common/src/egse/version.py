"""
This module defines the version for the Common-EGSE release. Whenever a version number
or the release number is needed, this module shall be imported. The version and release
number is then available as:

    >>> import egse.version
    >>> print(f"version = {egse.version.VERSION}")

The actual numbers are updated for each release in the `settings.yaml` configuration file.

"""
from __future__ import annotations

# WARNING: Make sure you are not importing any `egse` packages at the module level.
# This module is magically loaded by pip to determine the VERSION number before the
# package has been installed (see pyproject.py).
# Any imports from an 'egse' package will result in a ModuleNotFound error.

import os
import subprocess
from pathlib import Path

from egse.system import get_package_location

HERE = Path(__file__).parent.resolve()

__all__ = [
    "get_version_installed",
    "get_version_from_git",
    "get_version_from_settings",
    "VERSION",
]


def get_version_from_settings_file_raw(group_name: str, location: Path | str = None) -> str:
    """
    Reads the VERSION field from the `settings.yaml` file in raw mode, meaning the file
    is not read using the PyYAML module, but using the `readline()` function of the file
    descriptor.

    Args:
        group_name: major group name that contains the VERSION field, i.e. Common-EGSE or PLATO_TEST_SCRIPTS.
        location: the location of the `settings.yaml` file or None in which case the location of this file is used.

    Raises:
        A RuntimeError when the group_name is incorrect and unknown or the VERSION field is not found.

    Returns:
        The version from the `settings.yaml` file as a string.
    """
    basedir = location or os.path.dirname(__file__)

    with open(os.path.join(basedir, "settings.yaml"), mode="r") as yaml_fd:
        line = yaml_fd.readline()
        if not line.startswith(group_name):
            raise RuntimeError(f"Incompatible format for the settings.yaml file, should start with '{group_name}'")

        line = yaml_fd.readline().lstrip()
        if not line.startswith("VERSION"):
            raise RuntimeError("Incompatible format for the settings.yaml file, no VERSION found.")
        _, version = line.split(":")

        # remove possible trailing comment starting with '#'
        version, *_ = version.split("#")
        version = version.strip()

    return version


def get_version_from_settings(group_name: str, location: Path = None):
    """
    Reads the VERSION field from the `settings.yaml` file. This function first tries to load the proper Settings
    and Group and if that fails uses the raw method.

    Args:
        group_name: major group name that contains the VERSION field, i.e. Common-EGSE or PLATO_TEST_SCRIPTS.
        location: the location of the `settings.yaml` file or None in which case the location of this file is used.

    Raises:
        A RuntimeError when the group_name is incorrect and unknown or the VERSION field is not found.

    Returns:
        The version from the `settings.yaml` file as a string.
    """
    from egse.settings import Settings, SettingsError

    try:
        settings = Settings.load(group_name, location=location)
        version = settings.VERSION
    except (ModuleNotFoundError, SettingsError):
        version = get_version_from_settings_file_raw(group_name, location=location)

    return version


def get_version_from_git(location: str = None):
    """
    Returns the Git version number for the repository at the given location.

    The returned string has the following format: YYYY.X.Y+REPO.TH-N-HASH, where:

    * YYYY is the year
    * X is the major version number and equal to the week number of the release
    * Y is the minor version patch number
    * REPO is the name of the repository, i.e. CGSE or TS
    * TH is the name of the test house, i.e. CSL1, CSL2, IAS, INTA, SRON
    * N is the number of commits since the release
    * HASH is the Git hash number of the commit

    Args:
        location: The absolute path of the root or a sub-folder of the repo.

    Returns:
        The Git version number.
    """
    from egse.system import chdir

    location = location or Path().cwd()

    with chdir(location):
        try:
            std_out = subprocess.check_output(
                ["git", "describe", "--tags", "--long", "--always"], stderr=subprocess.PIPE
            )
            version = std_out.strip().decode("ascii")
            if "cgse" not in version.lower() and "ts" not in version.lower():
                version = None
        except subprocess.CalledProcessError as exc:
            version = None

    return version


def get_version_installed(package_name: str) -> str:
    """
    Returns the version that is installed, i.e. read from the metadata in the import lib.

    Args:
        package_name: the name of the installed package, e.g. cgse or cgse-ts

    Returns:
        The version of the installed repo.
    """
    from egse.system import chdir

    with chdir(Path(__file__).parent):
        from importlib.metadata import version, PackageNotFoundError

        try:
            version = version(package_name)
        except PackageNotFoundError as exc:
            version = None

    return version


# The version will be the installed version of the `egse.common`, because this is the package that is guaranteed
# to be installed, and not necessarily `cgse`.

VERSION = get_version_installed('cgse-common')

# The __PYPI_VERSION__ is the version number that will be used for the installation.
# The version will appear in PyPI and also as the `installed version`.

__PYPI_VERSION__ = VERSION.split('+')[0]


if __name__ == "__main__":
    import rich
    from egse.plugin import entry_points

    if VERSION:
        rich.print(f"CGSE version in Settings: [bold default]{VERSION}[/]")

    if git_version := get_version_from_git(os.getcwd()):
        rich.print(f"git version (current project) = [bold default]{git_version}[/]")

    for ep in entry_points("cgse.version"):
        if installed_version := get_version_installed(ep.name):
            rich.print(f"Installed version for {ep.name}= [bold default]{installed_version}[/]")
