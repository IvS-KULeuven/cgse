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

## Running The Service

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
