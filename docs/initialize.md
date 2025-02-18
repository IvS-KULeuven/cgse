# Initialize your project

So, we have seen how to get started with some basic commands and only the `cgse-common` package.
It's time now to initialize your project properly with all the necessary services.

## Set up your environment

I assume you are in the same environment that we have set up in
the [previous section](./getting_started.md) where also the `cgse-common` package was installed. We
will install another package that will provide us with the full functionality of the `cgse` command.
Install the `cgse-tools` and `cgse-core` packages which depends on
`cgse-core` and will also install that package.

```shell
$ pip install cgse-tools cgse-core
```

You should now have at least the follow three packages installed in your virtual environment:

```text
$ pip list | grep cgse
cgse-common       0.5.0
cgse-core         0.5.0
cgse-tools        0.5.0
```

## The `cgse` command

The two new packages that have been installed (`cgse-core` and `cgse-tools`) provide the `cgse`
command that we will use to initialize your environment, but this command is also used to inspect
different parts of the system, manage core services and device drivers, etc.

When you run the `cgse` command without any arguments, it will show something like this:

```text
$ cgse

 Usage: cgse [OPTIONS] COMMAND [ARGS]...

 The main cgse command to inspect, configure, monitor the core services and device control servers.

╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --install-completion          Install completion for the current shell.                                                                                      │
│ --show-completion             Show completion for the current shell, to copy it or customize the installation.                                               │
│ --help                        Show this message and exit.                                                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ version   Prints the version of the cgse-core and other registered packages.                                                                                 │
│ init      Initialize your project.                                                                                                                           │
│ top       A top-like interface for core services and device control servers.                                                                                 │
│ core      handle core services: start, stop, status                                                                                                          │
│ show      Show information about settings, environment, setup, ...                                                                                           │
│ check     Check installation, settings, required files, etc.                                                                                                 │
│ dev-x     device-x is an imaginary device that serves as an example                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

The `cgse` command is actually an app that is the starting point for a number of commands that can
be used to maintain the system, manage and inspect services and devices. For example, to check the
version of the different components, use:

```text
$ cgse version
CGSE-COMMON installed version = 0.5.0 — Software framework to support hardware testing
CGSE-CORE installed version = 0.5.0 — Core services for the CGSE framework
CGSE-TOOLS installed version = 0.5.0 — Tools for CGSE
```

We will for now concentrate on the `init` command. This command will guide us through a number of
steps to define the location of our device data, configuration data, etc. We will basically define
some environment variables that are used by the CGSE framework. The PROJECT is he name of the
project your will be working on, the SITE_ID is the identifier for the LAB or Setup that you are
using to perform the tests. As you see below, the environment variables all start with the project
name allowing you to work on different projects simultaneously. If you accept all the defaults, the
result of the `cgse init` command will look something like this:

```text
$ cgse init --project marvel
Please note default values are given between [brackets].
What is the name of the project [MARVEL] ?:
What is the site identifier ?: lab02
Where can the project data be stored [~/data/MARVEL/LAB02/] ?:
Where will the configuration data be located [~/data/MARVEL/LAB02/conf/] ?:
Where will the logging messages be stored [~/data/MARVEL/LAB02/log/] ?:
Where shall I create a local settings YAML file [~/data/MARVEL/LAB02/local_settings.yaml] ?:
Shall I add the environment to your ~/bash_profile ? [y/n]: n

# -> Add the following lines to your bash profile or equivalent

export PROJECT=MARVEL
export SITE_ID=LAB02
export MARVEL_DATA_STORAGE_LOCATION=~/data/MARVEL/LAB02/
export MARVEL_CONF_DATA_LOCATION=~/data/MARVEL/LAB02/conf/
export MARVEL_LOG_FILE_LOCATION=~/data/MARVEL/LAB02/log/
export MARVEL_LOCAL_SETTINGS=~/data/MARVEL/LAB02/local_settings.yaml

```

If you answered 'Y' to the last question, you should log in to the shell again
with `exec bash -login` or a similar command for other shells, or you should start a new terminal to
activate the environment variables.

Add this point you are ready to go and start the core services and any device control servers that
you need. You can explore other commands of the `cgse` app in
the [user guide](./user_guide/index.md).
