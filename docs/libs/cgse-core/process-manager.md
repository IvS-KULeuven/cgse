# The Process Manager

## Overview

The Process Manager (`pm_cs`) orchestrates CGSE process lifecycle based on setup/device context.
It provides an interface to inspect, start, and stop managed processes and core services.

Core responsibilities:

- manage process commands for configured devices
- provide process status and control via proxy/CLI
- integrate with storage for housekeeping persistence

## Socket Endpoints

`pm_cs` follows the standard Control Server pattern:

| Purpose              | Pattern   | Default Endpoint     |
|----------------------|:---------:|----------------------|
| Commanding           | REQ-REP   | tcp://localhost:6120 |
| Monitoring           | PUB-SUB   | tcp://localhost:6121 |
| Service/Admin        | REQ-REP   | tcp://localhost:6122 |

!!! note
    These default port values are defined in `cgse_core/settings.yaml` and can be overridden in the local settings.
    Ports can be static or dynamically allocated by the OS when configured as `0`. Clients discover
    the active endpoints through the Registry, especially when ports are configured as `0`.

## Client Access

Use `ProcessManagerProxy` for service interaction:

```python
from egse.procman import ProcessManagerProxy

with ProcessManagerProxy() as pm:
    status = pm.get_status()
```

Helper functions:

- `is_process_manager_active()`
- `get_status()`

## Control Actions

Process control is exposed through the proxy and command interface. Typical operations include:

- querying process status
- starting configured processes
- stopping managed processes

## The Devices Of The Setup

The process manager GUI (`pm_ui`) shows the devices of the Setup that the Configuration Manager has loaded, and starts
and stops their control servers. A device is a node of the Setup with a `cgse_object`, see
[The Setup](../cgse-common/setup.md):

```yaml
gse:
    hexapod:
        device_name: PUNA Hexapod
        cgse_object: puna
        device_id: PUNA_01
```

For such a device, the process manager:

- runs `cgse <cgse_object> start|stop|status [<device_id>]` for the control server, and `<cgse_object>_ui
  [<device_id>]` for its UI, e.g. `cgse puna start PUNA_01` and `puna_ui PUNA_01`. Without `device_id` (a single
  device, e.g. the DAQ6510) the commands have no argument.
- finds the running control server in the service registry by its `cgse_object` and `device_id`, not by its service
  type. When a control server of the same `cgse_object` runs with another `device_id`, it logs a warning that says
  what to change in the Setup.
- offers simulator mode when the output of `cgse <cgse_object> start --help` mentions `--sim`; it then starts the
  control server with `--sim`.
- reads the state of a running control server from the output of `cgse <cgse_object> status [<device_id>]`: "not
  active" or "inactive" means the control server doesn't run, "not connected" that it runs without connection to
  the device (orange LED), and "simulator" that it runs in simulator mode.

The `device_id` must be known to the device driver: some drivers take their settings for the device from the
(local) settings with the `device_id` as key, e.g. the KIKUSUI PMX-A, and fail at the start when it's missing.

Older Setups describe a device with `device` (a proxy class), `device_name`, `device_id` and `device_args`. For a node
without `cgse_object`, the process manager derives the `cgse` command from the proxy class, looks for the service type
`device_id` (in upper case) in the registry, and passes the first of the `device_args` to the `cgse` command. Add a
`cgse_object` to use the form above.

!!! note
    Restart `pm_cs` and `pm_ui` together after an update: an older `pm_ui` can't read the devices of a newer `pm_cs`.

## Running The Service

=== "Using `uv` (preferred)"

    ```bash
    uv run cgse pm start
    uv run cgse pm stop
    uv run cgse pm status
    ```

=== "Direct (for debugging)"

    ```bash
    python -m egse.procman.procman_cs start
    python -m egse.procman.procman_cs status
    python -m egse.procman.procman_cs stop
    ```

## Configuration

Settings are loaded from `Process Manager Control Server` in `cgse_core/settings.yaml`.
Important keys include:

- `COMMANDING_PORT`
- `MONITORING_PORT`
- `SERVICE_PORT`
- `STORAGE_MNEMONIC`

## Integration Notes

- `pm_cs` depends on setup context (via Configuration Manager) for managed process definitions.
- It stores housekeeping via Storage Manager.
- It registers as a discoverable service in the Registry.

## Monitoring And Troubleshooting

- Use `status` to verify the manager is reachable and process state is current.
- If process definitions appear incomplete, verify active setup retrieval from Configuration Manager.
- If housekeeping is not persisted, check Storage Manager availability and registration.
