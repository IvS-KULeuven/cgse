"""The log-files service: answers pickled string commands about the files of the log folder of its machine.

Commands:

- `status`: the PID, the log folder, the service type, whether it's registered, and the number of requests.
- `files`: the files of the log folder with their `name`, `size` and `mtime`, the most recently changed first.
- `read <name> [offset [max]]`: a page of the file from `offset`, or the last page when `offset` is `-`.
- `before <name> <end> [max]`: the page of the file that ends at `end`, to scroll back.

A name is quoted as in a shell when it has spaces, see `egse.logfiles.reader.read_file()` for the pages.
- `quit`: stops the service.

The service registers as soon as the registry answers, also when that is later than its own start, so it can be
started before the registry (e.g. by `cgse core start`).
"""

from __future__ import annotations

import json
import multiprocessing
import os
import pickle
import shlex
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any

import rich
import typer
import zmq
from egse.system import format_datetime
from egse.system import get_host_ip
from egse.system import get_machine_id
from egse.zmq_ser import get_port_number

from egse.logfiles import CGSE_OBJECT
from egse.logfiles import PROCESS_NAME
from egse.logfiles import lock_path
from egse.logfiles import log_folder
from egse.logfiles import logger
from egse.logfiles import reader
from egse.logfiles import send_request
from egse.logfiles import service_type
from egse.logger import remote_logging
from egse.registry.client import RegistryClient

REGISTER_INTERVAL = 10.0
"""Seconds between two tries to register while the registry doesn't answer."""

LOCK_TRIES = 10
"""Tries to take the lock, 0.1 s apart: a client that checks whether the service runs holds it for a moment."""

LOCK_CHECK_INTERVAL = 3600.0
"""Seconds between two checks of the lock file: it's touched, so the cleaner of the temporary directory leaves it (e.g.
after 10 days on Linux), and taken again when it was removed anyway."""

app = typer.Typer(name=PROCESS_NAME, help="The log-files service: reads the files of the log folder of this machine.")


def take_lock(path: Path) -> int | None:
    """Takes the lock on the file, the file descriptor; None when another service holds it."""
    import fcntl

    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    for _ in range(LOCK_TRIES):
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            time.sleep(0.1)
    os.close(fd)
    return None


def write_lock_info(fd: int, info: dict[str, Any]) -> None:
    os.ftruncate(fd, 0)
    os.pwrite(fd, json.dumps(info).encode(), 0)


class LockFile:
    """The lock that tells the service runs, on a file with its PID and port, see `egse.logfiles`.

    Args:
        path: the lock file.
    """

    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None
        self.info: dict[str, Any] = {}

    def take(self) -> bool:
        """Takes the lock, False when another service holds it."""
        self.fd = take_lock(self.path)
        return self.fd is not None

    def write(self, info: dict[str, Any]) -> None:
        self.info = info
        write_lock_info(self.fd, info)

    def keep(self) -> None:
        """Touches the lock file, so the cleaner of the temporary directory leaves it; takes the lock again on a new
        file when it was removed, so another start still sees that the service runs."""
        try:
            if os.stat(self.path).st_ino == os.fstat(self.fd).st_ino:
                os.utime(self.path)
                return
        except FileNotFoundError:
            pass
        logger.warning(f"The lock file {self.path!s} was removed, the log-files service takes the lock again.")
        os.close(self.fd)
        if self.take():
            self.write(self.info)
        else:
            logger.warning("Another log-files service took the lock.")

    def release(self) -> None:
        if self.fd is not None:
            os.ftruncate(self.fd, 0)
            os.close(self.fd)
            self.fd = None


