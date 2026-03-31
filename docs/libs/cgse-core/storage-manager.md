# The Storage Manager

## Overview

The Storage Manager (`sm_cs`) is the centralized persistence service for CGSE data products.
Other services register data origins and persistence strategies, then push data records to be stored.

It supports observation-aware storage and daily storage streams.

## Socket Endpoints

`sm_cs` follows the standard Control Server pattern:

| Purpose              | Pattern   | Default Endpoint     |
|----------------------|:---------:|----------------------|
| Commanding           | REQ-REP   | tcp://localhost:6115 |
| Monitoring           | PUB-SUB   | tcp://localhost:6116 |
| Service/Admin        | REQ-REP   | tcp://localhost:6117 |

!!! note
    These default port values are defined in `cgse_core/settings.yaml` and can be overridden in the local settings.
    Ports can be static or dynamically allocated by the OS when configured as `0`. Clients discover
    the active endpoints through the Registry, especially when ports are configured as `0`.

## Client Access

Use `StorageProxy`:

```python
from egse.storage import StorageProxy

with StorageProxy() as storage:
    storage.register({...})
    storage.save({...})
```

Helper functions:

- `is_storage_manager_active()`
- `get_status(full=False)`

## Control Actions

Writers must register an `origin` and persistence strategy before sending data.

Typical flow:

1. `register(origin, persistence_class, prep)`
2. `save(origin, data)`
3. `unregister(origin)`

The module provides convenience functions:

- `register_to_storage_manager(...)`
- `store_housekeeping_information(...)`
- `unregister_from_storage_manager(...)`

## Running The Service

```bash
python -m egse.storage.storage_cs start
python -m egse.storage.storage_cs status
python -m egse.storage.storage_cs status --full
python -m egse.storage.storage_cs stop
```

## Configuration

Settings are loaded from `Storage Manager Control Server` in `cgse_core/settings.yaml`.
Important keys include:

- `COMMANDING_PORT`
- `MONITORING_PORT`
- `SERVICE_PORT`
- `STORAGE_MNEMONIC`

## Data Organization

Storage Manager maintains two primary file streams:

- daily files (`daily/`)
- observation files (`obs/`), bounded by observation start/end

Supported persistence backends include CSV, TXT, FITS, and HDF5 through the persistence layer.

## Integration Notes

- `sm_cs` subscribes to setup-change events (`new_setup`) via Notify Hub.
- It receives observation lifecycle signals from Configuration Manager.

## Monitoring And Troubleshooting

- Use `status --full` to inspect active registrations and persistence state.
- If data is not written, verify registration (`register`) occurs before `save`.
- If observation files are missing, confirm observation start/end signals are received.
