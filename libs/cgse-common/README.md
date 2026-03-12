
![PyPI - Version](https://img.shields.io/pypi/v/cgse-common)
![Supported OS](https://img.shields.io/badge/Supported%20OS-Linux%20%7C%20macOS-blue)
![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FIvS-KULeuven%2Fcgse%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)
![PyPI - Wheel](https://img.shields.io/pypi/wheel/cgse-common)

# Generic Functionality used in the Common-EGSE

This package 'cgse-common' contains functionality that is used by all `cgse` sub-packages, but it is designed to be a stand-alone generic package that can be used also in any other project.


## Installation

Install the package using pip:

    $ pip install cgse-common


## Usage

All functionality resides in the package `egse`. As an example, if you need a standard way to format your timestamp, use the `format_datetime()` function from `egse.system`:

    >>> from egse.system import format_datetime
    >>> print(format_datetime())
    2023-10-10T08:41:51.937+0000


## Included Functionality

A non-comprehensive list of available functionality:

### Functionality of General Use

* **egse.bits**: contains a number of convenience functions to work with bits, bytes and integers
* **egse.decorators**: a collection of useful decorator functions
* **egse.reload**: a slightly better approach to reloading modules and function than the standard importlib.reload() function.
* **egse.resource**: provides convenience functions to use resources in your code without the need to specify an absolute path
* **egse.system**: defines convenience functions that provide information on system specific functionality like, file system interactions, timing, operating system interactions, etc.
* **egse.version**: functionality to retrieve the package version information
