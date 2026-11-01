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
- `r`: refresh, poll the registry and the services now;
- `o`: select the columns of the overview (in the dialog: `space` toggles a column, `a` all, `n` none, `d` defaults,
  `esc` or `o` closes it);
- `l`: show or hide the log pane;
- `ctrl+q`: quit.

## Latest release

- PyPI: https://pypi.org/project/cgse-tui/
- GitHub releases: https://github.com/IvS-KULeuven/cgse/releases
- Changelog: https://github.com/IvS-KULeuven/cgse/blob/main/CHANGELOG.md
