# The Configuration Manager

## Overview

The Configuration Manager (`cm_cs`) is the central authority for test setup configuration and observation lifecycle.
It manages setup loading, setup queries, and observation start/end coordination.

Core responsibilities:

- manage and distribute active setup
- expose setup discovery/list/load operations
- create and track observation identifiers (`obsid`)
- coordinate with Storage Manager when observations start/end

## Socket Endpoints

`cm_cs` follows the standard Control Server pattern with three sockets:

| Purpose              | Pattern   | Default Endpoint     |
|----------------------|:---------:|----------------------|
| Commanding           | REQ-REP   | tcp://localhost:6110 |
| Monitoring           | PUB-SUB   | tcp://localhost:6111 |
| Service/Admin        | REQ-REP   | tcp://localhost:6112 |

!!! note
    These default port values are defined in `cgse_core/settings.yaml` and can be overridden in the local settings.
    Ports can be static or dynamically allocated by the OS when configured as `0`. Clients discover
    the active endpoints through the Registry, especially when ports are configured as `0`.

## Client Access

Use `ConfigurationManagerProxy` for synchronous client access:

```python
from egse.confman import ConfigurationManagerProxy

with ConfigurationManagerProxy() as cm:
    current = cm.get_setup()
    setups = cm.list_setups(site_id="CSL", position=2)
```

Useful helper functions:

- `is_configuration_manager_active()`
- `get_status()`

## Control Actions

- `list_setups(...)`
- `load_setup(setup_id)`
- `get_setup()`
- `start_observation(...)`
- `end_observation(...)`
- `get_obsid()`

## Running The Service

```bash
python -m egse.confman.confman_cs start
python -m egse.confman.confman_cs status
python -m egse.confman.confman_cs list-setups
python -m egse.confman.confman_cs load-setup <setup_id>
python -m egse.confman.confman_cs stop
```

## Configuration

Settings are loaded from `Configuration Manager Control Server` in `cgse_core/settings.yaml`.
Important keys include:

- `COMMANDING_PORT`
- `MONITORING_PORT`
- `SERVICE_PORT`
- `STORAGE_MNEMONIC`

## Integration Notes

- `cm_cs` publishes setup-change events through Notify Hub.
- It registers to Storage Manager for housekeeping persistence.
- It propagates housekeeping metrics through Metrics Hub (via Control Server integration).

## Monitoring And Troubleshooting

- Use the `status` command to verify service health and current setup state.
- If setup changes are not observed by other services, validate Notify Hub connectivity.
- If observation transitions fail, verify Storage Manager availability and registration state.
