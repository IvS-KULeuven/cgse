# The structure of this monorepo

Currently, the structure starts with two main folders in the root, i.e. `libs` and `projects`. Where
_libs_ contains library type packages like common modules, small generic gui and tui functions,
reference frames, ... and _projects_ contain packages that build upon these libraries and can be
device drivers or stand-alone applications.

There is one package that I think doesn't fit into this picture, that is `cgse-core`. This is not a
library, but a – collection of – service(s). So, we might want to add a third top-level
folder `services` but I also fear that this again more complicates the monorepo.

Anyway, the overall structure of the monorepo is depicted below:

```
cgse/
│── pyproject.toml
├── libs/
│   ├── cgse-common/
│   │   ├── src/
│   │   ├── tests/
│   │   └── pyproject.toml
│   ├── cgse-core/
│   │   ├── src/
│   │   ├── tests/
│   │   └── pyproject.toml
│   ├── cgse-coordinates/
│   │   ├── src/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── cgse-gui/
│   │   ├── src/
│   │   ├── tests/
│   │   └── pyproject.toml
│
└── projects/
    ├── generic/
    │   ├── cgse-tools/
    │   ├── keithley-tempcontrol/
    │   └── symetrie-hexapod/
    └── plato/
        ├── plato-spw/
        ├── plato-fits/
        └── plato-hdf5/
```

We will discuss the structure of individual packages in a later section, for now let's look at the
root of the monorepo. The root also contains a `pyproject.toml` file although this is not a package
that will be build and published. The purpose of this root `pyproject.toml` file is to define
properties that are used to build the full repo or any individual package in it. In the root folder
we will also put some maintenance/management scripts to help you maintain and bump versions of the
projects, build and publish all projects, create and maintain a changelog etc.

## Package Structure

We try to keep the package structure as standard as possible and consistent over the whole monorepo.
The structure currently is as follows (example from cgse-common):

```
├── README.md
├── pyproject.toml
├── src/
│   └── egse/  # namespace, i.e. there shall not be a __init__.py in this folder
│       ├── modules (*.py)
│       └── <sub-packages>/  # these do contain a __init__.py
└── tests/
    ├── data
    └── pytest modules (test_*.py)
```

Note that each library or project is a standalone Python package with its own `pyproject.toml` file,
source code and unit tests.

## Package versions

All packages in the monorepo will have the same version. This can be maintained with the `bump.py`
script. This script will read the version from the `pyproject.toml` file at the root of the monorepo
and propagate the version to all libs and projects in the monorepo. Note that you –for now– will
have to update the version number in the `pyproject.toml` file located at the monorepo root folder
manually.

## The egse namespace

You might have notices that all packages in this monorepo have a `src/egse` folder in which they
maintain their source code, preferably in a sub-package. Note that the `egse` folder is not a normal
Python package but a namespace. There are two important facts you need to remember about namespaces:

1. A namespace package **does not** contain an `__init__.py` module, never, in any of the packages
   in this or any other repo. If you place an `__init__.py` module in one of your `egse` package
   folders, you will break the namespace and therefore also the external contributions in plugins
   etc.
2. A namespace package is spread out over several directories that can reside in different packages
   as distributed by PyPI.

## `egse` versus `cgse`

Why is there sometimes `egse` and sometimes `cgse` used in documentation, folder names etc.? The
acronym EGSE stands for Electric Ground Support Equipment and the CGSE stands for Common-EGSE. So,
the latter, CGSE, is what we use for the project name, to emphasise its common purpose as a
framework for testing instrumentation and for external packages and device drivers to emphasise that
they are intended to be common and work well with the CGSE framework. The `egse` is what the
software is about, the electric ground support equipment, and therefore we use this for the
namespace, i.e. the root of the library and projects. Using `egse` as the namespace also avoid 
any conflicts with the `cgse` monorepo name.
