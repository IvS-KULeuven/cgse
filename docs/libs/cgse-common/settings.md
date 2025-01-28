# The Settings

The Settings class contains all static information needed to configure your system, the environment you are using
and the test equipment. The Settings also contain all the IP addresses and port number for all the known devices,
together with other static information like the device name, default settings for the device like speed, timeout, delay
time, firmware version, etc. We will go into more details about the content later, let’s now first look at the format
and usage of the Settings.

## Loading the Settings

The Settings can be loaded as follows:

```python
>>> from egse.settings import Settings
>>> settings = Settings.load()
```

The `settings` object will be a dictionary where the keys are the top-level groups that are defined in the settings
for each package. For a system that has only `cgse-common` and `cgse-core` installed, the `settings` will contain
something like this:

```text
>>> print(settings)
Settings
├── PACKAGES
│   ├── CGSE_COMMON: Common classes, functions, decorators, etc. for the CGSE
│   └── CGSE_CORE: The core services of the CGSE
├── SITE
│   ├── ID: LAB42
│   ├── SSH_SERVER: localhost
│   └── SSH_PORT: 22
├── PROCESS
│   └── METRICS_INTERVAL: 10
├── Logging Control Server
│   ├── PROTOCOL: tcp
│   ├── HOSTNAME: localhost
│   ├── LOGGING_PORT: 7000
│   ├── COMMANDING_PORT: 7001
│   ├── METRICS_PORT: 7003
│   ├── MAX_NR_LOG_FILES: 20
│   ├── MAX_SIZE_LOG_FILES: 20
│   ├── TEXTUALOG_IP_ADDRESS: 127.0.0.1
│   └── TEXTUALOG_LISTENING_PORT: 19996
├── Configuration Manager Control Server
│   ├── PROTOCOL: tcp
│   ├── HOSTNAME: localhost
│   ├── COMMANDING_PORT: 6000
│   ├── MONITORING_PORT: 6001
│   ├── SERVICE_PORT: 6002
│   ├── METRICS_PORT: 6003
│   ├── DELAY: 1
│   └── STORAGE_MNEMONIC: CM
└── Storage Control Server
    ├── PROTOCOL: tcp
    ├── HOSTNAME: localhost
    ├── COMMANDING_PORT: 6100
    ├── MONITORING_PORT: 6101
    ├── SERVICE_PORT: 6102
    ├── METRICS_PORT: 6103
    └── DELAY: 1
```

If you only need the settings for a particular component, specify that group's name:

```python
>>> storage_settings = Settings.load("Storage Control Server")

>>> print(storage_settings)
Storage
Control
Server
├── PROTOCOL: tcp
├── HOSTNAME: localhost
├── COMMANDING_PORT: 6100
├── MONITORING_PORT: 6101
├── SERVICE_PORT: 6102
├── METRICS_PORT: 6103
└── DELAY: 1
```

The values can be accessed as usual with a dictionary, by specifying the name of the parameter as the key:

```python
>>> print(storage_settings["COMMANDING_PORT"])
6100
```

We usually only go one level deep when defining settings, and as a convenience, that first level of variables can
also be accessed with the dot-notation.

```python
>>> print(storage_settings.COMMANDING_PORT)
6100
```

## Entry-points

The Settings are collected from a set of YAML files which are provided by the packages through the entry-point
`cgse.settings`. The default Settings file is named `settings.yaml` but this can be changed by the entry-point (see
below).

Let's take a look at how the settings are provided for the `cgse-core` package. First, the `pyproject.toml` file of
the project shall define the entry-point. In the snippet below, the entry-point `cgse-core` is defined for the group
`cgse.settings`.

```toml
[project.entry-points."cgse.settings"]
cgse-core = "cgse_core:settings.yaml"
```

The entry-point itself has the following format: `<name> = "<module>.<filename>"`, where

- `<name>` is the name of the entry-point given in the `pyproject.toml` file, usually this is the package name,
- `<module>` is a valid module name that can be imported and from which the location can be determined, and
- `<filename>` is the name of the target file, e.g. a YAML file.

!!! Note

    The module name for this entry point has an underscore instead of a dash, i.e. `cgse_core` instead of 
    `cgse-core`. The reason is that module names with a dash will generate a SyntaxError during import.

The above example will load the settings for this package from the `settings.yaml` file that is located in the
`cgse_core` module. That is, the package shall also provide this as follows:

```text
cgse-core
├── pyproject.toml
└── src
    └── cgse_core
        ├── __init__.py
        └── settings.yaml
```

The `settigs.yaml` file for this module looks something like this:

