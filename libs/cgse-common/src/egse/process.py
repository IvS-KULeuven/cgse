"""
This module provides functions and classes to work with processes and sub-processes.

We combine two great packages, the `subprocess` and the `psutils` packages, to
provide a simplified, robust and user-friendly interface to work with sub-processes.
The classes and functions are optimized to work with processes within the framework
of the `cgse`, so we do not intend to be fully generic. If you need that, we recommend
to use the `subprocess` and `psutil` packages directly.

The main class provided is the `SubProcess` which by default, starts a sub-process
in the background and detached from the parent process. That means there is no
communication between the parent and the subprocess through pipes. Most (if not all)
processes in the `cgse` framework communicate with ZeroMQ messages in different
protocols like REQ-REP, PUSH-PULL and ROUTER-DEALER

Another useful class is the `ProcessStatus`. This class provides status information
like memory and CPU usage for the running process. Additionally, it will generate
and update metrics that can be queried by the Prometheus timeseries database.

"""

from __future__ import annotations

__all__ = [
    "get_process_info",
    "get_processes",
    "is_process_running",
    "list_processes",
    "list_zombies",
    "ps_egrep",
    "ProcessInfo",
    "ProcessStatus",
    "SubProcess",
]

import contextlib
import datetime
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable
from typing import List
from typing import Optional

import psutil
from prometheus_client import Gauge

from egse.bits import humanize_bytes
from egse.log import logger
from egse.system import humanize_seconds


@dataclass
class ProcessInfo:
    pid: int
    name: str
    username: str
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    status: str
    create_time: float
    command: str

    def as_dict(self):
        return {
            "pid": self.pid,
            "name": self.name,
            "username": self.username,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "memory_mb": self.memory_mb,
            "status": self.status,
            "create_time": self.create_time,
            "command": self.command,
        }


def get_processes(filter_func: Callable = None) -> list[ProcessInfo]:
    """Get current processes with optional filtering.

    Args:
        filter_func: a filter function for filtering the processes

    Returns:
        A list of process info dataclasses
    """
    processes = []

    for proc in psutil.process_iter(
        ["pid", "name", "username", "cpu_percent", "memory_percent", "create_time", "cmdline"]
    ):
        try:
            with proc.oneshot():  # Efficient way to get multiple attributes
                info = ProcessInfo(
                    pid=proc.pid,
                    name=proc.name(),
                    username=proc.username(),
                    cpu_percent=proc.cpu_percent(),
                    memory_percent=proc.memory_percent(),
                    memory_mb=proc.memory_info().rss / 1024 / 1024,
                    status=proc.status(),
                    create_time=proc.create_time(),
                    command=" ".join(proc.cmdline()) if proc.cmdline() else proc.name(),
                )

                if filter_func is None or filter_func(info):
                    processes.append(info)

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return processes


