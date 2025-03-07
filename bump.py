"""
This script bumps the version of all libs and projects in this monorepo to the version that
is currently in the `pyproject.toml` file in the root folder of the monorepo.

Usage:
    $ python bump.py <part>

where `<part>` should be 'patch', 'minor', or 'major'.

Note:
    You are expected to be in the minimal virtual environment associated with this monorepo,
    being a `pyenv` or Poetry environment, or your global environment shall include the tomlkit
    and the rich package.

    Alternatively (and preferably) you can use `uv run build.py <part>` to run this script.

"""

# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "tomlkit",
#   "rich",
#   "typer",
# ]
# ///
import os
import pathlib
import sys

import rich
import tomlkit
import tomlkit.exceptions
import typer


def bump_version(version, part='patch'):
    major, minor, patch = map(int, version.split('.'))

    if part == 'major':
        major += 1
        minor = 0
        patch = 0
    elif part == 'minor':
        minor += 1
        patch = 0
    elif part == 'patch':
        patch += 1
    else:
        raise ValueError("Part must be 'major', 'minor', or 'patch'")

    return f"{major}.{minor}.{patch}"


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


def update_all_projects_in_monorepo(root_dir: pathlib.Path, part: str, dry_run: bool = False, verbose: bool = True):
    """
    Updates all pyproject.toml files with the master version number.

    Parameters:
        root_dir:
        part:
        dry_run:
        verbose:
    """

    excluded_subdirs = ["__pycache__", ".venv", ".git", ".idea", "cgse/build", "cgse/dist"]

    master_version = get_master_version(os.path.join(root_dir, "pyproject.toml"))

    new_version = bump_version(master_version, part=part)

    rich.print(f"Projects will be bumped from version {master_version} to version {new_version}")

    for subdir, dirs, files in os.walk(root_dir):
        if subdir == "." or subdir == ".." or any(excluded in subdir for excluded in excluded_subdirs):
            # rich.print(f"rejected {subdir = }")
            continue
        if subdir != str(root_dir):
            # continue  # skip the root project file
            pass
        if "pyproject.toml" in files:
            verbose and print(f"Updating version for project in {subdir}")
            if not dry_run:
                update_project_version(subdir, new_version)


app = typer.Typer()


@app.command()
def main(part: str, dry_run: bool = False, verbose: bool = True):

    monorepo_root = pathlib.Path(__file__).parent.resolve()

    cwd = os.getcwd()
    os.chdir(monorepo_root)

    try:
        update_all_projects_in_monorepo(monorepo_root, part, dry_run, verbose)
    except ValueError as exc:
        rich.print(f"[red]{exc.__class__.__name__}: {exc}[/]")
        sys.exit(1)
    finally:
        os.chdir(cwd)


if __name__ == "__main__":
    app()
