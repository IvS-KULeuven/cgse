# Common-EGSE

This is a monorepo with all the code and documentation for the common egse framework.

This repository is organized in two main areas, `libs` and `projects`. The `libs` folder contains library type 
packages like common modules, small generic gui functions, reference frames, etc. and `projects` contains packages 
that build upon these libraries and can be device drivers or stand-alone applications.

In the `libs` folder, we have the following packages:

- `cgse-common`: Common modules and functions for the EGSE framework.
- `cgse-coordinates`: Coordinate systems and transformations.
- `cgse-core`: Core services for the EGSE framework.
- `cgse-gui`: GUI functions for the EGSE framework.

The `projects` folder contains generic and project specific packages. 

We have the following generic packages:

- `cgse-tools`: Tools for the `cgse` command.
- `symetrie-hexapod`: The Symétrie Hexapod drivers. We put this in the generic folder because it is a generic device driver that can be used by different projects.
- `keithley-tempcontrol`: The DAQ6510 data acquisition and logging multimeter from Keithley.

We have the following project specific packages:

- `plato-spw`: The PLATO SpaceWire drivers.
- `plato-fits`: The PLATO FITS plugins.
- `plato-hdf5`: The PLATO HDF5 plugins.

# Installation

The `cgse` package itself doesn't contain any source code, but you can still 
install the `cgse` package. It will `pip` install the `cgse-common`, 
`cgse-core` and `cgse-tools` packages and give you a head start.

```shell
$ pip install cgse
```

Always install in a virtual environment or use `uv`:

```shell
$ uv venv
$ uv pip install cgse
```
