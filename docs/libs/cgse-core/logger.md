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

The command endpoint takes a command string and answers with a dictionary with `status` `"ACK"`, or `"NACK"` and an
`error`. A failing command doesn't stop the logger, it answers with an error. The commands are:

| Command                                  | Answer                                                             |
|------------------------------------------|--------------------------------------------------------------------|
| `status`                                 | the ports, the levels, the location of the log file and statistics |
| `set_level <LEVEL>`                      | sets the level of the log file, e.g. `set_level INFO`              |
| `roll`                                   | rolls over the log file                                            |
| `tail [after [max]]`                     | the most recent records, kept in memory                            |
| `history <since> <until> [max [cursor]]` | the records of a time window, read from the log files              |
| `quit`                                   | stops the logger, the answer is `"ACK"`                            |

`egse.logger.send_request()` sends a command and returns the answer:

```python
from egse.logger import send_request

response = send_request("tail 0 50")
```

`status`, `roll` and `quit` are also available from the CLI, see below.

### `tail`

The logger keeps the last 10 000 records in memory (`TAIL_LENGTH` in `egse.logger.log_cs`). `tail [after [max]]`
returns the records with a sequence number above `after` (default 0), at most `max` of them (default 100), the most
recent ones. The answer has `records` and `last_seq`, the number of records received. A client that remembers
`last_seq` and passes it as `after` the next time only gets the new records; the CGSE TUI does this for its log panel.

A record is a dictionary with `seq`, `time` (a timestamp), `level`, `name` (the logger), `module`, `process` and
`message`, the message cut to 1000 characters.

### `history`

`history <since> <until> [max [cursor]]` returns the records created between the timestamps `since` and `until`, read
from the log files: `general.log` and the files it rotated into at midnight (`general.log.YYYY-MM-DD`). It's used by
the log screen of the CGSE TUI. The records come oldest first, at most `max` of them (default 5000); one answer reads
at most 8 MB of the log files, the logger doesn't handle other commands while it reads.

The answer has `records` and a `cursor`. When the window has more records, the `cursor` is not `None`: send the same
command with that cursor to continue where the answer stopped. A cursor is no longer valid when its log file has
rotated, the answer is then a `"NACK"`.

A record has the fields of a `tail` record without `seq`, and with `pid`, `filename` and `lineno`; the message is cut
to 4000 characters, a traceback included. The records are written in the order they arrive with the time they were
created, so a record can arrive up to some seconds after a younger one; the window is searched with a margin of 10 s
and the records are selected on their own time. See `egse.logger.history`.

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
