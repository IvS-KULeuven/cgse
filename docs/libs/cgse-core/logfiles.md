# The Log-Files Service

## Overview

The log folder of a machine has more than the log file of the [Logger](logger.md). Every `cgse <object> start` and
`stop` command writes the output of the process it starts to a file in the log folder of the machine where the command
ran, e.g. `puna_cs.puna_01.start.log` for `cgse puna start PUNA_01`. That output has what never reaches the logger: an
import error, a traceback before the service could connect to the logger, output printed with `print()`.

The log-files service (`lf_cs`) reads the files of the log folder of its own machine for clients like the CGSE
TUI (`F` in the log screen). It is read-only and reads nothing outside the log folder. Every machine with services
runs one, so the files can be read from the machine where the TUI runs. It's a separate process, so reading large
files never delays the logger.

## Starting and stopping

```bash
cgse lf start     # in the background, does nothing when it already runs
cgse lf status    # exit code 1 when it doesn't run
cgse lf stop
```

The start commands of the services (`cgse core start`, `cgse puna start`, `cgse daq6510 start-sim`, ...) start the
log-files service when it doesn't run, so normally there is nothing to do. A package does the same in its own start
commands with `egse.logfiles.start_output_log()` instead of `egse.system.redirect_output_to_log()`.

One service runs for a machine and a log folder (`<PROJECT>_LOG_FILE_LOCATION`). It holds a lock on a file in the
temporary directory of the machine; the operating system releases the lock when the process ends, also when it is
killed, so a new start always works. The service touches the lock file every hour, so the cleaner of the temporary
directory leaves it, and takes the lock again on a new file when it was removed anyway. The lock file has the PID and
the port of the service: `cgse lf stop` and `status` don't need the registry.

The service registers with a service type per machine and log folder, e.g. `LF_CS@lab-pc-3f2a9c`, and
`cgse_object: lf`. When the registry doesn't answer, it tries again every 10 s, so it can be started before the
registry.

## Commands

The service answers pickled string commands on a REQ-REP socket with a dynamic port (from the registry, or from the
lock file on the same machine):

| Command                      | Answer                                                                          |
|------------------------------|---------------------------------------------------------------------------------|
| `status`                     | PID, log folder, service type, whether it's registered, number of requests      |
| `files`                      | the files of the log folder with `name`, `size` and `mtime`, newest first       |
| `read <name> [offset [max]]` | a page of the file from `offset`, the last page when `offset` is `-`            |
| `before <name> <end> [max]`  | the page that ends at `end`, to scroll back                                     |
| `quit`                       | stops the service                                                               |

A page has `text`, `offset`, `end` (where the next page starts), `size` and `mtime`. A page has at most 1 MiB (256 KiB
by default). A page from `offset` continues exactly where the previous one ended; a page that ends at a position starts
at the beginning of a line. When `offset` is beyond the end of the file, the file was truncated or replaced (e.g.
rotated): the answer has `truncated` set, ask for the last page again.

Only bare file names are accepted: no paths, no hidden files, and no symbolic links that point out of the folder.

```python
from egse.logfiles import send_request

send_request("files")
send_request("read puna_cs.puna_01.start.log - 65536")
```

## The output files

The output of a start or stop command is appended to its file, after a line with the time (UTC) and the command:

```text
===== 2026-11-12T08:39:05.434+0000 cgse puna start PUNA_01 =====
```

The output of an earlier start, e.g. the traceback of a crash, is kept. A file larger than 10 MiB is renamed to
`<name>.1` (replacing the previous one) at the next start, a process that still writes to it goes on in the renamed
file.
