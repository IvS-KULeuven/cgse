All you need to get started using and building the CGSE.

## Requirements

- Python 3.9.x (we do not yet support higher versions, but are working to extend the list)
- macOS or Linux

## Virtual environment

You should always work inside a virtual environment to somehow containerize your project such that it doesn't 
pollute your global environment and you can run different projects next to each other. Create and activate a new 
virtual environment as follows:

```shell
$ python -m venv venv
$ source venv/bin/activate
```

## Installation

The easiest way to install the CGSE is to use the `pip` command. Since the CGSE is a monorepo and consists of 
numerous packages, you will need to make your choice which package you need for your project. You can however start 
with the `cgse-common` which contains all common code that is generic and useful as a basis for other packages.

```shell
$ pip install cgse-common
```

Check the [list of packages](./package_list.md) that are part of the CGSE repo and can be installed with `pip`. The 
packages are described in the sections [Libs](./libs/index.md) and [Projects](./projects/index.md).

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

The other environment variable follow the pattern `<PROJECT>_`, i.e. they all start with the project name as defined 
in the PROJECT environment variable. You should define at least `<PROJECT>_DATA_STORAGE_LOCATION`, the configuration 
data and log file location will be derived from it. 

```
$ py -m egse.env
/Users/rik/tmp/gettings-started/venv/lib/python3.9/site-packages/egse/env.py:112: UserWarning: The environment variable PROJECT is not set. PROJECT is required to define the project settings and environment variables. Please set the environment variable PROJECT before proceeding.
  warnings.warn(
/Users/rik/tmp/gettings-started/venv/lib/python3.9/site-packages/egse/env.py:112: UserWarning: The environment variable SITE_ID is not set. SITE_ID is required to define the project settings and environment variables. Please set the environment variable SITE_ID before proceeding.
  warnings.warn(
Environment variables:
    PROJECT = NoValue
    SITE_ID = NoValue
    NoValue_DATA_STORAGE_LOCATION = not set
    NoValue_CONF_DATA_LOCATION = not set
    NoValue_CONF_REPO_LOCATION = not set
    NoValue_LOG_FILE_LOCATION = not set
    NoValue_LOCAL_SETTINGS = not set

Generated locations and filenames
    get_data_storage_location() = The environment variable PROJECT is not set. Please set the environment variable before proceeding.
    get_conf_data_location() = Could not determine the location of the configuration files. The environment variable NoValue_CONF_DATA_LOCATION is not set and also the data storage location is
unknown.
    get_conf_repo_location() = None  ⟶ ERROR: The configuration repository location doesn't exist!
    get_log_file_location() = Could not determine the location of the log files. The environment variable NoValue_LOG_FILE_LOCATION is not set and also the data storage location is unknown.
    get_local_settings() = None  ⟶ ERROR: The local settings file is not defined or doesn't exist!

use the '--full' flag to get a more detailed report, '--doc' for help on the variables.
```

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
