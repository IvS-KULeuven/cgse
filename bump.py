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

import os
import pathlib
import subprocess

import rich
import tomlkit
import tomlkit.exceptions


def get_master_version(master_pyproject_path):
    """Returns the version number of the master project, i.e. cgse."""

    with open(master_pyproject_path, 'r') as file:
        data = tomlkit.parse(file.read())

    return data['tool']['poetry']['version']


def update_project_version(project_dir, new_version):
    """Updates the version of the subproject."""

    os.chdir(project_dir)

    # Check if the Poetry version is defined, otherwise print a message.

    with open("pyproject.toml", 'r') as file:
        data = tomlkit.parse(file.read())

    try:
        _ = data['tool']['poetry']['version']
        subprocess.run(['poetry', 'version', new_version], check=True)
    except tomlkit.exceptions.NonExistentKey:
        rich.print(f"[red]\[tool.poetry.version] is not defined in pyproject.toml in {project_dir}[/]")
    except subprocess.CalledProcessError:
        rich.print(f"[red]\[tool.poetry] is not defined in pyproject.toml in {project_dir}[/]")


def update_all_projects_in_monorepo(root_dir):
    """Updates all pyproject.toml files with the master version number."""

    master_version = get_master_version(os.path.join(root_dir, 'pyproject.toml'))

    rich.print(f"Projects will be bumped to version {master_version}")

    for subdir, dirs, files in os.walk(root_dir):
        if subdir == '.' or subdir == '..' or subdir == '__pycache__':
            continue
        if 'pyproject.toml' in files and subdir != str(root_dir):  # Skip the master pyproject.toml
            print(f"Updating version for project in {subdir}")
            update_project_version(subdir, master_version)


if __name__ == "__main__":

    monorepo_root = pathlib.Path(__file__).parent.resolve()

    cwd = os.getcwd()
    os.chdir(monorepo_root)

    update_all_projects_in_monorepo(monorepo_root)

    os.chdir(cwd)