class ProcessStatus:
    """
    The ProcessStatus is basically a dataclass that contains the status information of a running
    process.

    The available information is the following:

    * pid: the process identifier
    * uptime: the process up-time as a floating point number expressed in seconds
    * uuid: the UUID1 for this process
    * memory info: memory information on the process
    * cpu usage, percentage and count (number of physical cores)

    The status will always be updated before returning or printing.

    Parameters:
        metrics_prefix: the prefix that identifies the process for which these metrics are gathered.
    """

    def __init__(self, *, metrics_prefix: Optional[str] = None):
        self._process = psutil.Process()
        self._cpu_count = psutil.cpu_count(logical=False)
        with self._process.oneshot():
            self._pid: int = self._process.pid
            self._create_time: float = self._process.create_time()
            # not sure if we need to use interval=0.1 as an argument in the next call
            self._cpu_percent: float = self._process.cpu_percent()
            self._cpu_times = self._process.cpu_times()
            self._uptime = datetime.datetime.now(tz=datetime.timezone.utc).timestamp() - self._create_time
            self._memory_info = self._process.memory_full_info()
        self._uuid: uuid.UUID = uuid.uuid1()

        metrics_prefix = f"{metrics_prefix.lower()}_" if metrics_prefix else ""

        self.metrics = dict(
            PSUTIL_NUMBER_OF_CPU=Gauge(
                f"{metrics_prefix}psutil_number_of_cpu", "Number of physical cores, excluding hyper thread CPUs"
            ),
            PSUTIL_CPU_TIMES=Gauge(
                f"{metrics_prefix}psutil_cpu_times_seconds", "Accumulated process time in seconds", ["type"]
            ),
            PSUTIL_CPU_PERCENT=Gauge(
                f"{metrics_prefix}psutil_cpu_percent", "The current process CPU utilization as a percentage"
            ),
            PSUTIL_PID=Gauge(f"{metrics_prefix}psutil_pid", "Process ID"),
            PSUTIL_MEMORY_INFO=Gauge(
                f"{metrics_prefix}psutil_memory_info_bytes", "Memory info for this instrumented process", ["type"]
            ),
            PSUTIL_NUMBER_OF_THREADS=Gauge(
                f"{metrics_prefix}psutil_number_of_threads", "Return the number of Thread objects currently alive"
            ),
            PSUTIL_PROC_UPTIME=Gauge(
                f"{metrics_prefix}psutil_process_uptime",
                "Return the time in seconds that the process is up and running",
            ),
        )

        self.metrics["PSUTIL_NUMBER_OF_CPU"].set(self._cpu_count)
        self.metrics["PSUTIL_PID"].set(self._process.pid)

        self.update()

    def update_metrics(self):
        """
        Updates the metrics that are taken from the psutils module.

        The following metrics are never updated since they are not changed during a
        process execution:

          * PSUTIL_NUMBER_OF_CPU
          * PSUTIL_PID
        """

        self.metrics["PSUTIL_MEMORY_INFO"].labels(type="rss").set(self._memory_info.rss)
        self.metrics["PSUTIL_MEMORY_INFO"].labels(type="uss").set(self._memory_info.uss)
        self.metrics["PSUTIL_CPU_TIMES"].labels(type="user").set(self._cpu_times.user)
        self.metrics["PSUTIL_CPU_TIMES"].labels(type="system").set(self._cpu_times.system)
        self.metrics["PSUTIL_CPU_PERCENT"].set(self._cpu_percent)
        self.metrics["PSUTIL_NUMBER_OF_THREADS"].set(threading.active_count())
        self.metrics["PSUTIL_PROC_UPTIME"].set(self._uptime)

    def update(self) -> ProcessStatus:
        """
        Updates those values that change during execution, like memory usage, number of
        connections, ...

        This call will also update the metrics!

        Returns:
            the ProcessStatus object, self.
        """
        self._cpu_percent = self._process.cpu_percent()
        self._cpu_times = self._process.cpu_times()
        self._uptime = time.time() - self._create_time
        self._memory_info = self._process.memory_full_info()

        self.update_metrics()

        return self

    def as_dict(self) -> dict:
        """Returns all process information as a dictionary.

        This runs the `update()` method first to bring the numbers up-to-date.
        """
        self.update()
        return {
            "PID": self._pid,
            "Up": self._uptime,
            "UUID": self._uuid,
            "RSS": self._memory_info.rss,
            "USS": self._memory_info.uss,
            "CPU User": self._cpu_times.user,
            "CPU System": self._cpu_times.system,
            "CPU count": self._cpu_count,
            "CPU%": self._cpu_percent,
        }

    def __str__(self):
        self.update()
        msg = (
            f"PID: {self._pid}, "
            f"Up: {humanize_seconds(self._uptime)}, "
            f"UUID: {self._uuid}, "
            f"RSS: {humanize_bytes(self._memory_info.rss)}, "
            f"USS: {humanize_bytes(self._memory_info.uss)}, "
            f"CPU User: {humanize_seconds(self._cpu_times.user)}, "
            f"CPU System: {humanize_seconds(self._cpu_times.system)}, "
            f"CPU Count: {self._cpu_count}, "
            f"CPU%: {self._cpu_percent}"
        )
        return msg


#  * can we restart the same sub process?
#  * do we need to pass the additional arguments to the constructor or to the execute method?
#    When we can restart/re-execute a subprocess, we might want to do that with additional
#    arguments, e.g. to set a debugging flag or to start in simulator mode. Then we will need to
#    do that in the execute method.
#  * Process should have a notion of UUID, which it can request at start-up to communicate to the
#    process manager which can then check if it's known already or a new process that was started
#    (possible on another computer)


