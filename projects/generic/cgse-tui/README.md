# CGSE TUI

A terminal user interface, built with [Textual](https://textual.textualize.io/), that shows the status of the CGSE
core services and device control servers.

Start it with `cgse tui` or `cgse_tui`.

The design and the status information it uses are described in `docs/dev_guide/tui_status_inventory.md`:

- the services are found in the service registry;
- control servers are followed live on their monitoring port, and asked for their status report when they appear or
  are selected;
- the registry, logger, notification hub and metrics hub are asked for their own status.

The first version is read-only: an overview of all services and a detail screen with the status report of the
selected service.

Keys in the overview:

- `enter`: show the status report of the selected service;
- `r`: refresh, poll the registry and request the status of all services now (otherwise the status report of a
  control server, with the device connection, is requested every 10 s);
- `a`: start, stop or restart the selected service (also in the detail screen), see below;
- `o`: select the columns of the overview (in the dialog: `space` toggles a column, `a` all, `n` none, `d` defaults,
  `esc` or `o` closes it);
- `l`: show or hide the log pane;
- `ctrl+q`: quit.

The detail screen shows the selected service in panels, updated every second:

- Service: the registration in the service registry and the endpoints;
- Process: PID, uptime, CPU and memory. CPU % and memory are shown in orange (warning) or red (critical) when the
  process uses too much CPU or its memory keeps growing, with the reason below, see "CPU and memory warnings";
- Device: the connection and simulator mode, only for services that control a device;
- Details: the service specific status. For a control server these are the `details` of its status report,
  updated with the live values of its monitoring messages (the border says `live`), for the registry, logger and
  hubs their own status. The package of a device can show its details in its own way with a plugin (e.g. the
  positions of the hexapods), the TUI has its own for some core services (e.g. the disk usage of the Storage
  Manager, the observation and the whole Setup of the Configuration Manager), otherwise they're shown as a tree, see "Details in the TUI" in `docs/dev_guide/plugins.md`;
- Registrations: only for the service registry, all registered services; `enter` shows the details of the selected
  service, `esc` goes back.
- Core services: only for the Process Manager, the core services it manages with their state in the TUI; `enter`
  shows the details of the selected service, `esc` goes back.

CPU and memory warnings: the TUI judges the process of every service, and shows the CPU % and memory in orange or red,
also in the overview, and writes a message in the log pane when this changes:

- CPU: the average CPU % over the last minute, a warning from 50 %, critical from 90 %;
- memory: the growth of the RSS over the last 10 minutes, a warning from 10 %, critical from 25 %. It's judged when
  there are samples of at least 5 minutes, so a process that just started isn't taken for a leak.

The limits are in `cgse_tui/data/health.py`.

Panels are dimmed when the service is stale or not running. Keys in the detail screen: `r` requests the status report
now (otherwise every 10 s), `a` starts, stops or restarts the service, `v` shows the raw status report, `esc` goes
back to the overview.

Start, stop and restart run the `cgse <object> start|stop` command of the service, with its device identifier, e.g.
`cgse puna stop PUNA_01`. The dialog shows the commands; selecting an action is the confirmation. A running service
can be stopped or restarted, a core service that is not running can be started. With the simulator checkbox, the
service is started with its simulator: a simulator that is a separate process (e.g. DAQ6510, TVAC) is started first
with `cgse <object> start-sim` when it isn't running, other drivers are started with `--sim`. The checkbox is checked
when the service runs with its simulator now. The progress and the result are written to the
log pane: the TUI waits up to 30 s until a started service is registered, or a stopped service is no longer
registered. The commands run in their own session, so the services started from the TUI don't belong to the terminal of
the TUI.

## Latest release

- PyPI: https://pypi.org/project/cgse-tui/
- GitHub releases: https://github.com/IvS-KULeuven/cgse/releases
- Changelog: https://github.com/IvS-KULeuven/cgse/blob/main/CHANGELOG.md
