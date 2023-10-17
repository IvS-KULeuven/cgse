"""
This module provides functions and classes to work with processes and sub-processes.
"""
from __future__ import annotations

import contextlib
import datetime
import logging
import os
import subprocess
import threading
import time
import uuid
from typing import List
from typing import Optional

import psutil
from prometheus_client import Gauge

from egse.bits import humanize_bytes
from egse.system import humanize_seconds

LOGGER = logging.getLogger(__name__)


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
            self._uptime = (
                    datetime.datetime.now(tz=datetime.timezone.utc).timestamp() - self._create_time
            )
            self._memory_info = self._process.memory_full_info()
        self._uuid: uuid.UUID = uuid.uuid1()

        metrics_prefix = f"{metrics_prefix.lower()}_" if metrics_prefix else ""

        self.metrics = dict(
            PSUTIL_NUMBER_OF_CPU=Gauge(
                f"{metrics_prefix}psutil_number_of_cpu",
                "Number of physical cores, excluding hyper thread CPUs"
            ),
            PSUTIL_CPU_TIMES=Gauge(
                f"{metrics_prefix}psutil_cpu_times_seconds",
                "Accumulated process time in seconds", ["type"]
            ),
            PSUTIL_CPU_PERCENT=Gauge(
                f"{metrics_prefix}psutil_cpu_percent",
                "The current process CPU utilization as a percentage"
            ),
            PSUTIL_PID=Gauge(
                f"{metrics_prefix}psutil_pid", "Process ID"
            ),
            PSUTIL_MEMORY_INFO=Gauge(
                f"{metrics_prefix}psutil_memory_info_bytes",
                "Memory info for this instrumented process",
                ["type"]
            ),
            PSUTIL_NUMBER_OF_THREADS=Gauge(
                f"{metrics_prefix}psutil_number_of_threads",
                "Return the number of Thread objects currently alive"
            ),
            PSUTIL_PROC_UPTIME=Gauge(
                f"{metrics_prefix}psutil_proccess_uptime",
                "Return the time in seconds that the process is up and running"
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

    def update(self):
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

    def as_dict(self):
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

    Usage:

        hexapod_ui = SubProcess("MyApp", [sys.executable, "-m", "egse.hexapod.hexapod_ui"])
        hexapod_ui.execute()

    """

    def __init__(
            self, name: str, cmd: List, args: List = None, shell: bool = True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ):
        self._popen = None
        self._sub_process: psutil.Process | None = None
        self._name = name
        self._cmd = cmd
        self._args = args or []
        self._shell = shell
        self._stdout = stdout
        self._stderr = stderr

    def execute(self, detach_from_parent=False) -> bool:
        """ Execute the sub-process.

        Args:
            - detach_from_parent: Boolean indicating whether the sub-process should be detached from the
                                  parent process.  If set to False, the sub-process will be killed whenever the
                                  parent process is interrupted or stopped.
        """

        try:
            command: List = [*self._cmd, *self._args]
            LOGGER.debug(f"SubProcess command: {command}")
            # self._popen = subprocess.Popen(command, env=os.environ, close_fds=detach_from_parent)
            self._popen = subprocess.Popen(
                " ".join(command),
                env=os.environ,
                shell=self._shell,  # executable='/bin/bash',
                stdout=self._stdout,
                stderr=self._stderr,
                stdin=subprocess.DEVNULL,
            )
            self._sub_process = psutil.Process(self._popen.pid)

            LOGGER.debug(
                f"SubProcess started: {command}, pid={self._popen.pid}, sub_process="
                f"{self._sub_process} [pid={self._sub_process.pid}]"
            )
        except KeyError:
            LOGGER.error(f"Unknown client process: {self._name}", exc_info=True)
            return False
        except (PermissionError, FileNotFoundError) as exc:
            # This error is raised when the command is not an executable or is not found
            LOGGER.error(f"Could not execute sub-process: {exc}", exc_info=True)
            return False
        return True

    @property
    def name(self):
        return self._name

    @property
    def pid(self) -> int:
        return self._sub_process.pid if self._sub_process else None

    def cmdline(self) -> str:
        return " ".join(self._sub_process.cmdline())

    def children(self, recursive: bool = True) -> List:
        return self._sub_process.children(recursive=recursive)

    def is_child(self, pid: int):
        return any(pid == p.pid for p in self._sub_process.children(recursive=True))

    def is_running(self):
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
                LOGGER.warning("The sub-process is dead or a zombie.")
                return False
            return True
        LOGGER.debug(f"Return value of the sub-process: {self._popen.returncode}")
        return False

    def exists(self) -> bool:
        """
        Checks if the sub-process exists by checking if its process ID exists.

        Returns:
            True if the sub-process exists.
        """
        return psutil.pid_exists(self.pid)

    def quit(self):
        """
        Send a request to quit to the process.

        This sends a ZeroMQ message "Quit" to the process. The process is expected to answer with
        "Quiting" and then
        actually ends its execution.

        Returns:
            True when received the answer "Quiting", False otherwise.
        """
        return self.reap_children()

    def reap_children(self, timeout=3):
        """Tries hard to terminate and ultimately kill all the children of this process."""

        def on_terminate(proc):
            LOGGER.info(f"process {proc} terminated with exit code {proc.returncode}")

        return_code = 0

        procs = [self._sub_process]
        procs.extend(self._sub_process.children())

        LOGGER.info(f"Processes: {procs}")

        # send SIGTERM
        for p in procs:
            try:
                LOGGER.info(f"Terminating process {p}")
                p.terminate()
            except psutil.NoSuchProcess:
                pass
        gone, alive = psutil.wait_procs(procs, timeout=timeout, callback=on_terminate)
        if alive:
            # send SIGKILL
            for p in alive:
                LOGGER.info(f"process {p} survived SIGTERM; trying SIGKILL")
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            gone, alive = psutil.wait_procs(alive, timeout=timeout, callback=on_terminate)
            if alive:
                # give up
                for p in alive:
                    LOGGER.info(f"process {p} survived SIGKILL; giving up")
                    return_code += 1  # return code indicates how many processes are still running

        return return_code

    def returncode(self):
        """
        Check if the sub-process is terminated and return its return code or None when the process
        is still running.
        """
        return self._popen.poll()

    def communicate(self) -> tuple[str, str]:
        output, error = self._popen.communicate()
        return output.decode() if output else None, error.decode() if error else None


def is_process_running(items: List[str] | str, contains: bool = True, case_sensitive: bool = False):
    """
    Check if there is any running process that contains the given items in its commandline.

    Loops over all running processes and tries to match all items in 'cmd_line_items' to the command line
    of the process. If all 'cmd_line_items' can be matched to a process, the function returns True.

    Args:
        items: a string or a list of strings that should match command line parts
        contains: if True, the match is done with 'in' otherwise '=='
        case_sensitive: if True, the match shall be case-sensitive

    Returns:
        True if there exists a running process with the given items, False otherwise.
    """

    def lower(x: str) -> str:
        return x.lower()

    def pass_through(x: str) -> str:
        return x

    case = pass_through if case_sensitive else lower

    if not items:
        LOGGER.warning("Expected at least one item in 'items', none were given. False returned.")
        return False

    items = [items] if isinstance(items, str) else items

    for proc in psutil.process_iter():
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # LOGGER.info(f"{proc.name().lower() = }, {proc.cmdline() = }")
            if contains:
                if all(any(case(y) in case(x) for x in proc.cmdline()) for y in items):
                    return True
            elif all(any(case(y) == case(x) for x in proc.cmdline()) for y in items):
                return True

    return False


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
        LOGGER.warning("Expected at least one item in 'items', none were given. Empty list returned.")
        return response

    items = [items] if isinstance(items, str) else items

    for proc in psutil.process_iter():
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # LOGGER.info(f"{proc.name().lower() = }, {proc.cmdline() = }")
            if contains:
                if all(any(case(y) in case(x) for x in proc.cmdline()) for y in items):
                    response.append(proc.as_dict(attrs=['pid', 'cmdline', 'create_time']))
            elif all(any(case(y) == case(x) for x in proc.cmdline()) for y in items):
                response.append(proc.as_dict(attrs=['pid', 'cmdline', 'create_time']))

    return response
