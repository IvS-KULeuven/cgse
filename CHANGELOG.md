
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased](https://github.com/IvS-KULeuven/cgse/compare/v0.17.1...HEAD)

### Fixed
- ...
### Added
- ...

## [v0.17.1](https://github.com/IvS-KULeuven/cgse/compare/v0.17.0...v0.17.1) – 20/11/2025

### Fixed
- Fixed a missing expanduser(). Apparently a `pathresolve()` doesn't handle the '`~`' character.
- Fixed `env_var()` which is a context manager for temporarily setting an environment variable. It uses `setup_env()` 
  to update the environment before and after the `yield`, but `setup_env()` only initializes once.
- Fixed unit tests for settings, setup, and env.

### Changed
- Some of the debug messages in settings are now filtered behind the VERBOSE_DEBUG flag.

## [v0.17.0](https://github.com/IvS-KULeuven/cgse/compare/v0.16.14...v0.17.0) – 20/11/2025

### Added
- Added this CHANGELOG file. [#209](https://github.com/IvS-KULeuven/cgse/pull/209)
- Added an initial implementation of the ARIEL Telescope Control Unit (TCU). This is a separate package in this 
  monorepo that is located at `projects/ariel/ariel-tcu`. The package will be added to PyPI as `ariel-tcu`. [#178](https://github.com/IvS-KULeuven/cgse/pull/178)
- Added a `read_string()` method to the `DeviceTransport` and `AsyncDeviceTransport` classes. [#209](https://github.com/IvS-KULeuven/cgse/pull/209)
### Fixed
- Fixed the `sm_cs` for the missing `--full` cli argument. [#204](https://github.com/IvS-KULeuven/cgse/pull/204)
- Fixed the configuration of the InfluxDB client. The client can now be fully configured with environment variables 
  if needed. [#206](https://github.com/IvS-KULeuven/cgse/pull/206)
### Changed
- Improved initialization of the process environment with `setup_env()`. [#208](https://github.com/IvS-KULeuven/cgse/pull/208)
- The configuration manager now also re-registers the obsid table to the storage. [#207](https://github.com/IvS-KULeuven/cgse/pull/207)
- The `cgse` subcommand to start the notification hub is changed from `not` to `nh`. Use `cgse nh [start|stop|status]`.  [#209](https://github.com/IvS-KULeuven/cgse/pull/209)
- The environment variables that contain a path can start with a tilde '`~`' which will be expanded to the user's 
  home directory when used. [#204](https://github.com/IvS-KULeuven/cgse/pull/204)
### Docs
- Documentation updates for the Python version, the CLI `cgse` subcommands,  environment and the introduction of `dotenv`, ...
- Updated information on the use of `dotenv` in the developer guid.
- Added information on the environment variables to the user guide.

## [0.16.14](https://github.com/IvS-KULeuven/cgse/compare/v0.16.13...v0.16.14) – 24/10/2025

### Added
- Added `cmd_string_func` parameter to the `@dynamic_command` interface. Use this parameter if you need to create a fancy command string from the arguments passed into the command function.

## [0.16.13](https://github.com/IvS-KULeuven/cgse/compare/v0.16.12...v0.16.13) – 23/10/2025

### Changed
- Improved unit tests for the `mixin.py` module.

## [0.16.12](https://github.com/IvS-KULeuven/cgse/compare/v0.16.11...v0.16.12) – 21/10/2025

### Fixed
- Fixed a bug in starting the puna proxy.

## [0.16.11](https://github.com/IvS-KULeuven/cgse/compare/v0.16.10...v0.16.11) – 21/10/2025

### Fixed
- Fixed starting the hexapod GUI by specifying a device identifier.
- Fixed registration and connection of the notification hub.
### Added
- Added a dependency for the `dotenv` module.
### Changed
- The PUNA GUI script now starts as a Typer app.
- The `get_port_number()` in `zmq_ser.py` now returns 0 (zero) on error.
- Improved logging for the Symétrie hexapods.
- Introduced the `VERBOSE_DEBUG` environment variable that can be used to restrict debug logging messages only when 
  this environment variable is set. Use this for very verbose debug logging.

## [0.16.10](https://github.com/IvS-KULeuven/cgse/compare/v0.16.9...v0.16.10) – 03/10/2025

### Changed
- Renamed Settings for external logger from `TEXTUALOG_*` to `EXTERN_LOG_*`.
- The heartbeat ZeroMQ protocol now uses ROUTER-DEALER instead of REQ-REP. This was needed because too often we got an invalid state for the REQ sockets after one of the services went down.

## [0.16.9](https://github.com/IvS-KULeuven/cgse/compare/v0.16.8...v0.16.9) – 02/10/2025

### Removed
- Removed caching from the async registry client.

## [0.16.8](https://github.com/IvS-KULeuven/cgse/compare/v0.16.7...v0.16.8) – 02/10/2025

### Fixed
- Fixed re-registration for the async registry client.

## [0.16.7](https://github.com/IvS-KULeuven/cgse/compare/v0.16.6...v0.16.7) – 01/10/2025

### Fixed
- Fixed re-registration problem in the service registry.
### Changed
- Read the Settings in the `__init__.py` files where possible. Do not spread Settings in all modules of a package.

## [0.16.6](https://github.com/IvS-KULeuven/cgse/compare/v0.16.5...v0.16.6) – 30/09/2025

### Fixed
- Fixed timeouts for Proxy (sub)classes to seconds instead of milliseconds. We strive to have all timeout in seconds and only convert to milliseconds when needed for a library call.

## [0.16.5](https://github.com/IvS-KULeuven/cgse/compare/v0.16.4...v0.16.5) – 29/09/2025

### Changed
- The service type for the notification hub is now `NH_CS` instead of `NOTIFY_HUB`.
- Remove the leading dot '`.`' from all startup log filenames. Startup log files are log files per `cgse` subcommand that are located in the `LOG_FILE_LOCATION`. You will find a log file there for the `start` and the `stop` for each core service or device control server.

## [0.16.4](https://github.com/IvS-KULeuven/cgse/compare/v0.16.3...v0.16.4) – 29/09/2025

### Added
- Added the `bool_env()` function in `env.py`.
### Changed
- The listeners functionality has been transferred to the notification hub and services subscribe to this notification service.
- Log messages to the `general.log` file now contain the logger name.
### Removed
- Remove the listener notification from the configuration manager. 
- Remove listener registration from the storage manager and the process manager.

## [0.16.3](https://github.com/IvS-KULeuven/cgse/compare/v0.16.2...v0.16.3) – 19/09/2025

### Fixed
- Fixed a circular import problem in `system.py`.

## [0.16.2](https://github.com/IvS-KULeuven/cgse/compare/v0.16.1...v0.16.2) – 19/09/2025

### Changed
- The output of startup scripts is now redirected to the log location.

## [0.16.1](https://github.com/IvS-KULeuven/cgse/compare/v0.16.0...v0.16.1) – 19/09/2025

### Changed
- Use the `get_endpoint()` function in Proxy subclasses.
- Define constants from settings with proper defaults.
- Cleanup port numbers for core services in Settings. All core services now have a fixed port number, which can be 
  overwritten in the local settings file.
- When `port == 0` use the service registry to get the endpoint.

## [0.16.0](https://github.com/IvS-KULeuven/cgse/compare/v0.15.1...v0.16.0) – 17/09/2025

### Added
- Added a `deregister` subcommand to the service registry. Usage: `cgse reg deregister <SERVICE_TYPE>`.
### Fixed
- Fixed proper sorting of cgse subcommands.
- Fixed port numbers for core services.
### Changed
- Proxies now handle fixed port numbers properly.
- Renamed `cgse` subcommands `registry` →  `reg`, `notify` →  `not`.
