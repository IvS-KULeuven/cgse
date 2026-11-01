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
