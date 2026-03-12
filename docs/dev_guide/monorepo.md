# The structure of this monorepo

Currently, the structure starts with two main folders in the root, i.e. `libs`
and `projects`. Where
_libs_ contains library type packages like common modules, small generic gui and
tui functions, reference frames, ... and _projects_ contain packages that build
upon these libraries and can be device drivers or stand-alone applications.

There is one package that I think doesn't fit into this picture, that
is `cgse-core`. This is not a library, but a – collection of – service(s). So,
we might want to add a third top-level folder `services` but I also fear that
this again more complicates the monorepo.

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

We will discuss the structure of individual packages in a later section, for now
let's look at the root of the monorepo. The root also contains
a `pyproject.toml` file although this is not a package that will be build and
published. The purpose of this root `pyproject.toml` file is to define
properties that are used to build the full repo or any individual package in it.
In the root folder we will also put some maintenance/management scripts to help
you maintain and bump versions of the projects, build and publish all projects,
create and maintain a changelog etc.

## Package Structure

We try to keep the package structure as standard as possible and consistent over
the whole monorepo. The structure currently is as follows (example from
cgse-common):

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

Note that each library or project is a standalone Python package with its
own `pyproject.toml` file, source code and unit tests.

## Package versions

All packages within the monorepo maintain synchronized versioning, ensuring
consistency across the entire codebase. This unified versioning approach is
managed through the `bump.py` utility script. When executed, this script first
reads the current version from the root `pyproject.toml` file, which serves as
the canonical version source. Based on semantic versioning principles, it then
increments the specified component (major, minor, or patch) according to the
development team's requirements:

- Major version increments (x.0.0) for backward-incompatible API changes
- Minor version increments (0.x.0) for backward-compatible feature additions
- Patch version increments (0.0.x) for backward-compatible bug fixes

After determining the new version number, `bump.py` automatically propagates
this updated version to all library and project configuration files throughout
the monorepo structure, i.e. updating their respective `pyproject.toml`. This
ensures that all components reference the same version number when built or
published, simplifying dependency management and maintaining a clear release
history across the entire project ecosystem.

## The egse namespace

You may have noticed that all packages in this monorepo follow a standardized
structure with source code organized under `src/egse` directories, typically
within subject-specific sub-packages. It's crucial to understand that the `egse`
folder is not a conventional Python package but rather a PEP 420 namespace
package. This distinction carries two critical implications:

1. **No `__init__.py` files in namespace directories**: A namespace package must
   **never** contain an `__init__.py` module at the namespace level. This
   applies universally across all repositories using this namespace. Adding
   an `__init__.py` file to any `egse` directory would compromise the namespace
   mechanism, breaking compatibility with external plugins, extensions, and
   contributions. The absence of this file is what enables Python to recognize
   and properly resolve the distributed nature of the namespace.

2. **Distributed implementation across multiple locations**: Unlike traditional
   packages that exist in a single location, namespace packages can span
   multiple directories distributed across different installed packages. This
   powerful feature allows the `egse` namespace to be extended by various
   packages (both within this monorepo and from external sources like PyPI),
   with Python correctly assembling the complete namespace at runtime by
   discovering and including all relevant directories from the Python path.

This namespace approach enables modular architecture, allowing separate teams to
independently develop components that seamlessly integrate under the
unified `egse` namespace without requiring centralized coordination for package
imports.

## Understanding EGSE vs. CGSE Terminology

You may notice two related acronyms used throughout our documentation, folder
structures, and codebase: **EGSE** and **CGSE**. This deliberate distinction
serves an important purpose:

- **EGSE** (Electrical Ground Support Equipment) refers to the broader domain
  that our software addresses—the physical and software systems used for
  testing, calibration, and validation of instrumentation. This term represents
  the underlying technical concept, which is why we've chosen it as our Python
  namespace (`egse`). Using this domain-specific namespace provides clear
  context for all code functionality while avoiding potential conflicts with
  repository names.

- **CGSE** (Common-EGSE) represents our specific implementation framework
  designed to provide standardized, reusable solutions for EGSE requirements.
  The "Common" prefix emphasizes our framework's core philosophy: creating a
  unified ecosystem of interoperable components that can be shared across
  multiple projects, teams, and institutions. We use CGSE for project naming,
  repository identification, and when referring to the overall framework
  ecosystem.

This naming convention enables clear differentiation between the technical
domain (EGSE) and our specific framework implementation (CGSE). External
packages and device drivers that are designed to integrate with our framework
are labeled as CGSE-compatible to indicate their adherence to our
interoperability standards while still residing within the `egse` namespace for
technical consistency.
