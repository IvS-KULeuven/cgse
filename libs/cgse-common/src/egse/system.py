"""
The system module defines convenience functions that provide information on system specific
functionality like, file system interactions, timing, operating system interactions, etc.

The module has external dependencies to:

* __distro__: for determining the Linux distribution
* __psutil__: for system statistics
* __rich__: for console output

"""

from __future__ import annotations

import asyncio
import builtins
import collections
import contextlib
import datetime
import functools
import importlib
import importlib.metadata
import importlib.util
import inspect
import itertools
import logging
import math
import operator
import os
import platform  # For getting the operating system name
import re
import socket
import subprocess  # For executing a shell command
import sys
import threading
import time
import warnings
from collections import namedtuple
from contextlib import contextmanager
from io import SEEK_END
from io import SEEK_SET
from pathlib import Path
from types import FunctionType
from types import ModuleType
from typing import Any
from typing import Callable
from typing import Iterable
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
from typing import Union

import distro  # For determining the Linux distribution
import psutil
from rich.console import Console
from rich.text import Text
from rich.tree import Tree
from typer.core import TyperCommand

import signal
from egse.log import logger

EPOCH_1958_1970 = 378691200
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


# ACKNOWLEDGEMENT: The class is based on the textual.timer.Timer class from the Textual project.
class Periodic:
    """A timer that periodically invokes a function in the background.

    If no callback is provided, a warning message will be logged. In a future, we might send out an event to the
    application (will need an event handler).

    When the function execution takes longer then the interval there re several options:

    - if skip is True (default) the interval will take precedence and the
    Args:
        interval: The time between timer events, in seconds.
        name: A name to assign the event (for debugging), defaults to `Periodic#`.
        callback: A optional callback to invoke when the event is handled.
        repeat: The number of times to repeat the timer, or None to repeat forever.
        skip: Enable skipping of scheduled function calls that couldn't be sent in time.
        pause: Start the timer paused. Use `resume()` to activate the timer.
    """

    _periodic_count: int = 0
    """The number of Periodic instances that are created."""

    def __init__(
        self,
        interval: float,
        *,
        name: str | None = None,
        callback: Callable = None,
        repeat: int | None = None,
        skip: bool = True,
        pause: bool = False,
    ) -> None:
        self._interval = interval
        self.name = f"Periodic#{self._periodic_count}" if name is None else name
        self._periodic_count += 1
        self._callback = callback
        self._repeat = repeat
        self._skip = skip
        self._active = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._reset: bool = False
        self._logger = logging.getLogger("periodic")
        if not pause:
            self._active.set()

    def start(self) -> None:
        """Start the timer."""
        self._task = asyncio.create_task(self._run_timer(), name=self.name)

    def stop(self) -> None:
        """Stop the timer."""
        if self._task is None:
            return

        self._active.clear()
        self._task.cancel()
        self._task = None

    def is_running(self):
        return self._active.is_set() and self._task is not None

    def is_paused(self):
        return not self._active.is_set()

    def pause(self) -> None:
        """Pause the timer.

        A paused timer will not send events until it is resumed.
        """
        self._active.clear()

    def reset(self) -> None:
        """Reset the timer, so it starts from the beginning."""
        self._active.set()
        self._reset = True

    def resume(self) -> None:
        """Resume a paused timer."""
        self._active.set()

    async def _run_timer(self) -> None:
        """Run the timer task."""
        try:
            await self._run()
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        """Run the timer."""
        count = 0
        _repeat = self._repeat
        _interval = self._interval
        await self._active.wait()
        start = time.monotonic()

        while _repeat is None or count < _repeat:
            next_timer = start + ((count + 1) * _interval)
            now = time.monotonic()
            # self._logger.debug(f"{count = }, {next_timer = }, {now = }")
            if self._skip and next_timer < now:
                count = int((now - start) / _interval)
                # self._logger.debug(f"Recalculated {count = }, {now - start = }, {(now - start) / _interval = }")
                continue
            now = time.monotonic()
            wait_time = max(0.0, next_timer - now)
            await asyncio.sleep(wait_time)
            count += 1
            await self._active.wait()
            if self._reset:
                start = time.monotonic()
                count = 0
                self._reset = False
                continue

            await self._tick()

        self.stop()

    async def _tick(self) -> None:
        """Triggers the Timer's action: either call its callback, or logs a message."""

        if self._callback is None:
            self._logger.warning(f"Periodic – No callback provided for interval timer {self.name}.")
            return

        try:
            await await_me_maybe(self._callback)
        except asyncio.CancelledError:
            self._logger.debug("Caught CancelledError on callback function in Periodic.")
            raise
        except Exception as exc:
            self._logger.error(f"{type(exc).__name__} caught: {exc}")

    @property
    def interval(self):
        return self._interval


def round_up(n: float | int, decimals: int = 0):
    """
    Round a number up to a specified number of decimal places.

    This function rounds the input number upward (toward positive infinity)
    regardless of the value of the digits being rounded. It uses math.ceil()
    after multiplying by a power of 10 to achieve the specified precision.

    Args:
        n (float or int): The number to round up.
        decimals (int, optional): The number of decimal places to round to.
            Must be non-negative. Defaults to 0.

    Returns:
        float: The rounded number with the specified precision.

    Examples:
        >>> round_up(3.14159, 3)
        3.142
        >>> round_up(3.1409, 3)
        3.141
        >>> round_up(-3.14159, 3)
        -3.141
        >>> round_up(5, 2)
        5.0

    Note:
        For negative numbers, "rounding up" means rounding toward zero,
        so -3.14159 rounded up to 3 decimals is -3.141.
    """
    multiplier = 10**decimals
    return math.ceil(n * multiplier) / multiplier


async def await_me_maybe(callback: Callable, *params: object) -> Any:
    """Invoke a callback with an arbitrary number of parameters.

    The callback can be a coroutine (async def) or a plain old function.
    The `await_me_maybe` awaits the result of the callback if it's an awaitable,
    or simply returns the result if not.

    Args:
        callback: The callable to be invoked.

    Returns:
        The return value of the invoked callable.
    """
    result = callback(*params)
    if inspect.isawaitable(result):
        result = await result
    return result


