All you need to get started using and building the CGSE.

## Requirements

- Python 3.9.x (we do not yet support higher versions, but are working to extend the list)
- macOS or Linux

## Virtual environment

You should always work inside a virtual environment to somehow containerize your project such that it doesn't 
pollute your global environment and you can run different projects next to each other. Create and activate a new 
virtual environment as follows. It should be Python >= 3.9

```shell
$ python -m venv venv
$ source venv/bin/activate
```

## Installation

The easiest way to install the CGSE is to use the `pip` command. Since the CGSE is a monorepo and consists of 
several packages, you will need to make your choice which package you need for your project. You can however start 
with the `cgse-common` which contains all common code that is generic and useful as a basis for other packages.

```shell
$ pip install cgse-common
```

Check the [list of packages](./package_list.md) that are part of the CGSE repo and can be installed with `pip`. The 
packages are described in more detail in the sections [Libs](./libs/index.md) and [Projects](./projects/index.md).

## Set up your environment

To check your installation and set up your environment, here are a few tips.

The version of the core packages and any plugin packages can be verified as follows. The version you installed will 
probably be higher and more lines will appear when other packages are installed.

```shell
$ py -m egse.version
CGSE version in Settings: 2025.0.5
Installed version for cgse-common= 2025.0.5
```

Check your environment with the command below. This will probably print out some warning since you have not defined 
the expected environment variables yet. There are two mandatory environment variables: `PROJECT` and `SITE_ID`. The 
former shall contain the name of your project without spaces and preferably a single word or an acronym like PLATO, 
ARIEL, MARVEL, MERCATOR. The latter is the name of the site or lab where the tests will be performed. Good names are 
KUL, ESA, LAB23.

The other environment variables follow the pattern `<PROJECT>_...`, i.e. they all start with the project name as 
defined 
in the PROJECT environment variable. You should define at least `<PROJECT>_DATA_STORAGE_LOCATION`. The configuration 
data and log file location will be derived from it unless they are explicitly set themselves. 


Let's define the three expected environment variables:

```shell
$ export PROJECT=ARIEL
$ export SITE_ID=VACUUM_LAB
$ export ARIEL_DATA_STORAGE_LOCATION=~/data
```

Rerunning the above command now gives:

```
$ py -m egse.env
Environment variables:
    PROJECT = ARIEL
    SITE_ID = VACUUM_LAB
    ARIEL_DATA_STORAGE_LOCATION = /Users/rik/data
    ARIEL_CONF_DATA_LOCATION = not set
    ARIEL_CONF_REPO_LOCATION = not set
    ARIEL_LOG_FILE_LOCATION = not set
    ARIEL_LOCAL_SETTINGS = not set

Generated locations and filenames
    get_data_storage_location() = '/Users/rik/data/VACUUM_LAB'  ⟶ ERROR: The data storage location doesn't exist!
    get_conf_data_location() = '/Users/rik/data/VACUUM_LAB/conf'  ⟶ ERROR: The configuration data location doesn't exist!
    get_conf_repo_location() = None  ⟶ ERROR: The configuration repository location doesn't exist!
    get_log_file_location() = '/Users/rik/data/VACUUM_LAB/log'  ⟶ ERROR: The log files location doesn't exist!
    get_local_settings() = None  ⟶ ERROR: The local settings file is not defined or doesn't exist!

use the '--full' flag to get a more detailed report, '--doc' for help on the variables.
```

!!! Note

    The folders that do not exist (and are not None) can be created by adding the option `--mkdir` to the above 
    command.

## Check your Settings

Settings contains the static configuration of your system, test setup, equipment, including the System Under Test 
(SUT). You can test your settings with the command below. Let's first also set the `ARIEL_LOCALSETTINGS` environment 
variables:

```
$ export ARIEL_LOCAL_SETTINGS=~/cgse/local_settings_ariel_vacuum_lab.yaml
$ py -m egse.settings
Settings
├── PACKAGES
│   └── CGSE_COMMON: Common classes, functions, decorators, etc. for the CGSE
├── SITE
│   ├── ID: VACUUM_LAB
│   ├── SSH_SERVER: localhost
│   └── SSH_PORT: 22
└── PROCESS
    └── METRICS_INTERVAL: 10
Memoized locations:
['/Users/rik/tmp/gettings-started/venv/lib/python3.9/site-packages/cgse_common/settings.yaml', 
'/Users/rik/cgse/local_settings_ariel_vacuum_lab.yaml']
```
These Settings will grow when you add more packages to your installation or when you define settings yourself in the 
local settings file.
