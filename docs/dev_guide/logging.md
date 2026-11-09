# Logging

This part of the developer guide is about choosing the level of a log message, and about keeping the log useful for
the people who read it: operators during a test, and developers who explain a problem afterwards.

## Where log messages go

In the CGSE, a DEBUG message is not free. When logging is set up for a process (`egse.logger`):

- The `egse` loggers are set to DEBUG, and a ZeroMQ handler sends every record to the Logger (`log_cs`).
- The Logger writes all of them to the log file in the log file location, `general.log` unless the settings name it
  otherwise (`LOG_LEVEL_FILE` is DEBUG in `egse.logger.log_cs`, it can be changed with the `set_level` command of the
  Logger).
- The Logger keeps the most recent records in memory for its `tail` command, which the log panel of the CGSE TUI
  shows. That buffer has a fixed size: routine messages push the useful ones out.
- Only the terminal is filtered, with the `LOG_LEVEL` environment variable (default INFO).

So every DEBUG message of every process is sent over the network, written to disk, and takes a place in the
Logger's buffer. On a system where the services log every request and every heartbeat, a buffer of 1000 records
covered about 70 seconds.

## The levels

Choose the level by who acts on the message, not by how far the code is developed.

| Level             | Use it for                                                                                                                                                                                       | Test                                                                                              |
|-------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| **CRITICAL**      | The process can't continue, or is about to exit.                                                                                                                                                 | Someone must act now. Rare.                                                                       |
| **ERROR**         | An operation failed and its result is lost: a command failed, a device can't be reached, data wasn't saved.                                                                                       | Someone should look at it. Not for expected conditions that are handled.                          |
| **WARNING**       | Unexpected but handled; the system runs degraded, or it may turn into an error. E.g. the Storage Manager is not active and housekeeping isn't stored, a request succeeded only after a retry. | Every warning gets read. A warning that shows up in normal operation every cycle is no warning.   |
| **INFO**          | Lifecycle and state changes that belong in the record of a test: start and stop, connect and disconnect, register and deregister, Setup loaded, observation started and ended, commands that change the state of the hardware. | A system that runs quietly produces almost no INFO messages.                                      |
| **DEBUG**         | What you need afterwards to explain a problem: a device command received with its arguments, a decision taken, a retry.                                                                          | One line per event, never one per tick.                                                           |
| `VERBOSE_DEBUG`   | Development traces: raw messages, step-by-step lines, every iteration of a loop. Guarded with `if VERBOSE_DEBUG:` (an environment variable, see `egse.env`).                                     | Off in normal use.                                                                                |

## Rules

1. **Periodic code logs changes, not iterations.** Heartbeats, monitoring messages, polls and status requests log
   only when something changes (e.g. `ok → stale`) or fails.
2. **Monitoring requests are silent on the server.** `ping`, `info` and `status_report` come from tools like the
   CGSE TUI and the Process Manager; if the server logs them, the clients decide how much ends up in the log.
3. **A repeated condition is logged twice:** when it starts, and when it recovers, preferably with a count, e.g.
   `"Device reachable again after 37 failed attempts."`. Not on every attempt.
4. **Log an error once, where it is handled**, not at every layer that re-raises it. Use `logger.exception(...)` or
   `exc_info=True` for an unexpected error; an expected exception gets a short message without a traceback.
5. **A message stands on its own:** what happened, to which service or device (with its device id), and the outcome.
   No timestamp in the message, the record has its time. No messages without a subject, like `"Process the
   command..."`.

```python
# Bad: every second, with the time in the message, nobody acts on it
logger.debug(f"{datetime.datetime.now()} Sending status updates.")

# Good: only the change
if state != previous_state:
    logger.info(f"{service_name}: {previous_state} → {state}")
```

## Keeping levels from freezing in place

A level chosen while writing the code tends to stay when the code is finished. Two habits help:

- Write development traces with `VERBOSE_DEBUG`, or remove them before merging. Plain `logger.debug()` is for what
  stays.
- Review every new log call with two questions: **how often does it fire in normal operation**, and **who acts on
  it?** A log call in a loop needs a reason.

To find the noisy places in a running system, open the detail screen of the Logger in the CGSE TUI (`cgse tui`),
filter the log panel on a process, and look at the number of DEBUG lines of each process.
