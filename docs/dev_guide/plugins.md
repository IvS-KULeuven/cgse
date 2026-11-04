# Plugins

The CGSE is designed to be extensible and uses a few plugin mechanisms to extend its functionally
with external contributions. Also within the `cgse` monorepo we use the plugin mechanism at several
places. The following entry-points are currently defined:

* `cgse.version`: Each package that provides functionality within the CGSE or adds a device driver
  registers itself to provide version information.
* `cgse.command`: Packages can add commands or sub-commands to the `cgse` app to manage
  their functionality from within the `cgse` app, e.g. to start or stop the service or to report on
  its status.
* `cgse.service`: Package provides a device driver or another service. Device packages use the
  sub-group `cgse.service.device_command`, see [Add a Service](#add-a-service).
* `cgse.settings`: Package can add their own settings.
* `cgse.explore`: Package provides a set of functions to explore, e.g. if any of the processes 
  it provides are running.
* `cgse.resource`: Packages can register resources.
* `cgse.tui.details`: Package shows the details of its service in the detail screen of the CGSE TUI,
  see [Details in the TUI](#details-in-the-tui).

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
def show_settings(): ...


@show.command(name="env")
def show_env(): ...
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
entry-point group or one of its sub-groups. Service entry-points follow the same scheme as command
groups, i.e. they are added to the `cgse` app as a `Typer()` object. A device package uses the
`cgse.service.device_command` sub-group:

```toml
[project.entry-points."cgse.service.device_command"]
name = 'module:object'
```

where:

- `name` is the name of the sub-command of the `cgse` app, e.g. `daq6510` for `cgse daq6510`
- `module` is a fully qualified module name for your package, a module that can be imported
- `object` is the name of the `Typer()` object that you want to add as a service

The `cgse` app loads the `cgse.service` group and every sub-group `cgse.service.<sub-group>`. The
commands of a sub-group are listed in their own section of `cgse --help`, named after the sub-group,
e.g. _Device Command_ for `cgse.service.device_command`. The sub-groups currently used are:

| Entry-point group             | Section in `cgse --help` | Used by                                      |
|-------------------------------|--------------------------|----------------------------------------------|
| `cgse.service.core_command`   | Core Command             | the core services in `cgse-core`             |
| `cgse.service.device_command` | Device Command           | device packages, e.g. `keithley-tempcontrol` |
| `cgse.service.example`        | Example                  | the example service in `cgse-tools`          |

The process manager GUI (`pm_ui`) only looks at the `cgse.service.device_command` group, and it
uses the `object` part of the entry-point value as the name of the `cgse` sub-command. Keep `name`
and `object` the same, e.g.:

```toml
[project.entry-points."cgse.service.device_command"]
daq6510 = 'keithley_tempcontrol.cgse_services:daq6510'
```

#### Sub-commands of a device

The `cgse <device>` sub-commands manage the life cycle of the control server, nothing else:

| Sub-command  | Description                                                       |
|--------------|-------------------------------------------------------------------|
| `start`      | Starts the control server.                                        |
| `stop`       | Stops the control server.                                         |
| `status`     | Prints the status of the control server.                          |
| `start-sim`  | Starts the device simulator in the background.                    |
| `stop-sim`   | Stops the device simulator.                                       |
| `status-sim` | Prints the status of the device simulator.                        |

- The process manager starts, stops and queries a control server with
  `cgse <device> start|stop|status [<device_id>]`, so use these names.
- Add `start-sim`, `stop-sim` and `status-sim` only when the package has a simulator that runs as
  a separate process, e.g. `daq6510_sim` in `keithley-tempcontrol`. When the simulator is part of
  the control server, add a `--sim` (`--simulator`) option to `start` instead, e.g.
  `cgse puna start --sim PUNA_01`. The process manager offers simulator mode when it finds `--sim`
  in the output of `cgse <device> start --help`.
- Device operations, e.g. starting a scan or reading the latest values, don't belong in the `cgse`
  app. Provide them in the command of the control server itself, e.g. `daq6510_cs start-scan`.
  The `start` and `stop` sub-commands usually run the control server command in the background with
  its output redirected to a log file, so the result of a device operation would not be seen.

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
function `show_processes` is expected, and it shall return a list of ProcessInfo objects which 
will be used to print a nice process table. This entry-point is currently implemented for `cgse-core` and 
`cgse-dummy` (an external demo package) and when you run the `cgse show procs` command it looks 
something like below (the format is from the unix `ps -ef` command). 

```text
➜ cgse show procs
                                                 Process Information                                                 
┏━━━━━━━┳━━━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PID   ┃ Name       ┃ User ┃ CPU% ┃ Memory MB ┃ Status  ┃ Command                                                  ┃
┡━━━━━━━╇━━━━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 94461 │ python3.12 │ rik  │  0.0 │      46.9 │ running │ python -m cgse_dummy.dummy_sim start                     │
│ 94554 │ python3.12 │ rik  │  0.0 │     124.1 │ running │ python -m cgse_dummy.dummy_cs start                      │
│ 94360 │ python3.12 │ rik  │  0.0 │     121.3 │ running │ python -m egse.registry.server start --log-level WARNING │
│ 94361 │ python3.12 │ rik  │  0.0 │      49.6 │ running │ python -m egse.logger.log_cs start                       │
│ 94362 │ python3.12 │ rik  │  0.0 │      40.5 │ running │ python -m egse.notifyhub.server start                    │
│ 94363 │ python3.12 │ rik  │  0.0 │     125.9 │ running │ python -m egse.storage.storage_cs start                  │
│ 94364 │ python3.12 │ rik  │  0.0 │     126.1 │ running │ python -m egse.confman.confman_cs start                  │
│ 94365 │ python3.12 │ rik  │  0.0 │     125.6 │ running │ python -m egse.procman.procman_cs start                  │
└───────┴────────────┴──────┴──────┴───────────┴─────────┴──────────────────────────────────────────────────────────┘
```

## Details in the TUI

The detail screen of the CGSE TUI (`cgse tui`) shows a service in panels: Service, Process, Device and
Details. The first three are the same for every service. The Details panel shows the service specific status, by
default as a generic tree of the `details` in the status report of the control server, updated with the values of
its monitoring messages. A package can show these details in its own way with a `cgse.tui.details` entry-point.
The name of the entry-point is the `cgse_object` of the control server, i.e. the `cgse <object>` command, the value
is a function:

```toml
[project.entry-points."cgse.tui.details"]
puna = "symetrie_hexapod.tui_details:details"
zonda = "symetrie_hexapod.tui_details:details"
joran = "symetrie_hexapod.tui_details:details"
```

```python
def details(report: dict, live: dict) -> RenderableType | dict[str, RenderableType]:
    ...
```

- `report` is the last status report of the control server, see the `details` section for the values of
  `get_status_details()` (sync) or `get_component_status()` (async). A section that couldn't be retrieved contains
  only an `error` entry.
- `live` holds the device values of the last monitoring message, without the process information: the entries that
  a sync device protocol adds to its `get_status()`, or the `components` of an async control server. They are newer
  than those in the report; when the server publishes no device values, `live` is empty.
- The function returns a [Rich](https://rich.readthedocs.io) renderable, e.g. a `Table`, or a dictionary of
  renderables that are shown as separate panels with the keys as titles, e.g. `{"Position": ..., "Actuators": ...}`.

The function is called every second, so it shall be fast and must not talk to the device. A renderable that is
expensive to render, e.g. a large table that rarely changes, can be cached by the plugin: when the function returns
the same object as before, the TUI doesn't render it again. It only uses Rich, so the
package doesn't depend on Textual or on `cgse-tui`; the module is only imported by the TUI, and only when a
service with that `cgse_object` is shown. A plugin that can't be imported, raises an exception, or returns something
that isn't a Rich renderable, is logged once and the generic tree is shown, the panel border says the plugin failed.

The core services have built-in renderers in `cgse_tui.details`, e.g. the disk usage of the Storage Manager, and
the running observation and the loaded Setup of the Configuration Manager, and the core services of the Process
Manager with their state. A
plugin takes precedence over a built-in renderer. The `symetrie-hexapod` package has an example in
`symetrie_hexapod/tui_details.py`.

## Register resources

TODO: what if two packages provide a resource `icons` ?

- known resources: icons, styles
