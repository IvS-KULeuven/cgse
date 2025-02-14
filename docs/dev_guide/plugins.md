# Plugins

The CGSE is designed to be extensible and uses a few plugin mechanisms to extend its functionally
with external contributions. Also within the `cgse` monorepo we use the plugin mechanism at several
places. The following entry-points are currently defined:

* `cgse.version`: Each package that provides functionality within the CGSE or adds a device driver
  registers itself to provide version information.
* `cgse.command`: Packages can add commands or sub-commands to the `cgse` app to manage
  their functionality from within the `cgse` app, e.g. to start or stop the service or to report on
  its status.
* `cgse.service`: Package provides a device driver or another service.
* `cgse.settings`: Package can add their own settings.
* `cgse.explore`: Package provides a set of functions to explore, e.g. if any of the processes 
  it provides are running.
* `cgse.resource`: Packages can register resources.

Each of the entry-points knows how to load a module or object and each entry-point group is
connected to a specific action or plugin hook like, e.g. add a command or command group to the
`cgse` app, add package specific settings to the global settings.

## Version discovery

When you write a package that you want to integrate with the CGSE, provide a `cgse.version`
entry-point. The name of the entry-point shall match the package name and is used to read the
version from the importlib metadata. The entry-point value is currently not used. The entry-point
value can optionally provide additional information about the package, but that is currently not
specified.

Add the following to your `pyproject.toml` file in your project's root folder, replacing
_package-name_ with the name of your project. The entry-point value is currently not used, but you
want to use a valid format, the value below is always valid.

```toml
[project.entry-points."cgse.version"]
package-name = 'egse.version:get_version_installed'
```

## Extending the `cgse` app

### Add a Command

If your package provides specific functionality that can be added as a command or a command group to
the `cgse` app, use the `cgse.command` entry-point group. Since the `cgse` app uses
the [Typer](https://typer.tiangolo.com) package to build its commandline interface, adding a command
is as simple as writing a function. The function will be added to the `cgse` app using
the `app.command()` function of `Typer`, making the function a top-level command of the `cgse`
app. The function can be defined as a plain function or with Typer's `@app.command` decorator.

In the `pyproject.toml` file of your project, add the following lines to add the CGSE command:

```toml
[project.entry-points."cgse.command"]
name = 'module:object'
```

Where:

- `name` is the name of the command
- `module` is a fully qualified module name for your package, a module that can be imported
- `object` is the name of the function that you want to add as a command

As an example, for the `cgse-tools` package, the `init` command of the `cgse` app is listed in
the `pyproject.toml` file as follows:

```toml
[project.entry-points."cgse.command"]
init = 'cgse_tools.cgse_commands:init'
```

The `init` function is defined in the `cgse_commands.py` module which is located in the
`cgse_tools` module in the `src` folder of the package:

```text
src
├── cgse_tools
│   ├── __init__.py
│   ├── cgse_commands.py
...
```

### Add a Command group

Some commands are more complicated and define a number of sub-commands. An example is the `show`
command where you currently have the sub-commands `env` and `settings`

```text
$ cgse show --help

 Usage: cgse show [OPTIONS] COMMAND [ARGS]...

 Show information about settings, environment, setup, ...

╭─ Options ─────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                           │
╰───────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ────────────────────────────────────────────────────────────────────────────╮
│ settings   Show the settings that are defined by the installed packages.              │
│ env        Show the environment variables that are defined for the project.           │
╰───────────────────────────────────────────────────────────────────────────────────────╯
```

The `show` command is defined as a `typer.Typer()` object where `env` and `settings` are added using
the decorator `@<app>.command()`.

```python
import typer

show = typer.Typer(help="Show information about settings, environment, setup, ...")


@show.command(name="settings")
def show_settings():
    ...


@show.command(name="env")
def show_env():
    ...
```

To add this command group to the `cgse` app, the following entry was used in the `pyproject. toml`
file of the `cgse-tools` project. Notice the `[group]` at the end of the entry which indicates this
is a command group instead of a single command.

```toml
[project.entry-points."cgse.command"]
show = 'cgse_tools.cgse_commands:show[group]'
```

### Add a Service

If your package provides a device driver or a specific service, use the `cgse.service`
entry-point group. Service entry-points follow the same scheme as command groups, i.e. they are
added to the `cgse` app as a `Typer()` object. Use the following entry in your `pyproject.toml`
file:

```toml
[project.entry-points."cgse.service"]
name = 'module:object'
```

where:

- `name` is the name of the service or device driver
- `module` is a fully qualified module name for your package, a module that can be imported
- `object` is the name of the `Typer()` object that you want to add as a service

## Explore

The entry-point `cgse.explore` can be used to extend functionality without adding a new command 
or sub-command to the `cgse` app. The idea is that commands that work on different packages can 
use this entry-point to perform certain tasks on the package. This is currently used for the 
`show procs` command (see below).

The entry-point has the following format:

```toml
[project.entry-points."cgse.explore"]
explore = "<package>.cgse_explore"
```

So, what happens is that a command that wants to apply a functionality on an external package 
loads the `cgse_explore.py` module for that package and checks if a function with a specific 
name exists in that module. It then executes that function. For the `show procs` command, the 
function `show_processes` is expected and it shall return a list of strings which currently are 
printed to the terminal. This entry-point is currently implemented for `cgse-core` and 
`cgse-dummy` (an external demo package) and when you run the `cgse show procs` command it looks 
something like below (the format is from the unix `ps -ef` command). 

```text
➜  cgse show procs
459800007 76849     1   0 11:07PM ttys003    0:03.53 /Users/rik/tmp/test_dummy/venv/bin/python3.9 -m egse.logger.log_cs start
459800007 76850     1   0 11:07PM ttys003    2:18.60 /Users/rik/tmp/test_dummy/venv/bin/python3.9 -m egse.storage.storage_cs start
459800007 76851     1   0 11:07PM ttys003    2:20.10 /Users/rik/tmp/test_dummy/venv/bin/python3.9 -m egse.confman.confman_cs start
459800007 13825     1   0  4:31PM ttys003    0:02.97 /Users/rik/tmp/test_dummy/venv/bin/python3.9 -m cgse_dummy.dummy_sim start
```

## Register resources

TODO: what if two packages provide a resource `icons` ?

- known resources: icons, styles
