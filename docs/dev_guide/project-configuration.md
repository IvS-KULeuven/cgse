# Project Configuration

In this section we will explain the `pyproject.toml` contents and why we have taken certain
decisions.

## Python version dependency

Since we have adopted [`nox`](https://nox.thea.codes/en/stable/) as our platform to run the unit
tests for different Python environments/versions, the `pyproject.toml` file contains dependency
specifiers for Python versions. The main packages that have different dependencies based on the
Python version are: `numpy`, `pandas`, and `pyzmq`. The dependencies are specified in the
`project.dependencies` table in the `pyproject.toml` file of the `cgse-common` project.

Then, there is the case where the `importlib.metadata` entry_points used to return a dict-like 
object until Python 3.9, and a collection of entry points as of 3.10. The deprecated interface 
was completely removed as of Python 3.12. We have now implemented a check in `egse.plugin` that 
imports the `import_metadata` backport for Python < 3.10. This backport package is only 
installed when using Python 3.9 as is specified in the `pyproject.toml` file of the `cgse-common`.

## Dependency Groups

Dependency groups are a way to organize optional dependencies that aren't required for basic package
functionality. Dependency groups are not installed by default. They are only installed when
explicitly requested.

!!! warning

    The `[dependency-groups]` section is part of uv's own configuration system rather than a 
    standard Python packaging concept. It is different from the `[project.optional-dependencies]`
    section that follows Python's packaging standards.

By default, uv includes the `dev` dependency group in the environment, e.g. during `uv run`
or `uv sync`. You can define a group to be a default group by adding it to `tool.uv.default-groups`.
For example, when the `docs` dependency group should also be a default group, add

```text
[tool.uv]
default-groups = ["dev", "docs"]
```
