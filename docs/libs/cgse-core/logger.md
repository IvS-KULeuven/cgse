# The Logger

## Overview

The Logging Control Server (`log_cs`) is the centralized sink for CGSE logs.
Processes send log records over ZeroMQ to `log_cs`, which writes to rotating files,
prints selected levels to stdout, and can optionally forward records to an external logger.

In most services, logging forwarding is enabled through `egse.logger.setup_logging()`
or by using the `remote_logging()` context manager.

Core responsibilities:

- centralized log ingestion from services
- rotating file persistence and stdout mirroring
- optional forwarding to external logging endpoints

## Socket Endpoints

The logger uses two endpoints:

| Purpose             | Pattern   | Your Socket | Default Endpoint     |
|---------------------|:---------:|:-----------:|----------------------|
| Log record ingest   | PUSH-PULL |    PUSH     | tcp://localhost:6105 |
| Logger commands     | REQ-REP   |     REQ     | tcp://localhost:6106 |

!!! note
    These default port values are defined in `cgse_core/settings.yaml` and can be overridden in the local settings.
    Ports can be static or dynamically allocated by the OS when configured as `0`. Clients discover
    the active endpoints through the Registry, especially when ports are configured as `0`.


## Client Access

Use `remote_logging()` around your service main loop:

```python
from egse.logger import remote_logging

with remote_logging():
    ...
```

This configures the ZeroMQ log handler so records are forwarded to `log_cs`.

## Control Actions

The command endpoint supports:

- `status`
- `set_level <LEVEL>`
- `roll` (log rotation)
- `quit`

Convenience wrappers are exposed via CLI.

## Running The Service

=== "Using `uv` (preferred)"

    ```bash
    uv run cgse log start
    uv run cgse log stop
    uv run cgse log status
    ```

=== "Direct (for debugging)"

    ```bash
    python -m egse.logger.log_cs start
    python -m egse.logger.log_cs status
    python -m egse.logger.log_cs roll
    python -m egse.logger.log_cs stop
    ```

## Configuration

Settings are loaded from `Logging Control Server` in `cgse_core/settings.yaml`.
Important keys include:

- `RECEIVER_PORT`
- `COMMANDER_PORT`
- `MAX_NR_LOG_FILES`
- `MAX_SIZE_LOG_FILES`
- `EXTERN_LOG_HOST`
- `EXTERN_LOG_PORT`

## Integration Notes

At startup, `log_cs` registers itself in the Service Registry and publishes:

- command port as service port
- receiver port in service metadata (`receiver_port`)

This enables dynamic endpoint resolution for producers.

## Monitoring And Troubleshooting

- Use `uv run cgse log status` to inspect active ports, levels, and the location of the log file.
- If forwarding is missing, verify that Registry is running and `log_cs` is registered.
- If startup fails, check that log directory exists and is writable.