class SubProcess:
    """
    A SubProcess that is usually started by the ProcessManager.

    Example:

        proc = SubProcess("MyApp", [sys.executable, "-m", "egse.<module>"])
        proc.execute()



    """

    def __init__(
        self,
        name: str,
        cmd: List,
        args: List = None,
        shell: bool = False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ):
        self._popen = None
        self._sub_process: psutil.Process | None = None
        self._name = name
        self._cmd = [str(x) for x in cmd]
        self._args = [str(x) for x in args] if args else []
        self._shell = shell
        self._stdout = stdout
        self._stderr = stderr

        self._exc_info = {}

    def execute(self) -> bool:
        """
        Execute the sub-process.

        Returns:
            True if the process could be started, False on error.
        """
        self._exc_info = {}

        try:
            command: List | str = [*self._cmd, *self._args]
            if self._shell:
                command = " ".join(command)
            logger.debug(f"SubProcess command: {command}")
            self._popen = subprocess.Popen(
                command,
                env=os.environ,
                shell=self._shell,  # executable='/bin/bash',
                stdout=self._stdout,
                stderr=self._stderr,
                stdin=subprocess.DEVNULL,
            )
            self._sub_process = psutil.Process(self._popen.pid)

            logger.debug(
                f"SubProcess started: {command}, pid={self._popen.pid}, sub_process="
                f"{self._sub_process} [pid={self._sub_process.pid}]"
            )
        except Exception as exc:
            # This error is raised when the command is not an executable or is not found
            logger.error(f"Could not execute sub-process: {exc}", exc_info=True)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self._exc_info = {
                "exc_type": exc_type,
                "exc_value": exc_value,
                "exc_traceback": exc_traceback,
                "command": " ".join([*self._cmd, *self._args]),
            }
            return False
        return True

    @property
    def name(self):
        return self._name

    @property
    def pid(self) -> int:
        return self._sub_process.pid if self._sub_process else None

    @property
    def exc_info(self) -> dict:
        return self._exc_info

    def cmdline(self) -> str:
        return " ".join(self._sub_process.cmdline())

    def children(self, recursive: bool = True) -> List:
        return self._sub_process.children(recursive=recursive)

    def is_child(self, pid: int):
        return any(pid == p.pid for p in self._sub_process.children(recursive=True))

    def is_running(self) -> bool:
        """
        Check if this process is still running.

        * checks if process exists
        * checks if process is not a zombie and is not dead

        Returns:
            True if the process is running.
        """
        if self._sub_process is None:
            return False
        if self._sub_process.is_running():
            # it still might be a zombie process
            if self._sub_process.status() in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                logger.warning("The sub-process is dead or a zombie.")
                return False
            return True
        # logger.debug(f"Return value of the sub-process: {self._popen.returncode}")
        return False

    def is_dead_or_zombie(self):
        if self._sub_process is None:
            return False
        if self._sub_process.is_running():
            # it might be a zombie process
            if self._sub_process.status() in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                return True
        return False

    def exists(self) -> bool:
        """
        Checks if the sub-process exists by checking if its process ID exists.

        Returns:
            True if the sub-process exists.
        """
        return psutil.pid_exists(self.pid)

    def quit(self) -> int:
        """
        Send a request to quit to the process.

        This will first send a SIGTERM signal to the process, if that fails,
        a SIGKILL will be sent.

        Returns:
            0 if the process and its sub-processes are all terminated. Will
                return > 0 to indicate the number of processes that survived the
                SIGKILL.
        """
        return self.reap_children()

    def reap_children(self, timeout=3) -> int:
        """
        Tries hard to terminate and ultimately kill all the children of this process.

        This will first send a SIGTERM signal to the process, if that fails,
        a SIGKILL will be sent.

        Returns:
            0 if the process and its sub-processes are all terminated. Will
                return > 0 to indicate the number of processes that survived the
                SIGKILL.
        """

        def on_terminate(proc):
            logger.info(f"process {proc} terminated with exit code {proc.returncode}")

        return_code = 0
        self._exc_info = {}

        children = self._sub_process.children()

        logger.info(f"Children: {children}")

        # send SIGTERM to subprocess

        try:
            logger.info(f"Send a SIGTERM to process with PID={self.pid}")
            self._sub_process.terminate()
            try:
                return_code = self._sub_process.wait(timeout=5.0)  # make this timeout an instance parameter
                logger.info(f"{return_code = }")
            except psutil.TimeoutExpired:
                logger.info(f"TimeoutExpired after 5s for PID={self.pid}")
                logger.info(f"Send a SIGKILL to process with PID={self.pid}")

                exc_type, exc_value, exc_traceback = sys.exc_info()
                self._exc_info = {
                    "exc_type": exc_type,
                    "exc_value": exc_value,
                    "exc_traceback": exc_traceback,
                    "command": " ".join([*self._cmd, *self._args]),
                }

                self._sub_process.kill()
                return -9  # meaning the process was terminated by a SIGKILL
        except psutil.NoSuchProcess:
            # If we get here, the process died already and there are also no children to terminate
            logger.info(f"NoSuchProcess with PID={self._sub_process.pid}")

            exc_type, exc_value, exc_traceback = sys.exc_info()
            self._exc_info = {
                "exc_type": exc_type,
                "exc_value": exc_value,
                "exc_traceback": exc_traceback,
                "command": " ".join([*self._cmd, *self._args]),
            }

            return 0

        # now terminate the children

        if children:
            for p in children:
                try:
                    logger.info(f"Send a SIGTERM to child process with PID={p.pid}")
                    p.terminate()
                except psutil.NoSuchProcess:
                    pass
            gone, alive = psutil.wait_procs(children, timeout=timeout, callback=on_terminate)
            if alive:
                # send SIGKILL
                for p in alive:
                    logger.info(f"Child process {p} survived SIGTERM; trying SIGKILL")
                    try:
                        logger.info(f"Send a SIGKILL to child process with PID={p.pid}")
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
                gone, alive = psutil.wait_procs(alive, timeout=timeout, callback=on_terminate)
                if alive:
                    # give up
                    for p in alive:
                        logger.info(f"Child process {p} survived SIGKILL; giving up")

        return return_code

    def returncode(self):
        """
        Check if the sub-process is terminated and return its return code or None when the process
        is still running.
        """
        return self._popen.poll() if self._popen else None

    def communicate(self) -> tuple[str, str]:
        output, error = self._popen.communicate()
        return output.decode() if output else None, error.decode() if error else None