```text
PACKAGES:
    CGSE_CORE: The core services of the CGSE

Logging Control Server:                          # LOG_CS

    PROTOCOL:                       tcp
    HOSTNAME:                 localhost          # The hostname that client shall connect to, e.g. pleiad01 @ KU Leuven
    LOGGING_PORT:                  7000
    COMMANDING_PORT:               7001
    METRICS_PORT:                  7003          # The HTTP port where Prometheus will connect to for retrieving metrics
    MAX_NR_LOG_FILES:                20          # The maximum number of log files that will be maintained in a roll-over
    MAX_SIZE_LOG_FILES:              20          # The maximum size one log file can become
    TEXTUALOG_IP_ADDRESS:     127.0.0.1          # The IP address of the textualog listening server
    TEXTUALOG_LISTENING_PORT:     19996          # The port number on which the textualog server is listening

Configuration Manager Control Server:            # CM_CS

    ...
```

## Local Settings

You can, and you should, define local settings for your project and put those settings in a known folder
on your system. The usual place is `~/cgse/local-settings.yaml`. This file will be automatically loaded by the
`Settings.load()` function when you define the local settings environment variable. That variable name is
`<PROJECT>_LOCAL_SETTINGS` where `<PROJECT>` is the name of your project as defined by the `PROJECT` environment
variable. For a `PROJECT=LAB23` the local settings would be defined as follows:

```text
$ export LAB23_LOCAL_SETTINGS=~/cgse/local-settings-lab23.yaml
```

The local settings take higher precedence that will overwrite the global settings when loaded. You only need to define
the settings that actually change for your local installation, respect the full hierarchy when specifying those
settings. You are allowed to define new entries at any level in the Settings hierarchy.

The usual parameters to put into a local settings file are:

- the SITE ID
- the hostnames of the different devices that you use
- the hostname of the server where core services or device control servers are running
- port numbers that have been changed from the default

## Terminal Command

You can check the current settings from the terminal with the following command:

```shell
$ py -m egse.settings
Settings
├── PACKAGES
│   ├── CGSE_COMMON: Common classes, functions, decorators, etc. for the CGSE
│   └── CGSE_CORE: The core services of the CGSE
├── SITE
│   ├── ID: LAB42
│   ├── SSH_SERVER: localhost
│   └── SSH_PORT: 22
├── PROCESS
│   └── METRICS_INTERVAL: 10
├── Logging Control Server
│   ├── PROTOCOL: tcp
│   ├── HOSTNAME: localhost
│   ├── LOGGING_PORT: 7000
│   ├── COMMANDING_PORT: 7001
... ...
└── Storage Control Server
    ├── PROTOCOL: tcp
    ├── HOSTNAME: localhost
    ├── COMMANDING_PORT: 6100
    ├── MONITORING_PORT: 6101
    ├── SERVICE_PORT: 6102
    ├── METRICS_PORT: 6103
    └── DELAY: 1
Memoized locations:
['/Users/rik/github/cgse/libs/cgse-common/src/cgse_common/settings.yaml', '/Users/rik/github/cgse/libs/cgse-core/src/cgse_core/settings.yaml', '/Users/rik/cgse/local_settings_ariel.yaml']
```

The _memoized locations_ are the settings files that have been loaded and cached. Once the application has started and
the settings have been loaded, they can only be reloaded by explicitly forcing a reload as follows:

```python
>>> settings = Settings.load(force=True)
```

!!! Warning
    
    The `force` reload does however not guarantee that the settings will propagate properly throughout the application
    or to client apps. Settings can be saved in local variables or class instances that have no knowledge of a Settings
    reload. So, be careful when changing your Settings. If there are parameters that change often and are not as 
    static as thought, maybe they belong in the [Setup](./setup.md) instead of the Settings. Examples are:
    
    - calibration parameters
    - SUT parameters
    - conversion functions
    - coordinates and reference frames
    - models


## The design of the `load()` method

A word about the `Settings.load()` method. Depending on the parameters provided, this method either loads all 
settings, a group of settings or just one single YAML file. We have already explained how to load a specific group 
of settings by giving the name of the group as a parameter. When you want to load just one YAML file, you need to 
specify its location also. When a location is given as a str or a Path, the Settings will be loaded from that file 
only, using the default `settings.yaml` name or another name given through the `filename` argument.

This can be used to e.g. load command files for a device:

```python
>>> commands = Settings.load(location="~", filename="DAQ5610.yaml")
```

The mechanism behind the `Settings.load()` method is shown in the following diagram. For simplicity, parameters are 
not shown and only the success path is presented, not any exceptions or error handling.


![load_methods](./images/load_methods.png)