class TyperAsyncCommand(TyperCommand):
    """Runs an asyncio Typer command.

    Example:

        @add.command(cls=TyperAsyncCommand)
        async def start():
            ...

    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        old_callback = self.callback

        def new_callback(*args, **kwargs):
            return asyncio.run(old_callback(*args, **kwargs))

        self.callback = new_callback


@contextmanager
def all_logging_disabled(highest_level=logging.CRITICAL, flag=True):
    """
    Context manager to temporarily disable logging messages during its execution.

    Args:
        highest_level (int, optional): The maximum logging level to be disabled.
            Defaults to logging.CRITICAL.
            Note: Adjust this only if a custom level greater than CRITICAL is defined.
        flag (bool, optional): If True, disables all logging; if False, no changes are made.
            Defaults to True.

    Example:
        ```python
        with all_logging_disabled():
            ...  # Your code with logging messages disabled
        ```

    Note:
        This context manager is designed to prevent any logging messages triggered during its body
        from being processed. It temporarily disables logging and restores the previous state afterward.
    """
    # Code below is copied from https://gist.github.com/simon-weber/7853144
    # two kind-of hacks here:
    #    * can't get the highest logging level in effect => delegate to the user
    #    * can't get the current module-level override => use an undocumented
    #       (but non-private!) interface

    previous_level = logging.root.manager.disable

    if flag:
        logging.disable(highest_level)

    try:
        yield
    finally:
        logging.disable(previous_level)


def get_active_loggers() -> dict:
    """
    Retrieves information about active loggers and their respective log levels.

    Returns a dictionary where keys are the names of active loggers, and values
    are the corresponding log levels in string format.

    Returns:
        dict: A dictionary mapping logger names to their log levels.

    Note:
        This function provides a snapshot of the currently active loggers and
        their log levels at the time of the function call.

    """

    return {
        name: logging.getLevelName(logging.getLogger(name).level) for name in sorted(logging.Logger.manager.loggerDict)
    }


# The code below was taken from https://stackoverflow.com/a/69639238/4609203


def ignore_m_warning(modules=None):
    """
    Ignore RuntimeWarning by `runpy` that occurs when executing a module with `python -m package.module`,
    while that module is also imported.

    The original warning message is:

        '<package.module>' found in sys.modules after import of package '<package'>,
        but prior to execution of '<package.module>'
    """
    if not isinstance(modules, (list, tuple)):
        modules = [modules]

    try:
        import warnings
        import re

        msg = "'{module}' found in sys.modules after import of package"
        for module in modules:
            module_msg = re.escape(msg.format(module=module))
            warnings.filterwarnings("ignore", message=module_msg, category=RuntimeWarning, module="runpy")  # ignore -m
    except (ImportError, KeyError, AttributeError, Exception):
        pass


def now(utc: bool = True):
    """Returns a datetime object for the current time in UTC or local time."""
    if utc:
        return datetime.datetime.now(tz=datetime.timezone.utc)
    else:
        return datetime.datetime.now()


def format_datetime(
    dt: Union[str, datetime.datetime] = None, fmt: str = None, width: int = 6, precision: int = 3
) -> str:
    """Format a datetime as YYYY-mm-ddTHH:MM:SS.μs+0000.

    If the given argument is not timezone aware, the last part, i.e. `+0000` will not be there.

    If no argument is given, the timestamp is generated as
    `datetime.datetime.now(tz=datetime.timezone.utc)`.

    The `dt` argument can also be a string with the following values: today, yesterday, tomorrow,
    and 'day before yesterday'. The format will then be '%Y%m%d' unless specified.

    Optionally, a format string can be passed in to customize the formatting of the timestamp.
    This format string will be used with the `strftime()` method and should obey those conventions.

    Example:
        ```python
        >>> format_datetime(datetime.datetime(2020, 6, 13, 14, 45, 45, 696138))
        '2020-06-13T14:45:45.696'
        >>> format_datetime(datetime.datetime(2020, 6, 13, 14, 45, 45, 696138), precision=6)
        '2020-06-13T14:45:45.696138'
        >>> format_datetime(datetime.datetime(2020, 6, 13, 14, 45, 59, 999501), precision=3)
        '2020-06-13T14:45:59.999'
        >>> format_datetime(datetime.datetime(2020, 6, 13, 14, 45, 59, 999501), precision=6)
        '2020-06-13T14:45:59.999501'
        >>> _ = format_datetime()
        ...
        >>> format_datetime("yesterday")
        '20220214'
        >>> format_datetime("yesterday", fmt="%d/%m/%Y")
        '14/02/2022'
        ```

    Args:
        dt (datetime): a datetime object or an agreed string like yesterday, tomorrow, ...
        fmt (str): a format string that is accepted by `strftime()`
        width (int): the width to use for formatting the microseconds
        precision (int): the precision for the microseconds

    Returns:
        a string representation of the current time in UTC, e.g. `2020-04-29T12:30:04.862+0000`.

    Raises:
        ValueError: will be raised when the given dt argument string is not understood.
    """
    dt = dt or datetime.datetime.now(tz=datetime.timezone.utc)
    if isinstance(dt, str):
        fmt = fmt or "%Y%m%d"
        if dt.lower() == "yesterday":
            dt = datetime.date.today() - datetime.timedelta(days=1)
        elif dt.lower() == "today":
            dt = datetime.date.today()
        elif dt.lower() == "day before yesterday":
            dt = datetime.date.today() - datetime.timedelta(days=2)
        elif dt.lower() == "tomorrow":
            dt = datetime.date.today() + datetime.timedelta(days=1)
        else:
            raise ValueError(f"Unknown date passed as an argument: {dt}")

    if fmt:
        timestamp = dt.strftime(fmt)
    else:
        width = min(width, precision)
        timestamp = (
            f"{dt.strftime('%Y-%m-%dT%H:%M')}:"
            f"{dt.second:02d}.{dt.microsecond // 10 ** (6 - precision):0{width}d}{dt.strftime('%z')}"
        )

    return timestamp


SECONDS_IN_A_DAY = 24 * 60 * 60
SECONDS_IN_AN_HOUR = 60 * 60
SECONDS_IN_A_MINUTE = 60


def humanize_seconds(seconds: float, include_micro_seconds: bool = True) -> str:
    """
    The number of seconds is represented as `[#D]d [#H]h[#M]m[#S]s.MS` where:

    * `#D` is the number of days if days > 0
    * `#H` is the number of hours if hours > 0
    * `#M` is the number of minutes if minutes > 0 or hours > 0
    * `#S` is the number of seconds
    * `MS` is the number of microseconds

    Args:
        seconds: the number of seconds
        include_micro_seconds: True if microseconds shall be included

    Example:
        ```python
        >>> humanize_seconds(20)
        '20s.000'
        >>> humanize_seconds(10*24*60*60)
        '10d 00s.000'
        >>> humanize_seconds(10*86400 + 3*3600 + 42.023)
        '10d 03h00m42s.023'
        >>> humanize_seconds(10*86400 + 3*3600 + 42.023, include_micro_seconds=False)
        '10d 03h00m42s'
        ```

    Returns:
         a string representation for the number of seconds.
    """
    micro_seconds = round((seconds - int(seconds)) * 1000)
    rest = int(seconds)

    days = rest // SECONDS_IN_A_DAY
    rest -= SECONDS_IN_A_DAY * days

    hours = rest // SECONDS_IN_AN_HOUR
    rest -= SECONDS_IN_AN_HOUR * hours

    minutes = rest // SECONDS_IN_A_MINUTE
    rest -= SECONDS_IN_A_MINUTE * minutes

    seconds = rest

    result = ""
    if days:
        result += f"{days}d "

    if hours:
        result += f"{hours:02d}h"

    if minutes or hours:
        result += f"{minutes:02d}m"

    result += f"{seconds:02d}s"
    if include_micro_seconds:
        result += f".{micro_seconds:03d}"

    return result


def str_to_datetime(datetime_string: str) -> datetime.datetime:
    """
    Convert the given string to a datetime object.

    Args:
        datetime_string: String representing a datetime, in the format `%Y-%m-%dT%H:%M:%S.%f%z`.

    Returns:
        a datetime object.
    """

    return datetime.datetime.strptime(datetime_string.strip("\r"), TIME_FORMAT)


def duration(dt_start: str | datetime.datetime, dt_end: str | datetime.datetime) -> datetime.timedelta:
    """
    Returns a `timedelta` object with the duration, i.e. time difference between dt_start and dt_end.

    Notes:
        If you need the number of seconds of your measurement, use the `total_seconds()` method of
        the timedelta object.

        Even if you —by accident— switch the start and end time arguments, the duration will
        be calculated as expected.

    Args:
        dt_start: start time of the measurement
        dt_end: end time of the measurement

    Returns:
        The time difference (duration) between dt_start and dt_end.
    """
    if isinstance(dt_start, str):
        dt_start = str_to_datetime(dt_start)
    if isinstance(dt_end, str):
        dt_end = str_to_datetime(dt_end)

    return dt_end - dt_start if dt_end > dt_start else dt_start - dt_end


def time_since_epoch_1958(datetime_string: str) -> float:
    """
    Calculate the time since epoch 1958 for the given string representation of a datetime.

    Args:
        datetime_string: String representing a datetime, in the format `%Y-%m-%dT%H:%M:%S.%f%z`.

    Returns:
        Time since the 1958 epoch [s].
    """

    time_since_epoch_1970 = str_to_datetime(datetime_string).timestamp()  # Since Jan 1st, 1970, midnight

    return time_since_epoch_1970 + EPOCH_1958_1970


class Timer:
    """
    Context manager to benchmark some lines of code.

    When the context exits, the elapsed time is sent to the default logger (level=INFO).

    Elapsed time can be logged with the `log_elapsed()` method and requested in fractional seconds
    by calling the class instance. When the contexts goes out of scope, the elapsed time will not
    increase anymore.

    Log messages are sent to the logger (including egse_logger for egse.system) and the logging
    level can be passed in as an optional argument. Default logging level is INFO.

    Args:
        name (str): a name for the Timer, will be printed in the logging message
        precision (int): the precision for the presentation of the elapsed time
            (number of digits behind the comma)
        log_level (int): the log level to report the timing [default=INFO]

    Example:
        ```Python
        with Timer("Some calculation") as timer:
            # do some calculations
            timer.log_elapsed()
            # do some more calculations
            print(f"Elapsed seconds: {timer()}")
        Elapsed seconds: ...
        ```
    """

    def __init__(self, name="Timer", precision=3, log_level=logging.INFO):
        self.name = name
        self.precision = precision
        self.log_level = log_level
        caller_info = get_caller_info(level=2)
        self.filename = caller_info.filename
        self.func = caller_info.function
        self.lineno = caller_info.lineno

    def __enter__(self):
        # start is a value containing the start time in fractional seconds
        # end is a function which returns the time in fractional seconds
        self.start = time.perf_counter()
        self.end = time.perf_counter
        self._last_elapsed = time.perf_counter()
        return self

    def __exit__(self, ty, val, tb):
        # The context goes out of scope here and we fix the elapsed time
        self._total_elapsed = time.perf_counter()
        self._last_elapsed = self._total_elapsed

        # Overwrite self.end() so that it always returns the fixed end time
        self.end = self._end

        logger.log(
            self.log_level,
            f"{self.name} [ {self.filename}:{self.func}:{self.lineno} ]: "
            f"{self.end() - self.start:0.{self.precision}f} seconds",
        )
        return False

    def __call__(self):
        return self.end() - self.start

    def log_elapsed(self):
        """Sends the elapsed time info to the default logger."""
        current_lap = self.end()
        logger.log(
            self.log_level,
            f"{self.name} [ {self.func}:{self.lineno} ]: "
            f"{current_lap - self.start:0.{self.precision}f} seconds elapsed, "
            f"{current_lap - self._last_elapsed:0.{self.precision}f}s since last lap.",
        )
        self._last_elapsed = current_lap

    def get_elapsed(self) -> float:
        """Returns the elapsed time for this timer as a float in seconds."""
        return self.end() - self.start

    def _end(self):
        return self._total_elapsed


def ping(host, timeout: float = 3.0) -> bool:
    """
    Sends a ping request to the given host.

    Remember that a host may not respond to a ping (ICMP) request even if the host name is valid.

    Args:
        host (str): hostname or IP address (as a string)
        timeout (float): timeout in seconds

    Returns:
        True when host responds to a ping request.

    Reference:
        [SO – Pinging servers in Python](https://stackoverflow.com/a/32684938)
    """

    # Option for the number of packets as a function of
    param = "-n" if platform.system().lower() == "windows" else "-c"

    # Building the command. Ex: "ping -c 1 google.com"
    command = ["ping", param, "1", host]

    try:
        return subprocess.call(command, stdout=subprocess.DEVNULL, timeout=timeout) == 0
    except subprocess.TimeoutExpired:
        logging.info(f"Ping to {host} timed out in {timeout} seconds.")
        return False


def get_host_ip() -> Optional[str]:
    """Returns the IP address. If no IP address can be found, None will be returned and the caller can try
    to use localhost."""

    host_ip = None

    # The following code needs internet access

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # sock.connect(("8.8.8.8", 80))
        sock.connect(("10.255.255.255", 1))
        host_ip = sock.getsockname()[0]
        sock.close()
    except Exception as exc:
        logger.warning(f"{type(exc).__name__} caught: {exc}")

    if host_ip:
        return host_ip

    # This may still return 127.0.0.1 when hostname is defined in /etc/hosts
    try:
        host_name = socket.gethostname()
        host_ip = socket.gethostbyname(host_name)
        return host_ip
    except Exception as exc:
        logger.warning(f"{type(exc).__name__} caught: {exc}")

    return None


def get_current_location():
    """
    Returns the location where this function is called, i.e. the filename, line number, and function name.
    """
    frame = inspect.currentframe().f_back

    filename = inspect.getframeinfo(frame).filename
    line_number = inspect.getframeinfo(frame).lineno
    function_name = inspect.getframeinfo(frame).function

    # Clean up to prevent reference cycles
    del frame

    return filename, line_number, function_name


CallerInfo = namedtuple("CallerInfo", "filename function lineno")


def get_caller_info(level=1) -> CallerInfo:
    """
    Returns the filename, function name and lineno of the caller.

    The level indicates how many levels to go back in the stack.
    When level is 0 information about this function will be returned. That is usually not
    what you want so the default level is 1 which returns information about the function
    where the call to `get_caller_info` was made.

    Args:
        level (int): the number of levels to go back in the stack

    Returns:
        a namedtuple: `CallerInfo['filename', 'function', 'lineno']`.
    """
    frame = inspect.currentframe()
    for _ in range(level):
        if frame.f_back is None:
            break
        frame = frame.f_back
    frame_info = inspect.getframeinfo(frame)

    return CallerInfo(frame_info.filename, frame_info.function, frame_info.lineno)


def get_caller_breadcrumbs(prefix: str = "call stack: ", limit: int = 5, with_filename: bool = False) -> str:
    """
    Returns a string representing the calling sequence of this function. The string contains the calling sequence from
    left to right. Each entry has the function name and the line number of the line being executed.
    When the `with_filename` is `True`, also the filename is printed before the function name. If the file
    is `__init__.py`, also the parent folder name is printed.

        <filename>:<function name>[<lineno>] <— <filename>:<caller function name>[<lineno>]

    Use this function for example if you need to find out when and where a function is called in your process.

    Example:
        ```text
        state.py:load_setup[126] <- state.py:setup[103] <- spw.py:__str__[167] <- nfeesim.py:run[575]
        ```

    Args:
        prefix: a prefix for the calling sequence [default='call stack: '].
        limit: the maximum number of caller to go back up the calling stack [default=5].
        with_filename: filename is included in the returned string when True [default=False].

    Returns:
        A string containing the calling sequence.
    """
    frame = inspect.currentframe()
    msg = []
    while (frame := frame.f_back) is not None:
        fi = inspect.getframeinfo(frame)
        if with_filename:
            filename = Path(fi.filename)
            if filename.name == "__init__.py":
                filename = f"{filename.parent.name}/{filename.name}:"
            else:
                filename = f"{filename.name}:"
        else:
            filename = ""
        msg.append(f"{filename}{fi.function}[{fi.lineno}]")
        if (limit := limit - 1) == 0:
            break

    return prefix + " <- ".join(msg)


def get_referenced_var_name(obj: Any) -> List[str]:
    """
    Returns a list of variable names that reference the given object.
    The names can be both in the local and global namespace of the object.

    Args:
        obj (Any): object for which the variable names are returned

    Returns:
        a list of variable names.
    """
    frame = inspect.currentframe().f_back
    f_locals = frame.f_locals
    f_globals = frame.f_globals
    if "self" in f_locals:
        f_locals = frame.f_back.f_locals
    name_set = [k for k, v in {**f_locals, **f_globals}.items() if v is obj]
    return name_set or []


class AttributeDict(dict):
    """
    This class is and acts like a dictionary but has the additional functionality
    that all keys in the dictionary are also accessible as instance attributes.

        >>> ad = AttributeDict({'a': 1, 'b': 2, 'c': 3})

        >>> assert ad.a == ad['a']
        >>> assert ad.b == ad['b']
        >>> assert ad.c == ad['c']

    Similarly, adding or defining attributes will make them also keys in the dict.

        >>> ad.d = 4  # creates a new attribute
        >>> print(ad['d'])
        4
    """

    def __init__(self, *args, label: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__["_label"] = label

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    @property
    def label(self):
        return self.__dict__["_label"]

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __rich__(self) -> Tree:
        label = self.__dict__["_label"] or "AttributeDict"
        tree = Tree(label, guide_style="dim")
        walk_dict_tree(self, tree, text_style="dark grey")
        return tree

    def __repr__(self):
        # We only want the first 10 key:value pairs

        count = 10
        sub_msg = ", ".join(f"{k!r}:{v!r}" for k, v in itertools.islice(self.items(), 0, count))

        lbl = f", label='{self.__dict__['_label']}'" if self.label else ""

        # if we left out key:value pairs, print a ', ...' to indicate incompleteness
        return self.__class__.__name__ + f"({{{sub_msg}{', ...' if len(self) > count else ''}}}{lbl})"


attrdict = AttributeDict
"""Shortcut for the AttributeDict class."""


def walk_dict_tree(dictionary: dict, tree: Tree, text_style: str = "green"):
    for k, v in dictionary.items():
        if isinstance(v, dict):
            branch = tree.add(f"[purple]{k}", style="", guide_style="dim")
            walk_dict_tree(v, branch, text_style=text_style)
        else:
            text = Text.assemble((str(k), "medium_purple1"), ": ", (str(v), text_style))
            tree.add(text)


def recursive_dict_update(this: dict, other: dict) -> dict:
    """
    Recursively update a dictionary `this` with the content of another dictionary `other`.

    Any key in `this` dictionary will be recursively updated with the value of the same key in the
    `other` dictionary.

    Please note that the update will be in-place, i.e. the `this` dictionaory will be
    changed/updated.
    ```python
    >>> global_settings = {"A": "GA", "B": "GB", "C": "GC"}
    >>> local_settings = {"B": "LB", "D": "LD"}
    >>> {**global_settings, **local_settings}
    {'A': 'GA', 'B': 'LB', 'C': 'GC', 'D': 'LD'}

    >>> global_settings = {"A": "GA", "B": "GB", "C": "GC", "R": {"X": "GX", "Y": "GY"}}
    >>> local_settings = {"B": "LB", "D": "LD", "R": {"Y": "LY"}}
    >>> recursive_dict_update(global_settings, local_settings)
    {'A': 'GA', 'B': 'LB', 'C': 'GC', 'R': {'X': 'GX', 'Y': 'LY'}, 'D': 'LD'}

    >>> global_settings = {"A": {"B": {"C": {"D": 42}}}}
    >>> local_settings = {"A": {"B": {"C": 13, "D": 73}}}
    >>> recursive_dict_update(global_settings, local_settings)
    {'A': {'B': {'C': 13, 'D': 73}}}
    ```

    Args:
        this (dict): The origin dictionary
        other (dict): Changes that shall be applied to `this`

    Returns:
        The original `this` dictionary with the recursive updates.
    """

    if not isinstance(this, dict) or not isinstance(other, dict):
        raise ValueError("Expected arguments of type dict.")

    for key, value in other.items():
        if isinstance(value, dict) and isinstance(this.get(key), dict):
            this[key] = recursive_dict_update(this[key], other[key])
        else:
            this[key] = other[key]

    return this


def flatten_dict(source_dict: dict) -> dict:
    """
    Flatten the given dictionary concatenating the keys with a colon '`:`'.

    Args:
        source_dict: the original dictionary that will be flattened

    Returns:
        A new flattened dictionary.

    Example:
        ```python
        >>> d = {"A": 1, "B": {"E": {"F": 2}}, "C": {"D": 3}}
        >>> flatten_dict(d)
        {'A': 1, 'B:E:F': 2, 'C:D': 3}

        >>> d = {"A": 'a', "B": {"C": {"D": 'd', "E": 'e'}, "F": 'f'}}
        >>> flatten_dict(d)
        {'A': 'a', 'B:C:D': 'd', 'B:C:E': 'e', 'B:F': 'f'}
        ```
    """

    def expand(key, value):
        if isinstance(value, dict):
            return [(key + ":" + k, v) for k, v in flatten_dict(value).items()]
        else:
            return [(key, value)]

    items = [item for k, v in source_dict.items() for item in expand(k, v)]

    return dict(items)


def get_system_stats() -> dict:
    """
    Gather system information about the CPUs and memory usage and return a dictionary with the
    following information:

    * cpu_load: load average over a period of 1, 5,and 15 minutes given in in percentage
      (i.e. related to the number of CPU cores that are installed on your system) [percentage]
    * cpu_count: physical and logical CPU count, i.e. the number of CPU cores (incl. hyper-threads)
    * total_ram: total physical ram available [bytes]
    * avail_ram:  the memory that can be given instantly to processes without the system going
      into swap. This is calculated by summing different memory values depending on the platform
      [bytes]
    * boot_time: the system boot time expressed in seconds since the epoch [s]
    * since: boot time of the system, aka Up time [str]

    Returns:
        a dictionary with CPU and memory statistics.
    """
    statistics = {}

    # Get Physical and Logical CPU Count

    physical_and_logical_cpu_count = psutil.cpu_count()
    statistics["cpu_count"] = physical_and_logical_cpu_count

    # Load average
    # This is the average system load calculated over a given period of time of 1, 5 and 15 minutes.
    #
    # The numbers returned by psutil.getloadavg() only make sense if
    # related to the number of CPU cores installed on the system.
    #
    # Here we are converting the load average into percentage.
    # The higher the percentage the higher the load.

    cpu_load = [x / physical_and_logical_cpu_count * 100 for x in psutil.getloadavg()]
    statistics["cpu_load"] = cpu_load

    # Memory usage

    vmem = psutil.virtual_memory()

    statistics["total_ram"] = vmem.total
    statistics["avail_ram"] = vmem.available

    # boot_time = seconds since the epoch timezone
    # the Unix epoch is 00:00:00 UTC on 1 January 1970.

    boot_time = psutil.boot_time()
    statistics["boot_time"] = boot_time
    statistics["since"] = datetime.datetime.fromtimestamp(boot_time, tz=datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    return statistics


def get_system_name() -> str:
    """Returns the name of the system in lower case.

    Returns:
        name: 'linux', 'darwin', 'windows', ...
    """
    return platform.system().lower()


def get_os_name() -> str:
    """Returns the name of the OS in lower case.

    If no name could be determined, 'unknown' is returned.

    Returns:
        os: 'macos', 'centos'
    """
    sys_name = get_system_name()
    if sys_name == "darwin":
        return "macos"
    if sys_name == "linux":
        return distro.id().lower()
    if sys_name == "windows":
        return "windows"
    return "unknown"


def get_os_version() -> str:
    """Return the version of the OS.

    If no version could be determined, 'unknown' is returned.

    Returns:
        version: as '10.15' or '8.0' or 'unknown'
    """

    # Don't use `distro.version()` to get the macOS version. That function will return the version
    # of the Darwin kernel.

    os_name = get_os_name()
    sys_name = get_system_name()
    if os_name == "unknown":
        return "unknown"
    if os_name == "macos":
        version, _, _ = platform.mac_ver()
        return ".".join(version.split(".")[:2])
    if sys_name == "linux":
        return distro.version()

    # FIXME: add other OS here for their version number

    return "unknown"


def wait_until(
    condition: Callable, *args: list, interval: float = 0.1, timeout: float = 1.0, verbose: bool = False, **kwargs: dict
) -> bool:
    """
    Sleep until the given condition is fulfilled. The arguments are passed into the condition
    callable which is called in a while loop until the condition is met or the timeout is reached.

    Note that the condition can be a function, method or callable class object.
    An example of the latter is:

    ```python
    class SleepUntilCount:
        def __init__(self, end):
            self._end = end
            self._count = 0

        def __call__(self, *args, **kwargs):
            self._count += 1
            if self._count >= self._end:
                return True
            else:
                return False
    ```

    Args:
        condition: a callable that returns True when the condition is met, False otherwise
        interval: the sleep interval between condition checks [s, default=0.1]
        timeout: the period after which the function returns, even when the condition is
            not met [s, default=1]
        verbose: log debugging messages if True
        *args: any arguments that will be passed into the condition function
        **kwargs: any keyword arguments that will be passed into the condition function

    Returns:
        True when function timed out, False otherwise.
    """

    if inspect.isfunction(condition) or inspect.ismethod(condition):
        func_name = condition.__name__
    else:
        func_name = condition.__class__.__name__

    caller = get_caller_info(level=2)

    start = time.time()

    while not condition(*args, **kwargs):
        if time.time() - start > timeout:
            logger.warning(
                f"Timeout after {timeout} sec, from {caller.filename} at {caller.lineno}, {func_name}{args} not met."
            )
            return True
        time.sleep(interval)

    if verbose:
        logger.debug(f"wait_until finished successfully, {func_name}{args}{kwargs} is met.")

    return False


def waiting_for(
    condition: Callable, *args: list, interval: float = 0.1, timeout: float = 1.0, verbose: bool = False, **kwargs: dict
) -> float:
    """
    Sleep until the given condition is fulfilled. The arguments are passed into the condition
    callable which is called in a while loop until the condition is met or the timeout is reached.

    Note that the condition can be a function, method or callable class object.
    An example of the latter is:

    ```python
    class SleepUntilCount:
        def __init__(self, end):
            self._end = end
            self._count = 0

        def __call__(self, *args, **kwargs):
            self._count += 1
            if self._count >= self._end:
                return True
            else:
                return False
    ```

    Args:
        condition: a callable that returns True when the condition is met, False otherwise
        interval: the sleep interval between condition checks [s, default=0.1]
        timeout: the period after which the function returns, even when the condition is
            not met [s, default=1]
        verbose: log debugging messages if True
        *args: any arguments that will be passed into the condition function
        **kwargs: any keyword arguments that will be passed into the condition function

    Returns:
        The duration until the condition was met.

    Raises:
        TimeoutError: when the condition was not fulfilled within the timeout period.
    """

    if inspect.isfunction(condition) or inspect.ismethod(condition):
        func_name = condition.__name__
    else:
        func_name = condition.__class__.__name__

    caller = get_caller_info(level=2)

    start = time.time()

    while not condition(*args, **kwargs):
        if time.time() - start > timeout:
            raise TimeoutError(
                f"Timeout after {timeout} sec, from {caller.filename} at {caller.lineno}, {func_name}{args} not met."
            )
        time.sleep(interval)

    duration = time.time() - start

    if verbose:
        logger.debug(f"waiting_for finished successfully after {duration:.3f}s, {func_name}{args}{kwargs} is met.")

    return duration


def has_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0):
    """Returns True if we have internet connection.

    Args:
        host: hostname or IP address [default: 8.8.8.8 (google-public-dns-a.google.com)]
        port: 53 [service: tcp]
        timeout: the time to block before failing on a connection

    Note:
        This might give the following error codes:

        * [Errno 51] Network is unreachable
        * [Errno 61] Connection refused (because the port is blocked?)
        * timed out

    Source: https://stackoverflow.com/a/33117579
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        return True
    except socket.error as ex:
        logging.info(f"No Internet: Unable to open socket to {host}:{port} [{ex}]")
        return False
    finally:
        if s is not None:
            s.close()


def do_every(
    period: float,
    func: Callable,
    *args: tuple[int, ...],
    count: int = None,
    setup_func: Callable = None,
    teardown_func: Callable = None,
    stop_event: threading.Event = None,
) -> None:
    """
    This method executes a function periodically, taking into account
    that the function that is executed will take time also and using a
    simple `sleep()` will cause a drift. This method will not drift.

    You can use this function in combination with the threading module
    to execute the function in the background, but be careful as the
    function `func` might not be thread safe.

    ```
    timer_thread = threading.Thread(target=do_every, args=(10, func))
    timer_thread.daemon = True
    timer_thread.start()
    ```

    The `setup_func` and `teardown` functions will be called before and after
    the loop that repeats the `func` function. This can be used e.g. for setting
    up and closing sockets.

    Apart from the `count`, the loop can also be stopped by passing a threading
    event and setting the `stop_event` when you want to terminate the thread.

    ```
    self._stop_event = threading.Event()

    timer_thread = threading.Thread(
        target=do_every,
        args=(interval, send_heartbeat),
        kwargs={
            'stop_event': self._stop_event,
            'setup_func': self._connect_hb_socket,
            'teardown_func': self._disconnect_hb_socket
        }
    )
    timer_thread.daemon = True
    timer_thread.start()

    ...

    self._stop_event.set()
    ```

    Args:
        period: a time interval between successive executions [seconds]
        func: the function to be executed
        *args: optional arguments to be passed to the function
        count: if you do not need an endless loop, provide the number of
            iterations, if count=0 the function will not be executed.
        setup_func: a function that will be called before going into the loop
        teardown_func: a function that will be called when the loop ended
        stop_event: use a threading event to stop the loop
    """

    # Code from SO:https://stackoverflow.com/a/28034554/4609203
    # The max in the yield line serves to protect sleep from negative numbers in case the
    # function being called takes longer than the period specified. In that case it would
    # execute immediately and make up the lost time in the timing of the next execution.

    def g_tick():
        next_time = time.time()
        while True:
            next_time += period
            yield max(next_time - time.time(), 0)

    g = g_tick()
    iteration = 0

    if stop_event is None:
        stop_event = threading.Event()

    if setup_func:
        setup_func()

    while not stop_event.is_set():
        if count is not None and iteration >= count:
            break
        # Wait for the timeout or until the stop_event is set
        # The wait functions returns True only when the event is set and returns False on a timeout
        if stop_event.wait(timeout=next(g)):
            break
        func(*args)
        iteration += 1

    if teardown_func:
        teardown_func()


@contextlib.contextmanager
def chdir(dirname=None):
    """
    Context manager to temporarily change directory.

    Args:
        dirname (str or Path): temporary folder name to switch to within the context

    Example:
        ```python
        with chdir('/tmp'):
            ...  # do stuff in this writable /tmp folder
        ```
    """
    current_dir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(current_dir)


@contextlib.contextmanager
def env_var(**kwargs: dict[str, str]):
    """
    Context manager to run some code that need alternate settings for environment variables.

    Args:
        **kwargs: dictionary with environment variables that are needed

    Example:
        ```python
        with env_var(PLATO_DATA_STORAGE_LOCATION="/Users/rik/data"):
           # do stuff that needs these alternate setting
           ...
        ```
    """
    saved_env = {}

    for k, v in kwargs.items():
        saved_env[k] = os.environ.get(k)
        if v is None:
            if k in os.environ:
                del os.environ[k]
        else:
            os.environ[k] = v

    yield

    for k, v in saved_env.items():
        if v is None:
            if k in os.environ:
                del os.environ[k]
        else:
            os.environ[k] = v


def filter_by_attr(elements: Iterable, **attrs: dict[str, Any]) -> List:
    """
    A helper that returns the elements from the iterable that meet all the traits passed in `attrs`.

    The attributes are compared to their value with the `operator.eq` function. However,
    when the given value for an attribute is a tuple, the first element in the tuple is
    considered a comparison function and the second value the actual value. The attribute
    is then compared to the value using this function.

    ```python
    result = filter_by_attr(setups, camera__model="EM", site_id=(is_in, ("CSL", "INTA")))
    ```
    The function `is_in` is defined as follows:
    ```python
    def is_in(a, b):
        return a in b
    ```
    but you can of course also use a lambda function: `lambda a, b: a in b`.

    One function is treated special, it is the built-in function `hasattr`. Using this function,
    the value can be `True` or `False`. Use this to return all elements in the iterable
    that have the attribute, or not. The following example returns all Setups where the
    `gse.ogse.fwc_factor` is not defined:
    ```python
    result = filter_by_attr(setups, camera__model="EM", gse__ogse__fwc_factor=(hasattr, False)))
    ```

    When multiple attributes are specified, they are checked using logical AND, not logical OR.
    Meaning they have to meet every attribute passed in and not one of them.

    To have a nested attribute search (i.e. search by `gse.hexapod.ID`) then
    pass in `gse__hexapod__ID` as the keyword argument.

    If nothing is found that matches the attributes passed, then an empty list is returned.

    When an attribute is not part of the iterated object, that attribute is silently ignored.

    Args:
        elements: An iterable to search through.
        attrs: Keyword arguments that denote attributes to search with.
    """

    # This code is based on and originates from the get(iterable, **attr) function in the
    # discord/utils.py package (https://github.com/Rapptz/discord.py). After my own version,
    # Ruud van der Ham, improved the code drastically to the version it is now.

    def check(attr_, func, value_, el):
        try:
            a = operator.attrgetter(attr_)(el)
            return value_ if func is hasattr else func(a, value_)
        except AttributeError:
            return not value_ if func is hasattr else False

    attr_func_values = []
    for attr, value in attrs.items():
        if not (isinstance(value, (tuple, list)) and len(value) == 2 and callable(value[0])):
            value = (operator.eq, value)
        attr_func_values.append((attr.replace("__", "."), *value))

    return [el for el in elements if all(check(attr, func, value, el) for attr, func, value in attr_func_values)]


def replace_environment_variable(input_string: str):
    """
    Returns the `input_string` with all occurrences of ENV['var'].

    ```python
    >>> replace_environment_variable("ENV['HOME']/data/CSL")
    '/Users/rik/data/CSL'
    ```

    Args:
        input_string (str): the string to replace
    Returns:
        The input string with the ENV['var'] replaced, or None when the environment variable
        doesn't exists.
    """

    match = re.search(r"(.*)ENV\[['\"](\w+)['\"]\](.*)", input_string)
    if not match:
        return input_string
    pre_match = match.group(1)
    var = match.group(2)
    post_match = match.group(3)

    result = os.getenv(var, None)

    return pre_match + result + post_match if result else None


def read_last_line(filename: str | Path, max_line_length=5000):
    """Returns the last line of a (text) file.

    The argument `max_line_length` should be at least the length of the last line in the file,
    because this value is used to backtrack from the end of the file as an optimization.

    Args:
        filename (Path | str): the filename as a string or Path
        max_line_length (int): the maximum length of the lines in the file
    Returns:
        The last line in the file (whitespace stripped from the right). An empty string is returned
        when the file is empty, `None` is returned when the file doesn't exist.
    """
    filename = Path(filename)

    if not filename.exists():
        return None

    with filename.open("rb") as file:
        file.seek(0, 2)  # 2 is relative to end of file
        size = file.tell()
        if size:
            file.seek(max(0, size - max_line_length))
            return file.readlines()[-1].decode("utf-8").rstrip("\n")
        else:
            return ""


def read_last_lines(filename: str | Path, num_lines: int) -> List[str]:
    """
    Return the last lines of a text file.

    Args:
        filename: Filename.
        num_lines: Number of lines at the back of the file that should be read and returned.

    Returns:
        Last lines of a text file as a list of strings. An empty list is returned
            when the file doesn't exist.

    Raises:
        AssertionError: when the requested num_lines is zero (0) or a negative number.
    """

    # See: https://www.geeksforgeeks.org/python-reading-last-n-lines-of-a-file/
    # (Method 3: Through exponential search)

    filename = Path(filename)

    sanity_check(num_lines >= 0, "the number of lines to read shall be a positive number or zero.")

    if not filename.exists():
        return []

    # Declaring variable to implement exponential search

    pos = num_lines + 1

    # List to store last N lines

    lines = []

    with open(filename) as f:
        size = f.seek(0, SEEK_END)
        while len(lines) <= num_lines:
            try:
                f.seek(size - pos, SEEK_SET)
            # ValueError: e.g. negative seek position
            except (IOError, ValueError):
                f.seek(0)
                break

            finally:
                lines = list(f)
                lines = [x.rstrip() for x in lines]

            # Increasing value of variable exponentially

            pos *= 2

    return lines[-num_lines:]


def is_namespace(module: str | ModuleType) -> bool:
    """
    Checks if a module represents a namespace package.

    Args:
        module: The module to be checked.

    Returns:
        True if the argument is a namespace package, False otherwise.

    Note:
        A namespace package is a special kind of package that spans multiple
        directories or locations, but doesn't contain an `__init__.py` file
        in any of its directories.

        Technically, a namespace package is defined as a module that has a
        `__path__` attribute and no `__file__` attribute.

        A namespace package allows for package portions to be distributed
        independently.

    """

    if isinstance(module, str):
        try:
            module = importlib.import_module(module)
        except (TypeError, ModuleNotFoundError):
            return False

    if hasattr(module, "__path__") and getattr(module, "__file__", None) is None:
        return True
    else:
        return False


def is_module(module: str | ModuleType) -> bool:
    """
    Returns True if the argument is a module or represents a module, False otherwise.

    Args:
        module: a module or module name.

    Returns:
        True if the argument is a module, False otherwise.
    """
    if isinstance(module, ModuleType):
        return True
    elif isinstance(module, str):
        try:
            module = importlib.import_module(module)
        except (TypeError, ModuleNotFoundError):
            return False
        else:
            return True
    else:
        return False


def get_package_description(package_name) -> str:
    """
    Returns the description of the package as specified in the projects metadata Summary.

    Example:
        ```python
        >>> get_package_description('cgse-common')
        'Software framework to support hardware testing'
        ```
    """
    try:
        # Get the metadata for the package
        metadata = importlib.metadata.metadata(package_name)
        # Extract the description
        description = metadata.get("Summary", "Description not found")
        return description
    except importlib.metadata.PackageNotFoundError:
        return "Package not found"


def get_package_location(module: str) -> List[Path]:
    """
    Retrieves the file system locations associated with a Python package.

    This function takes a module, module name, or fully qualified module path,
    and returns a list of Path objects representing the file system locations
    associated with the package. If the module is a namespace package, it returns
    the paths of all namespaces; otherwise, it returns the location of the module.

    Args:
        module (Union[FunctionType, ModuleType, str]): The module or module name to
            retrieve locations for.

    Returns:
        List[Path]: A list of Path objects representing the file system locations.

    Note:
        If the module is not found or is not a valid module, an empty list is returned.

    """

    if isinstance(module, FunctionType):
        module_name = module.__module__
    elif isinstance(module, ModuleType):
        module_name = module.__name__
    elif isinstance(module, str):
        module_name = module
        try:
            module = importlib.import_module(module)
        except TypeError:
            warnings.warn(f"The module is not found or is not valid: {module_name}.")
            return []
    else:
        return []

    if is_namespace(module):
        return [Path(location) for location in module.__path__]
    else:
        location = get_module_location(module)
        return [] if location is None else [location]


def get_module_location(arg: Any) -> Path | None:
    """
    Returns the location of the module as a Path object.

    The function can be given a string, which should then be a module name, or a function or module.
    For the latter two, the module name will be determined.

    Args:
        arg: can be one of the following: function, module, string

    Returns:
        The location of the module as a Path object or None when the location can not be determined or
            an invalid argument was provided.

    Example:
        ```python
        >>> get_module_location('egse')
        Path('/path/to/egse')

        >>> get_module_location(egse.system)
        Path('/path/to/egse/system')
        ```

    Note:
        If the module is not found or is not a valid module, None is returned.

    Warning:
        If the module is a namespace, None will be returned. Use the function
            [is_namespace()](system.md#egse.system.is_namespace) to determine if the 'module'
            is a namespace.

    """
    if isinstance(arg, FunctionType):
        # print(f"func: {arg = }, {arg.__module__ = }")
        module_name = arg.__module__
    elif isinstance(arg, ModuleType):
        # print(f"mod: {arg = }, {arg.__file__ = }")
        module_name = arg.__name__
    elif isinstance(arg, str):
        # print(f"str: {arg = }")
        module_name = arg
    else:
        return None

    # print(f"{module_name = }")

    try:
        module = importlib.import_module(module_name)
    except TypeError:
        return None

    if is_namespace(module):
        # print(f"{module = }")
        return None

    location = Path(module.__file__)

    if location.is_dir():
        return location.resolve()
    elif location.is_file():
        return location.parent.resolve()
    else:
        # print(f"Unknown {location = }")
        return None


def get_full_classname(obj: object) -> str:
    """
    Returns the fully qualified class name for the given object.

    Args:
        obj (object): The object for which to retrieve the fully qualified class name.

    Returns:
        str: The fully qualified class name, including the module.

    Example:
        ```python
        >>> get_full_classname("example")
        'builtins.str'

        >>> get_full_classname(42)
        'builtins.int'
        ```

    Note:
        The function considers various scenarios, such as objects being classes,
        built-ins, or literals like int, float, or complex numbers.

    """

    if type(obj) is type or obj.__class__.__module__ == str.__module__:
        try:
            module = obj.__module__
            name = obj.__qualname__
        except (TypeError, AttributeError):
            module = type(obj).__module__
            name = obj.__class__.__qualname__
    else:
        module = obj.__class__.__module__
        name = obj.__class__.__qualname__

    return module + "." + name


def find_class(class_name: str) -> Type:
    """Find and returns a class based on the fully qualified name.

    A class name can be preceded with the string `class//`. This is used in YAML
    files where the class is then instantiated on load by the [Setup](setup.md#egse.setup.Setup).

    Args:
        class_name (str): a fully qualified name for the class

    Returns:
        The class object corresponding to the fully qualified class name.

    Raises:
        AttributeError: when the class is not found in the module.
        ValueError: when the class_name can not be parsed.
        ModuleNotFoundError: if the module could not be found.
    """
    if class_name.startswith("class//"):
        class_name = class_name[7:]

    module_name, class_name = class_name.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def type_name(var):
    """Returns the name of the type of var."""
    return type(var).__name__


def check_argument_type(obj: object, name: str, target_class: Union[type, Tuple[type]], allow_none: bool = False):
    """
    Check that the given object is of a specific (sub)type of the given target_class.
    The `target_class` can be a tuple of types.

    Args:
        obj: any object
        name: the name of the object
        target_class: the required type of the object (can be a tuple of types)
        allow_none: True if the object can be None

    Raises:
        TypeError: when not of the required type or None when not allowed.
    """
    if obj is None and allow_none:
        return
    if obj is None:
        raise TypeError(f"The argument '{name}' cannot be None.")
    if not isinstance(obj, target_class):
        raise TypeError(f"The argument '{name}' must be of type {target_class}, but is {type(obj)}")


def check_str_for_slash(arg: str):
    """Check if there is a slash in the given string, and raise a ValueError if so.

    Raises:
        ValueError: if the string contains a slash '`/`'.
    """

    if "/" in arg:
        ValueError(f"The given argument can not contain slashes, {arg=}.")


def check_is_a_string(var: Any, allow_none=False):
    """
    Checks if the given variable is a string and raises a TypeError if the check fails.

    Args:
        var: The variable to be checked.
        allow_none (bool, optional): If True, allows the variable to be None without raising an error.
            Defaults to False.

    Raises:
        TypeError: If the variable is not a string or is None (when allow_none is False).

    Example:
        ```python
        check_is_a_string("example")
        ```

    Note:
        This function is designed to validate that the input variable is a string.
        If `allow_none` is set to True, it allows the variable to be None without raising an error.

    """

    if var is None and allow_none:
        return
    if var is None and not allow_none:
        raise TypeError("The given variable cannot be None.")
    if not isinstance(var, str):
        raise TypeError(f"var must be a string, however {type(var)=}")


def sanity_check(flag: bool, msg: str):
    """
    Checks a boolean flag and raises an AssertionError with the provided message if the check fails.

    This function serves as a replacement for the 'assert' statement in production code.
    Using this ensures that your checks are not removed during optimizations.

    Args:
        flag (bool): The boolean flag to be checked.
        msg (str): The message to be included in the AssertionError if the check fails.

    Raises:
        AssertionError: If the flag is False.

    Example:
        ```python
        >>> sanity_check(x > 0, "x must be greater than 0")
        ```

    Note:
        This function is designed for production code to perform runtime checks
        that won't be removed during optimizations.

    """

    if not flag:
        raise AssertionError(msg)


class NotSpecified:
    """
    Class for NOT_SPECIFIED constant.
    Is used so that a parameter can have a default value other than None.

    Evaluate to False when converted to boolean.
    """

    def __nonzero__(self):
        """Always returns False. Called when to converting to bool in Python 2."""
        return False

    def __bool__(self):
        """Always returns False. Called when to converting to bool in Python 3."""
        return False


NOT_SPECIFIED = NotSpecified()
"""The constant that defines a not-specified value. Intended use is as a sentinel object."""

# Do not try to catch SIGKILL (9) that will just terminate your script without any warning

SIGNAL_NAME = {
    1: "SIGHUP",
    2: "SIGINT",
    3: "SIGQUIT",
    6: "SIGABRT",
    15: "SIGTERM",
    30: "SIGUSR1",
    31: "SIGUSR2",
}
"""The signals that can be caught with the SignalCatcher."""


class SignalCatcher:
    """
    This class registers handler to signals. When a signal is caught, the handler is
    executed and a flag for termination or user action is set to True. Check for this
    flag in your application loop.

    - Termination signals: 1=HUP, 2=INT, 3=QUIT, 6=ABORT, 15=TERM
    - User signals: 30=USR1, 31=USR2
    """

    def __init__(self):
        self.term_signal_received = False
        self.user_signal_received = False
        self.term_signals = [1, 2, 3, 6, 15]
        self.user_signals = [30, 31]
        for signal_number in self.term_signals:
            signal.signal(signal_number, self.handler)
        for signal_number in self.user_signals:
            signal.signal(signal_number, self.handler)

        self._signal_number = None
        self._signal_name = None

    @property
    def signal_number(self):
        """The value of the signal that was caught."""
        return self._signal_number

    @property
    def signal_name(self):
        """The name of the signal that was caught."""
        return self._signal_name

    def handler(self, signal_number, frame):
        """Handle the known signals by setting the appropriate flag."""
        logger.warning(f"Received signal {SIGNAL_NAME[signal_number]} [{signal_number}].")
        if signal_number in self.term_signals:
            self.term_signal_received = True
        if signal_number in self.user_signals:
            self.user_signal_received = True
        self._signal_number = signal_number
        self._signal_name = SIGNAL_NAME[signal_number]

    def clear(self, term: bool = False):
        """
        Call this method to clear the user signal after handling.
        Termination signals are not cleared by default since the application is supposed to terminate.
        Pass in a `term=True` to also clear the TERM signals, e.g. when you want to ignore some
        TERM signals.
        """
        self.user_signal_received = False
        if term:
            self.term_signal_received = False
        self._signal_number = None
        self._signal_name = None


def is_in(a, b):
    """Returns result of `a in b`."""
    return a in b


def is_not_in(a, b):
    """Returns result of `a not in b`."""
    return a not in b


def is_in_ipython():
    """Returns True if the code is running in IPython."""
    return hasattr(builtins, "__IPYTHON__")


_function_timing = {}


def execution_time(func):
    """
    A decorator to save the execution time of the function. Use this decorator
    if you want —by default and always— have an idea of the average execution time
    of the given function.

    Use this in conjunction with the [get_average_execution_time()](system.md#egse.system.get_average_execution_time)
    function to retrieve the average execution time for the given function.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return save_average_execution_time(func, *args, **kwargs)

    return wrapper


def save_average_execution_time(func: Callable, *args, **kwargs):
    """
    Executes the function 'func' with the given arguments and saves the execution time. All positional
    arguments (in args) and keyword arguments (in kwargs) are passed into the function. The execution
    time is saved in a deque of maximum 100 elements. When more times are added, the oldest times are
    discarded. This function is used in conjunction with the
    [get_average_execution_time()](system.md#egse.system.get_average_execution_time) function.
    """

    with Timer(log_level=logging.NOTSET) as timer:
        response = func(*args, **kwargs)

    if func not in _function_timing:
        _function_timing[func] = collections.deque(maxlen=100)

    _function_timing[func].append(timer.get_elapsed())

    return response


def get_average_execution_time(func: Callable) -> float:
    """
    Returns the average execution time of the given function. The function 'func' shall be previously executed using
    the [save_average_execution_time()](system.md#egse.system.save_average_execution_time) function which remembers the
    last
    100 execution times of the function.
    You can also decorate your function with [@execution_time](system.md#egse.system.execution_time) to permanently
    monitor it.
    The average time is a moving average over the last 100 times. If the function was never called before, 0.0 is
    returned.

    This function can be used when setting a frequency to execute a certain function. When the average execution time
    of the function is longer than the execution interval, the frequency shall be decreased or the process will get
    stalled.
    """

    # If the function was previously wrapped with the `@execution_time` wrapper, we need to get
    # to the original function object because that's the one that is saved.

    with contextlib.suppress(AttributeError):
        func = func.__wrapped__

    try:
        d = _function_timing[func]
        return sum(d) / len(d)
    except KeyError:
        return 0.0


def get_average_execution_times() -> dict:
    """
    Returns a dictionary with `key = <function name>` and  `value = <average execution time>`, for all function that
    have been monitored in this process.
    """
    return {func.__name__: get_average_execution_time(func) for func in _function_timing}


def clear_average_execution_times():
    """Clear out all function timing for this process."""
    _function_timing.clear()


def get_system_architecture() -> str:
    """
    Returns the machine type. This is a string describing the processor architecture,
    like 'i386' or 'arm64', but the exact string is not defined. An empty string can be
    returned when the type cannot be determined.
    """
    return platform.machine()


def time_in_ms() -> int:
    """
    Returns the current time in milliseconds since the Epoch.

    Note:
        if you are looking for a high performance timer, you should really be using `perf_counter()`
          instead of this function.
    """
    return int(round(time.time() * 1000))


class Sentinel:
    """
    This Sentinel can be used as an alternative to None or other meaningful values in e.g. a function argument.

    Usually, a sensible default would be to use None, but if None is a valid input parameter, you can use a Sentinel
    object and check in the function if the argument value is a Sentinel object.

    Example:
        ```python
        def get_info(server_socket, timeout: int = Sentinel()):
            if isinstance(timeout, Sentinel):
               raise ValueError("You should enter a valid timeout or None")
        ```
    """

    def __repr__(self):
        return "A default Sentinel object."


def touch(path: Path | str):
    """
    Unix-like 'touch', i.e. create a file if it doesn't exist and set the modification time to the current time.

    Args:
        path: full path to the file, can start with `~` which is automatically expanded.
    """

    path = Path(path).expanduser().resolve()
    basedir = path.parent
    if not basedir.exists():
        basedir.mkdir(parents=True, exist_ok=True)

    with path.open("a"):
        os.utime(path)


def capture_rich_output(obj: Any, width: int = 120) -> str:
    """
    Capture the output of a Rich console print of the given object. If the object is a known Rich renderable or if
    the object implements the `__rich__()` method, the output string will contain escape sequences to format the
    output when printed to a terminal.

    This method is usually used to represent Rich output in a log file, e.g. to print a table in the log file.

    Args:
        obj: any object
        width: the console width to use, None for full width

    Returns:
        The output of the capture, a string that possibly contains escape sequences as a result of rendering rich text.
    """
    console = Console(width=width)

    with console.capture() as capture:
        console.print(obj)

    captured_output = capture.get()

    return captured_output


def log_rich_output(logger_: logging.Logger, level: int, obj: Any):
    console = Console(width=None)

    with console.capture() as capture:
        console.print()  # start on a fresh line when logging
        console.print(obj)

    captured_output = capture.get()

    logger_.log(level, captured_output)


def is_package_installed(package_name):
    """Check if a package is installed."""
    return importlib.util.find_spec(package_name) is not None


def get_logging_level(level: str | int):
    """
    Convert a logging level to its integer representation.

    This function normalizes various logging level inputs (string names,
    integer values, or custom level strings) into their corresponding
    integer logging levels.

    Args:
        level (str | int): The logging level to convert. Can be:
            - Standard logging level name (e.g., 'DEBUG', 'INFO', 'WARNING')
            - Integer logging level (e.g., 10, 20, 30)
            - Custom level string (e.g., 'Level 25')

    Returns:
        int: The integer representation of the logging level.
            - Standard levels: DEBUG=10, INFO=20, WARNING=30, ERROR=40, CRITICAL=50
            - Custom levels: Extracted integer value or dynamically resolved value
    """

    log_level = logging.getLevelName(level)

    if isinstance(log_level, str):
        match = re.search(r"\d+", log_level)
        if match:
            int_level = level = int(match.group())
        else:
            int_level = getattr(logging, log_level)
    else:
        int_level = log_level

    return int_level


def camel_to_kebab(camel_str: str) -> str:
    """Convert a string in CamelCase to kebab-case."""

    # Handle sequences of uppercase letters followed by lowercase
    s1 = re.sub("([A-Z]+)([A-Z][a-z])", r"\1-\2", camel_str)

    # Handle lowercase/digit followed by uppercase
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1-\2", s1)
    return s2.lower()


def camel_to_snake(camel_str: str) -> str:
    """Convert a string in CamelCase to snake_case."""

    # Handle sequences of uppercase letters followed by lowercase
    s1 = re.sub("([A-Z]+)([A-Z][a-z])", r"\1_\2", camel_str)

    # Handle lowercase/digit followed by uppercase
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower()


def kebab_to_title(kebab_str: str) -> str:
    """Convert kebab-case to Title Case (each word capitalized)"""
    return kebab_str.replace("-", " ").title()


def snake_to_title(snake_str: str) -> str:
    """Convert snake_case to Title Case (each word capitalized)"""
    return snake_str.replace("_", " ").title()


ignore_m_warning("egse.system")

if __name__ == "__main__":
    print(f"Host IP: {get_host_ip()}")
    print(f"System name: {get_system_name()}")
    print(f"OS name: {get_os_name()}")
    print(f"OS version: {get_os_version()}")
    print(f"Architecture: {get_system_architecture()}")
    print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print("Running in IPython") if is_in_ipython() else None