def list_processes(
    items: List[str] | str, contains: bool = True, case_sensitive: bool = False, verbose: bool = False
) -> list[dict]:
    """
    Returns and optionally prints the processes that match the given criteria in items.

    Args:
        items: a string or a list of strings that should match command line parts
        contains: if True, the match is done with 'in' otherwise '==' [default: True]
        case_sensitive: if True, the match shall be case-sensitive [default: False]
        verbose: if True, the processes will be printed to the console

    Returns:
        A list of dictionaries for the matching processes. The dict contains the
            'pid', 'status' and 'cmdline' of a process.
    """
    procs = is_process_running(items, contains=contains, case_sensitive=case_sensitive, as_list=True)

    result = []

    for pid in procs:
        proc = psutil.Process(pid)
        status = proc.status()
        cmdline = " ".join(proc.cmdline())
        result.append({"pid": pid, "status": status, "cmdline": cmdline})

    if verbose:
        if result:
            print(f"{'PID':5s} {'Status':>20s} {'Commandline'}")
            print("\n".join([f"{entry['pid']:5d} {entry['status']:>20s} {entry['cmdline']}" for entry in result]))
        else:
            print(f"No processes found for {items}.")

    return result


def list_zombies() -> list[dict]:
    """
    Returns a list of zombie processes.

    A zombie process, also known as a defunct process, is a process that has
    completed its execution but still has an entry in the process table.
    This happens when a child process terminates, but the parent process hasn't
    yet read its exit status by using a system call like wait(). As a result,
    the process is "dead" (it has completed execution) but hasn't been "reaped"
    or removed from the system's process table.

    A zombie process can not be killed with SIGKILL because it's already dead, and
    it's only removed when the parent process reads their exit status or when the
    parent process itself terminates.

    A zombie process does not block ports, so it's mostly harmless and will disappear
    when the parent process terminates.

    Returns:
        A list of dictionaries with information on the zombie processes. The dict
            contains the 'pid', 'name', and 'cmdline' of the zombie process.
    """
    zombies = []

    for proc in psutil.process_iter(["pid", "name", "status", "cmdline"]):
        try:
            if proc.info["status"] == psutil.STATUS_ZOMBIE:
                zombies.append(
                    {
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                        "cmdline": proc.info["cmdline"],
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    return zombies


def is_process_running(
    items: List[str] | str, contains: bool = True, case_sensitive: bool = False, as_list: bool = False
) -> int | List[int]:
    """
    Check if there is any running process that contains the given items in its
    commandline.

    Loops over all running processes and tries to match all items in the 'items'
    argument to the command line of the process. If all 'items' can be matched
    to a process, the function returns the PID of that process.

    By default, only the first matching process PID is returned. If `as_list=True`
    then all mathing process PIDs are returned as a list.

    Args:
        items: a string or a list of strings that should match command line parts
        contains: if True, the match is done with 'in' otherwise '==' [default: True]
        case_sensitive: if True, the match shall be case-sensitive [default: False]
        as_list: return the PID of all matching processes as a list [default: False]

    Returns:
        The PID(s) if there exists a running process with the given items, 0 or [] otherwise.
    """

    def lower(x: str) -> str:
        return x.lower()

    def pass_through(x: str) -> str:
        return x

    case = pass_through if case_sensitive else lower

    if not items:
        logger.warning("Expected at least one item in 'items', none were given. False returned.")
        return [] if as_list else 0

    items = [items] if isinstance(items, str) else items

    found = []

    for proc in psutil.process_iter(attrs=["pid", "cmdline", "name"], ad_value="n/a"):
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # logger.info(f"{proc.name().lower() = }, {proc.cmdline() = }")
            if contains:
                if all(any(case(y) in case(x) for x in proc.cmdline()) for y in items):
                    found.append(proc.pid)
            elif all(any(case(y) == case(x) for x in proc.cmdline()) for y in items):
                found.append(proc.pid)
    if found:
        return found if as_list else found[0]
    else:
        return [] if as_list else 0


def get_process_info(items: List[str] | str, contains: bool = True, case_sensitive: bool = False) -> List:
    """
    Loops over all running processes and tries to match each item in 'items' to the command line
    of the process. Any process where all 'items' can be matched will end up in the response.

    Returns a list with the process info (PID, cmdline, create_time) for any processes where all 'items' match
    the process command line. An empty list is returned when not 'all the items' match for any of the
    processes.

    Examples:
        >>> get_process_info(items=["feesim"])
        [
            {
                'pid': 10166,
                'cmdline': [
                    '/Library/Frameworks/Python.framework/Versions/3.8/Resources/Python.app/Contents/MacOS/Python',
                    '/Users/rik/git/plato-common-egse/venv38/bin/feesim',
                    'start',
                    '--zeromq'
                ],
                'create_time': 1664898231.915995
            }
        ]

        >>> get_process_info(items=["dpu_cs", "--zeromq"])
        [
            {
                'pid': 11595,
                'cmdline': [
                    '/Library/Frameworks/Python.framework/Versions/3.8/Resources/Python.app/Contents/MacOS/Python',
                    '/Users/rik/git/plato-common-egse/venv38/bin/dpu_cs',
                    'start',
                    '--zeromq'
                ],
                'create_time': 1664898973.542281
            }
        ]

    Args:
        items: a string or a list of strings that should match command line items
        contains: if True, the match is done with 'in' otherwise '=='
        case_sensitive: if True, the match shall be case-sensitive

    Returns:
        A list of process info entries.

    """
    response = []

    def lower(x: str) -> str:
        return x.lower()

    def pass_through(x: str) -> str:
        return x

    case = pass_through if case_sensitive else lower

    if not items:
        logger.warning("Expected at least one item in 'items', none were given. Empty list returned.")
        return response

    items = [items] if isinstance(items, str) else items

    for proc in psutil.process_iter():
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # logger.info(f"{proc.name().lower() = }, {proc.cmdline() = }")
            if contains:
                if all(any(case(y) in case(x) for x in proc.cmdline()) for y in items):
                    response.append(proc.as_dict(attrs=["pid", "cmdline", "create_time"]))
            elif all(any(case(y) == case(x) for x in proc.cmdline()) for y in items):
                response.append(proc.as_dict(attrs=["pid", "cmdline", "create_time"]))

    return response


def ps_egrep(pattern):
    # First command-line
    ps_command = ["ps", "-ef"]

    # Second command-line
    grep_command = ["egrep", pattern]

    # Launch first process
    ps_process = subprocess.Popen(ps_command, stdout=subprocess.PIPE)

    # Launch second process and connect it to the first one
    grep_process = subprocess.Popen(grep_command, stdin=ps_process.stdout, stdout=subprocess.PIPE)

    # Let stream flow between them
    output, _ = grep_process.communicate()

    response = [line for line in output.decode().rstrip().split("\n") if line and "egrep " not in line]

    return response


def kill_process(pid: int, force: bool = False):
    """Safely kill a process. Return True if process could be killed, False otherwise.

    If the process doesn't exist, or you have don't the right permission to kill the process, False is returned.
    """
    try:
        proc = psutil.Process(pid)
        if force:
            proc.kill()
        else:
            proc.terminate()
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