class LogFilesServer:
    """The log-files service of a log folder.

    Args:
        folder: the log folder.
        registry: the registry client, None to run without registration (tests).
        lock: the lock that tells the service runs, kept while the service runs.
    """

    def __init__(self, folder: Path, registry: RegistryClient | None = None, lock: LockFile | None = None):
        self.folder = folder
        self.lock = lock
        self._next_lock_check = time.monotonic() + LOCK_CHECK_INTERVAL
        self.service_type = service_type(folder)
        self.registry = registry
        self.service_id: str | None = None
        self.requests = 0
        self.start_time = time.time()
        self._running = False
        self._next_registration = 0.0
        self.context = zmq.Context.instance()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind("tcp://*:0")
        self.port = get_port_number(self.socket)

    def handle(self, command: str) -> dict[str, Any]:
        """The answer to a command, an answer with `status` NACK and an `error` for a bad command."""
        answer: dict[str, Any] = dict(timestamp=format_datetime())
        try:
            words = shlex.split(command) if isinstance(command, str) else []
        except ValueError as exc:
            return {**answer, "status": "NACK", "error": f"Bad command {command!r}: {exc}"}
        name = words[0].lower() if words else ""

        if name == "status":
            answer.update(
                status="ACK",
                pid=os.getpid(),
                start_time=self.start_time,
                folder=str(self.folder),
                service_type=self.service_type,
                cgse_object=CGSE_OBJECT,
                registered=self.service_id is not None,
                port=self.port,
                requests=self.requests,
            )
        elif name == "files":
            answer.update(status="ACK", folder=str(self.folder), files=reader.list_files(self.folder))
        elif name in ("read", "before"):
            usage = "read <name> [offset|- [max]]" if name == "read" else "before <name> <end> [max]"
            try:
                if not (2 if name == "read" else 3) <= len(words) <= 4:
                    raise IndexError
                position = None if len(words) < 3 or words[2] == "-" else int(words[2])
                maximum = int(words[3]) if len(words) > 3 else reader.MAX_READ
            except (IndexError, ValueError):
                return {**answer, "status": "NACK", "error": f"Usage: {usage}, got {command!r}"}
            positions = dict(offset=position) if name == "read" else dict(before=position)
            try:
                answer.update(status="ACK", **reader.read_file(self.folder, words[1], max_bytes=maximum, **positions))
            except (ValueError, OSError) as exc:
                answer.update(status="NACK", error=str(exc))
        else:
            answer.update(status="NACK", error=f"Unknown command {command!r}, use status, files, read, before or quit.")
        return answer

    def register(self) -> None:
        """Registers the service when the registry answers, tries again after `REGISTER_INTERVAL` when it doesn't."""
        if self.registry is None or self.service_id is not None or time.monotonic() < self._next_registration:
            return
        self._next_registration = time.monotonic() + REGISTER_INTERVAL
        if not self.registry.health_check():
            return
        self.service_id = self.registry.register(
            name=f"{PROCESS_NAME}@{socket.gethostname()}",
            host=get_host_ip() or "127.0.0.1",
            port=self.port,
            service_type=self.service_type,
            metadata={
                "server_kind": "command",  # pickled string commands, e.g. "status"
                "cgse_object": CGSE_OBJECT,  # `cgse lf start|stop|status`
                "log_folder": str(self.folder),
            },
        )
        if self.service_id is not None:
            self.registry.start_heartbeat()

    def serve(self) -> None:
        """Answers the requests until `quit` or `stop()`."""
        self._running = True
        while self._running:
            self.register()
            if self.lock is not None and time.monotonic() >= self._next_lock_check:
                self._next_lock_check = time.monotonic() + LOCK_CHECK_INTERVAL
                self.lock.keep()
            if not self.socket.poll(1000):
                continue
            command = pickle.loads(self.socket.recv())
            if command == "quit":
                self.socket.send(pickle.dumps("ACK"))
                break
            self.requests += 1
            try:
                answer = self.handle(command)
            except Exception as exc:  # a bad request shall not stop the service
                answer = dict(timestamp=format_datetime(), status="NACK", error=f"{type(exc).__name__}: {exc}")
            self.socket.send(pickle.dumps(answer))

    def stop(self) -> None:
        self._running = False

    def close(self) -> None:
        if self.registry is not None:
            if self.service_id is not None:
                self.registry.stop_heartbeat()
                self.registry.deregister(self.service_id)
            self.registry.disconnect()
        self.socket.close(linger=0)


@app.command()
def start():
    """Start the log-files service of this machine, when it doesn't run yet."""
    multiprocessing.current_process().name = PROCESS_NAME
    try:
        folder = log_folder()
    except ValueError as exc:
        rich.print(f"[red]The log-files service can't start: {exc}[/]")
        sys.exit(1)

    lock = LockFile(lock_path(folder))
    if not lock.take():
        rich.print(f"The log-files service already runs for {folder!s}.")
        return

    with remote_logging():
        registry = RegistryClient()
        registry.connect()
        server = LogFilesServer(folder, registry, lock)
        lock.write(dict(pid=os.getpid(), port=server.port, folder=str(folder), machine_id=get_machine_id()))
        signal.signal(signal.SIGTERM, lambda *_: server.stop())
        logger.info(f"The log-files service serves {folder!s} on port {server.port}.")
        try:
            server.serve()
        except KeyboardInterrupt:
            pass
        finally:
            server.close()
            lock.release()
            logger.info("The log-files service stopped.")


@app.command()
def stop():
    """Stop the log-files service of this machine."""
    answer = send_request("quit")
    if answer == "ACK":
        rich.print("The log-files service stopped.")
    else:
        rich.print(f"The log-files service: {answer.get('error')}")


@app.command()
def status():
    """Print the status of the log-files service of this machine."""
    answer = send_request("status")
    if answer.get("status") != "ACK":
        rich.print("Log-files service:")
        rich.print("    Status: [red]not active[/]")
        rich.print(f"    {answer.get('error')}")
        sys.exit(1)
    rich.print("Log-files service:")
    rich.print("    Status: [green]active[/]")
    rich.print(f"    Log folder: {answer['folder']}")
    rich.print(f"    Service type: {answer['service_type']}")
    rich.print(f"    Registered: {'yes' if answer['registered'] else 'no, the registry did not answer yet'}")
    rich.print(f"    PID: {answer['pid']}, port: {answer['port']}, requests: {answer['requests']}")


if __name__ == "__main__":
    app()
