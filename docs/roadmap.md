---
hide:
    - navigation
---

# Roadmap

Don't worry, the feature set will grow ...

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
- [x] Use of Grafana to visualize the metrics

## Core Services

- [ ] Process Manager needs to be added with optimised design and performance
- [ ] Synoptic Manager
- [x] Distributed Service Registry
- [x] dynamic port assignment for all services -> service registry

## Devices

- [x] The Symétrie Hexapods: PUNA, ZONDA, JORAN
- [x] The Keithley Data Acquisition Multimeter
- [x] The Lakeshore temperature controller

## Projects

- [ ] Ariel HDF5 format plugin
- [ ] Ariel FITS format plugin

## GUIs and TUIs

- [ ] A Process Manager TUI
- [ ] `tui-executor` integration

## Maintenance and refactoring

- [ ] Allow core services to register and/or re-register to another core service as a listener
- [ ] The storage manager shall be able to restore registrations from 
  devices after a restart/crash. This means the registration to the Storage 
  manager needs to be persistent -> SQLite ?
- [ ] Refactor the commanding protocol
- [ ] The Proxy and Protocol classes should be refactored for full dynamic commanding. Eliminate the
  use of command YAML files, replace `dynamic_interface` with `dynamic_command`.
- [ ] Introduce asyncio into the commanding protocol, e.g. `get_status()` 
  and `get_housekeeping()` shall be handled asynchronously.
- [x] GlobalState Setup needs some redesign, especially `GlobalState.setup` 
  which should not consult
  the configuration manager by default.

## Removals

- [x] The `get_common_egse_root()` is of no use anymore and needs to be 
  removed or replaced in some
  cases.

## Testing

- [x] Add unit testing with `nox` running tests for Python 3.9, 3.10, 3.11, and 3.12
- [ ] Add proper unit tests for all packages – using `pytest`
- [ ] Add a CI test suite
- [ ] Add GitHub Action to check proper formatting of all the code in a pull 
  request
- [ ] Add GitHub Actions for running tests before merging
