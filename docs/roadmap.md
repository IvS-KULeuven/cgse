---
hide:
  - navigation
---

# Roadmap

Don't worry, the feature set will grow..

## Features

### The `cgse` Command

Provide a `cgse` command that is extensible with new commands and command groups:

- [x] a command to initialise your environment.
- [x] a command to check versions of installed packages.
- [ ] a command to check your installation, settings, setups, environment ..
- [x] a command group to handle core services
- [x] a command to list running CGSE processes.
- [x] device drivers shall be able to plug in their own command groups.

### Settings, Setup and the environment

- [x] A modular/decomposed `settings.yaml` file.
- [x] A clear set of environment variables.
- [ ] automatic submit of new Setups to GitHub.
- [ ] a TUI for inspecting the loaded Setup.

### Common functionality

- [ ] Reference Frames and coordinate transformations -> Graphs
- [ ] Metrics for all devices will be handled using InfluxDB
- [ ] Use of Grafana to visualize the metrics

## Devices

- [x] The Symétrie Hexapods: PUNA, ZONDA, JORAN
- [ ] The Keithley Data Acquisition Multimeter
- [ ] The Lakeshore temperature controller

## Projects

- [ ] Ariel HDF5 format plugin
- [ ] Ariel FITS format plugin

## GUIs and TUIs

- [ ] A Process Manager TUI
- [ ] `tui-executor` integration

## Removals

- [ ] The `get_common_egse_root()` is of no use anymore and needs to be removed or replaced in 
  some cases.

## Testing

- [ ] Add proper unit tests for all packages – using `pytest`
- [ ] Add a CI test suite
- [ ] Use GitHub Actions for running tests before merging
