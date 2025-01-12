"""
This script bumps the version of all libs and projects in this monorepo to the version that
is currently in the `pyproject.toml` file in the root folder of the monorepo.

Usage:
    $ python bump.py

Note:
    You are expected to be in the minimal virtual environment associated with this monorepo,
    being a `pyenv` or Poetry environment, or your global environment shall include the tomlkit
    and the rich package.

"""

# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "tomlkit",
#   "rich",
# ]
# ///
import os
import pathlib

import rich
import tomlkit
import tomlkit.exceptions


def get_master_version(master_pyproject_path):
    """Returns the version number of the master project, i.e. cgse."""

    with open(master_pyproject_path, "r") as file:
        data = tomlkit.parse(file.read())

    return data["project"]["version"]


def update_project_version(project_dir, new_version):
    """Updates the version of the subproject."""

    os.chdir(project_dir)

    # Check if the Poetry version is defined, otherwise print a message.

    with open("pyproject.toml", "r") as file:
        data = tomlkit.parse(file.read())

    try:
        data["project"]["version"] = new_version

        with open("pyproject.toml", "w") as file:
            tomlkit.dump(data, file)

    except tomlkit.exceptions.NonExistentKey:
        rich.print(f"[red]\[project.version] is not defined in pyproject.toml in {project_dir}[/]")


def update_all_projects_in_monorepo(root_dir):
    """Updates all pyproject.toml files with the master version number."""

    excluded_subdirs = ["__pycache__", ".venv", ".git", ".idea", "cgse/build", "cgse/dist"]

    master_version = get_master_version(os.path.join(root_dir, "pyproject.toml"))

    rich.print(f"Projects will be bumped to version {master_version}")

    for subdir, dirs, files in os.walk(root_dir):
        if subdir == "." or subdir == ".." or any(excluded in subdir for excluded in excluded_subdirs):
            # rich.print(f"rejected {subdir = }")
            continue
        if "pyproject.toml" in files and subdir != str(root_dir):  # Skip the master pyproject.toml
            print(f"Updating version for project in {subdir}")
            update_project_version(subdir, master_version)


if __name__ == "__main__":
    monorepo_root = pathlib.Path(__file__).parent.resolve()

    cwd = os.getcwd()
    os.chdir(monorepo_root)

    update_all_projects_in_monorepo(monorepo_root)

    os.chdir(cwd)
