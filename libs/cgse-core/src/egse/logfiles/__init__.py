"""The log-files service: reads the files of the log folder of its machine for clients like the CGSE TUI.

The log folder of a machine has more than the log file of the logger: the output of every process that was started
with a `cgse <object> start` command (`*.start.log`, `*.stop.log`), with e.g. the traceback of a service that didn't
start. These files are written on the machine where the command ran, so every machine with services runs its own
log-files service, read-only, and only for its own log folder. See `egse.logfiles.reader` for what it reads.

The service (`lf_cs`) is started with `cgse lf start`, and by the start commands of the services, see
`start_output_log()`. One service runs for a machine and a log folder: the service holds a lock on a file in the
temporary directory of the machine, which the operating system releases when the process ends, also when it is
killed. The lock file has the PID and the port of the service, so `cgse lf stop` and `status` don't need the
registry.

The service registers with a service type per machine and log folder, e.g. `LF_CS@lab-pc-3f2a9c`.
"""

from __future__ import annotations

__all__ = [
    "CGSE_OBJECT",
    "PROCESS_NAME",
    "SERVICE_TYPE_PREFIX",
    "ensure_running",
    "lock_info",
    "lock_path",
    "log_folder",
    "send_request",
    "service_type",
    "start_output_log",
]

import hashlib
import json
import logging
import os
import pickle
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from typing import TextIO

import zmq
from egse.system import get_machine_id

logger = logging.getLogger("egse.logfiles")

PROCESS_NAME = "lf_cs"

CGSE_OBJECT = "lf"
"""The `cgse lf start|stop|status` command."""

SERVICE_TYPE_PREFIX = "LF_CS"

OUTPUT_FILE = "lf_cs.start.log"
"""The output of the service process, in the log folder."""

REQUEST_TIMEOUT = 2.0
"""Seconds to wait for an answer of the service."""


def log_folder() -> Path:
    """The log folder of this machine, resolved.

    Raises:
        ValueError: the location of the log files is not configured, or the folder doesn't exist.
    """
    from egse.env import get_log_file_location

    folder = Path(get_log_file_location()).expanduser()
    if not folder.is_dir():
        raise ValueError(f"The log folder doesn't exist: {folder!s}.")
    return folder.resolve()


def _key(folder: Path) -> str:
    """A short identity of this machine and the log folder."""
    return hashlib.sha1(f"{get_machine_id()}|{folder}".encode()).hexdigest()[:6]


def service_type(folder: Path) -> str:
    """The service type of the log-files service of this machine and the log folder, e.g. `LF_CS@lab-pc-3f2a9c`."""
    return f"{SERVICE_TYPE_PREFIX}@{socket.gethostname()}-{_key(folder)}"


def lock_path(folder: Path) -> Path:
    """The lock file of the log-files service of the log folder, in the temporary directory of this machine."""
    return Path(tempfile.gettempdir()) / f"cgse-lf_cs-{_key(folder)}.lock"


def is_locked(path: Path) -> bool:
    """True when a process holds the lock on the file, i.e. the service runs."""
    import fcntl

    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def lock_info(folder: Path) -> dict[str, Any] | None:
    """The PID and port of the service of the log folder that runs on this machine, None when it doesn't run."""
    path = lock_path(folder)
    if not is_locked(path):
        return None
    try:
        info = json.loads(path.read_text() or "{}")
    except (OSError, ValueError):
        return None
    return info if info.get("port") else None


def send_request(command: str, folder: Path | None = None, timeout: float = REQUEST_TIMEOUT) -> dict[str, Any]:
    """Sends a command to the log-files service of this machine and returns its answer, a dictionary with `error`
    when it doesn't run or doesn't answer."""
    try:
        folder = folder or log_folder()
    except ValueError as exc:
        return {"error": str(exc)}
    info = lock_info(folder)
    if info is None:
        return {"error": "The log-files service doesn't run on this machine."}

    sock = zmq.Context.instance().socket(zmq.REQ)
    sock.setsockopt(zmq.LINGER, 0)
    try:
        sock.connect(f"tcp://127.0.0.1:{info['port']}")
        sock.send(pickle.dumps(command))
        if not sock.poll(int(timeout * 1000)):
            return {"error": "The log-files service doesn't answer."}
        return pickle.loads(sock.recv())
    finally:
        sock.close(linger=0)


def start_process(folder: Path) -> None:
    """Starts the service process in the background, in its own session, with its output in the log folder."""
    with open(folder / OUTPUT_FILE, "a") as out:
        subprocess.Popen(
            [sys.executable, "-m", "egse.logfiles.server", "start"],
            stdout=out,
            stderr=out,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )


def ensure_running() -> None:
    """Starts the log-files service of this machine when it doesn't run. It never raises: a problem is logged, the
    command that calls it (e.g. the start of a control server) goes on."""
    try:
        folder = log_folder()
        if not is_locked(lock_path(folder)):
            start_process(folder)
    except Exception as exc:
        logger.warning(f"The log-files service couldn't be started: {type(exc).__name__}: {exc}")


def start_output_log(output_fn: str) -> TextIO:
    """Opens the file in the log folder for the output of a process that is started, see
    `egse.system.redirect_output_to_log()`, and makes sure the log-files service runs on this machine, so the file can
    be read from the CGSE TUI. Use it in the start commands of services, e.g. `cgse puna start`."""
    from egse.system import redirect_output_to_log

    ensure_running()
    return redirect_output_to_log(output_fn)
