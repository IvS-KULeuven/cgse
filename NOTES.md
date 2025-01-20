# The monorepo structure

Currently, the structure starts with two folders in the root, i.e. `libs` and `projects`. Where _libs_ contains library type packages like common modules, small generic gui functions, reference frames, ... and _projects_ contain packages that build upon these libraries and can be device drivers or stand-alone applications.

There is one package that I think doesn't fit into this picture, that is `cgse-core`. This is not a library, but a – collection of – service(s). So, we might want to add a third top-level folder `services` but I also fear that this again more complicates the monorepo.

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
│   ├── cgse-coordinates/
│   └── cgse-gui/
│
└── projects/
    ├── generic/
    │   ├── cgse-tools/
    │   └── symetrie-hexapod/
    └── plato/
        ├── plato-spw/
        ├── plato-fits/
        └── plato-hdf5/
```

We will discuss the structure of individual packages in a later section, for now let's look at the root of the monorepo. The root also contains a `pyproject.toml` file although this is not a package that will be build and published. The purpose of this root `pyproject.toml` file is to define properties that are used to build the full repo or any individual package in it. In the root folder we will also put some maintenance/management scripts to help you maintain and bump versions of the projects, build and publish all projects, create and maintain a changelog etc.

# Package Structure

We try to keep the package structure as standard as possible and consistent over the whole monorepo. The structure currently is as follows (example from cgse-common):

```
├── README.md
├── dist
│   ├── cgse_common-2023.1.4-py3-none-any.whl
│   └── cgse_common-2023.1.4.tar.gz
├── pyproject.toml
├── src/
│   └── egse/  # namespace
│       ├── modules (*.py)
│       └── <sub-packages>/
└── tests/
    ├── data
    └── pytest modules (test_*.py)
```

Note that each library or project is a standalone Poetry package with its own `pyproject.toml` file, source code and unit tests.

# Package versions

All packages in the monorepo will have the same version. This can be maintained with the `bump.py` script. This script will read the version from the `pyproject.toml` file at the root of the monorepo and propagate the version to all libs and projects in the monorepo. Note that you –for now– will have to update the version number in the `pyproject.toml` file  located at the monorepo root folder manually. 


# Build and Publish

Building a source distribution and a wheel for your project is as easy as running the following command:
```
$ pipx run build
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling
* Getting build dependencies for sdist...
* Building sdist...
* Building wheel from sdist
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling
* Getting build dependencies for wheel...
* Building wheel...
```
Make sure you have updated/bumped the version number in the `pyproject.toml`. Publishing your package on PyPI needs some more preparation, since you need to prepare a token that allows you to upload your project to PyPI. Publishing itself is a peace of cake when the credentials have been configured correctly. Poetry will also automatically take the latest version to publish.
```
$ pipx run twine publish
Publishing cgse-common (2023.1.5) to PyPI
 - Uploading cgse_common-2023.1.5-py3-none-any.whl 100%
 - Uploading cgse_common-2023.1.5.tar.gz 100%
```

# The egse namespace

You might have notices that all packages in this monorepo have a `src/egse` folder in which they maintain their source code, preferably in a sub-package. Note that the `egse` folder is not a normal Python package but a namespace. There are two important facts you need to remember about namespaces:

1. A namespace package **does not** contain an `__init__.py` module, never, in any of the packages in this or any other repo. If you place an `__init__.py` module in one of your `egse` package folders, you will break the namespace and therefore also the external contributions in plugins etc.
2. A namespace package is spread out over several directories that can reside in different packages as distributed by PyPI.

# Questions

What is the meaning of the common egse root folder in this monorepo and when the packages are installed through PyPI?

* do we still need `get_common_egse_root()`

    NO, this has nothing to do with a generic common egse and also the concept of a project root folder doesn't really work for PyPI projects, especially in a monorepo. What might work in this specific case is to use the egse namespace as a root and find folders and files in the folders that make up the namespace.

* what is the Projects root directory?

    This folder basically contains device implementations and plugins for e.g. the storage manager.
