# The Environment

The CGSE uses a number of environment variables that you will need to set in order to properly run services. There 
are currently two mandatory environment variables:

- **PROJECT**: which is the name of your project, use ALL_CAPS to set its value. The value of this environment 
  variable is used as a prefix for other known environment variable specific for your project. For instance, when 
  your PROJECT=ARIEL, you will have a number of environment variables starting with `ARIEL_`, e.g. 
  `ARIEL_DATA_STORAGE_LOCATION`.
- **SITE_ID**: this is the name of the site or lab where the CGSE is running. The site id makes your tests and 
  environment unique. Suppose you have a laboratory with three test setupt, you can distinct site ids for each of 
  these setups. The `SITE_ID` will be used to assemble the path location of your storage, database, configurations 
  files, etc.

Besides the mandatory environment variables, the CGSE also maintains a number of _known_ environment variables. When 
these variables are not set, they will be determined from defaults.

**`{PROJECT}_DATA_STORAGE_LOCATION`**

:   This directory contains all the data files that are generated and filled by 
    the control servers and other components. The folder is the root folder for all 
    data from your test equipment, the SUT (system under test) and
    all site ids.

**`{PROJECT}_CONF_DATA_LOCATION`**: 

:   This directory is the root folder for all the Setups of the site, the site is part
    of the name. By default, this directory is located in the overall data storage folder.

**`{PROJECT}_LOG_FILE_LOCATION`**: 

:   This directory contains the log files with all messages that were sent to the
    logger control server. The log files are rotated on a daily basis at midnight UTC.
    By default, this directory is also located in the overall data storage folder, such
    that log files are kept per project and site id.

**`{PROJECT}_LOCAL_SETTINGS`**: 

:   This file is used for local site-specific settings. When the environment
    variable is not set, no local settings will be loaded. By default, the name 
    of this file is assumed to be 'local_settings.yaml'.

You can inspect your current environment with the command given below. The example is for 
a project called ARIEL and a test setup in the vacuum lab.

```shell
➜ cgse show env
Environment variables:
    PROJECT = ARIEL
    SITE_ID = VACUUM_LAB
    ARIEL_DATA_STORAGE_LOCATION = ~/data/ARIEL/VACUUM_LAB
    ARIEL_CONF_DATA_LOCATION = ~/data/ARIEL/VACUUM_LAB/conf
    ARIEL_CONF_REPO_LOCATION = not set
    ARIEL_LOG_FILE_LOCATION = ~/data/ARIEL/VACUUM_LAB/log
    ARIEL_LOCAL_SETTINGS = ~/data/ARIEL/VACUUM_LAB/local_settings.yaml

Generated locations and filenames
    get_data_storage_location() = '~/data/ARIEL/VACUUM_LAB'
    get_conf_data_location() = '~/data/ARIEL/VACUUM_LAB/conf'
    get_conf_repo_location() = None  ⟶ ERROR: The configuration repository location doesn't exist!
    get_log_file_location() = '~/data/ARIEL/VACUUM_LAB/log'
    get_local_settings_path() = '~/data/ARIEL/VACUUM_LAB/local_settings.yaml'

use the '--full' flag to get a more detailed report, '--doc' for help on the variables.
```
!!! note

    Note that the environment variables can start with the tilde `~` character which will be expanded into the 
    user's home folder when used.
