"""
A collection of useful decorator functions.
"""

import cProfile
import functools
import logging
import pstats
import time
import types
import warnings
from typing import Callable
from typing import List
from typing import Optional

import rich

from egse.settings import Settings
from egse.system import get_caller_info
from egse.log import logger


def static_vars(**kwargs):
    """
    Define static variables in a function.

    The static variable can be accessed with <function name>.<variable name> inside the function body.

    Example:
        ```python
        @static_vars(count=0)
        def special_count():
            return special_count.count += 2
        ```

    """

    def decorator(func):
        for kw in kwargs:
            setattr(func, kw, kwargs[kw])
        return func

    return decorator


def implements_protocol(protocol):
    """
    Decorator to verify and document protocol compliance at class definition time.

    Usage:
        @implements_protocol(AsyncRegistryBackend)
        class MyBackend:
            ...
    """

    def decorator(cls):
        # Add protocol documentation
        if cls.__doc__:
            cls.__doc__ += f"\n\nThis class implements the {protocol.__name__} protocol."
        else:
            cls.__doc__ = f"This class implements the {protocol.__name__} protocol."

        # Store the protocol for reference
        cls.__implements_protocol__ = protocol

        # Add runtime verification method
        def _verify_protocol_compliance(self):
            if not isinstance(self, protocol):
                raise TypeError(f"{self.__class__.__name__} does not correctly implement {protocol.__name__}")
            return True

        cls.verify_protocol_compliance = _verify_protocol_compliance

        # Return the modified class
        return cls

    return decorator


def dynamic_interface(func) -> Callable:
    """Adds a static variable `__dynamic_interface` to a method.

    The intended use of this function is as a decorator for functions in an interface class.

    The static variable is currently used by the Proxy class to check if a method
    is meant to be overridden dynamically. The idea behind this is to loosen the contract
    of an abstract base class (ABC) into an interface. For an ABC, the abstract methods
    must be implemented at construction/initialization. This is not possible for the Proxy
    subclasses as they load their commands (i.e. methods) from the control server, and the
    method will be added to the Proxy interface after loading. Nevertheless, we like the
    interface already defined for auto-completion during development or interactive use.

    When a Proxy subclass that implements an interface with methods decorated by
    the `@dynamic_interface` does overwrite one or more of the decorated methods statically,
    these methods will not be dynamically overwritten when loading the interface from the
    control server. A warning will be logged instead.
    """
    setattr(func, "__dynamic_interface", True)
    return func


def query_command(func):
    """Adds a static variable `__query_command` to a method."""

    setattr(func, "__query_command", True)
    return func


def transaction_command(func):
    """Adds a static variable `__transaction_command` to a method."""

    setattr(func, "__transaction_command", True)
    return func


def read_command(func):
    """Adds a static variable `__read_command` to a method."""

    setattr(func, "__read_command", True)
    return func


def write_command(func):
    """Adds a static variable `__write_command` to a method."""

    setattr(func, "__write_command", True)
    return func


def average_time(*, name: str = "average_time", level: int = logging.INFO, precision: int = 6) -> Callable:
    """
    This is a decorator that is intended mainly as a development aid. When you decorate your function with
    `@average_time`, the execution time of your function will be kept and accumulated. At anytime in your code,
    you can request the total execution time and the number of calls:

        @average_time()
        def my_function():
            ...
        total_execution_time, call_count = my_function.report()

    Requesting the report will automatically log the average runtime and the number of calls.
    If you need to reset the execution time and the number of calls during your testing, use:

        my_function.reset()

    Args:
        name: A name for the timer that will be used during reporting, default='average_time'
        level: the required log level, default=logging.INFO
        precision: the precision used to report the average time, default=6

    Returns:
        The decorated function.

    """

    def actual_decorator(func):
        func._run_time = 0.0
        func._call_count = 0

        def _report_average_time():
            if func._call_count:
                average_time = func._run_time / func._call_count
                logger.log(
                    level,
                    f"{name}: "
                    f"average runtime of {func.__name__!r} is {average_time:.{precision}f}s, "
                    f"#calls = {func._call_count}.",
                )
            else:
                logger.log(level, f"{name}: function {func.__name__!r} was never called.")

            return func._run_time, func._call_count

        def _reset():
            func._run_time = 0
            func._call_count = 0

        func.report = _report_average_time
        func.reset = _reset

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            func._run_time += end_time - start_time
            func._call_count += 1
            return result

        return wrapper

    return actual_decorator


def timer(*, name: str = "timer", level: int = logging.INFO, precision: int = 4):
    """
    Print the runtime of the decorated function.

    Args:
        name: a name for the Timer, will be printed in the logging message
        level: the logging level for the time message [default=INFO]
        precision: the number of decimals for the time [default=3 (ms)]
    """

    def actual_decorator(func):
        @functools.wraps(func)
        def wrapper_timer(*args, **kwargs):
            start_time = time.perf_counter()
            value = func(*args, **kwargs)
            end_time = time.perf_counter()
            run_time = end_time - start_time
            logger.log(level, f"{name}: Finished {func.__name__!r} in {run_time:.{precision}f} secs")
            return value

        return wrapper_timer

    return actual_decorator


def async_timer(*, name: str = "timer", level: int = logging.INFO, precision: int = 4):
    """
    Print the runtime of the decorated async function.

    Args:
        name: a name for the Timer, will be printed in the logging message
        level: the logging level for the time message [default=INFO]
        precision: the number of decimals for the time [default=3 (ms)]
    """

    def actual_decorator(func):
        @functools.wraps(func)
        async def wrapper_timer(*args, **kwargs):
            start_time = time.perf_counter()
            value = await func(*args, **kwargs)
            end_time = time.perf_counter()
            run_time = end_time - start_time
            logger.log(level, f"{name}: Finished {func.__name__!r} in {run_time:.{precision}f} secs")
            return value

        return wrapper_timer

    return actual_decorator


def time_it(count: int = 1000, precision: int = 4) -> Callable:
    """Print the runtime of the decorated function.

    This is a simple replacement for the builtin ``timeit`` function. The purpose is to simplify
    calling a function with some parameters.

    The intended way to call this is as a function:

        value = function(args)

        value = time_it(10_000)(function)(args)

    The `time_it` function can be called as a decorator in which case it will always call the
    function `count` times which is probably not what you want.

    Args:
        count (int): the number of executions [default=1000].
        precision (int): the number of significant digits [default=4]

    Returns:
        value: the return value of the last function execution.

    See also:
        the ``Timer`` context manager located in ``egse.system``.

    Usage:
        ```python
        @time_it(count=10000)
        def function(args):
            pass

        time_it(10000)(function)(args)
        ```
    """

    def actual_decorator(func):
        @functools.wraps(func)
        def wrapper_timer(*args, **kwargs):
            value = None
            start_time = time.perf_counter()
            for _ in range(count):
                value = func(*args, **kwargs)
            end_time = time.perf_counter()
            run_time = end_time - start_time
            logging.info(
                f"Finished {func.__name__!r} in {run_time / count:.{precision}f} secs "
                f"(total time: {run_time:.2f}s, count: {count})"
            )
            return value

        return wrapper_timer

    return actual_decorator


def debug(func):
    """Logs the function signature and return value."""

    @functools.wraps(func)
    def wrapper_debug(*args, **kwargs):
        if __debug__:
            args_repr = [repr(a) for a in args]
            kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
            signature = ", ".join(args_repr + kwargs_repr)
            logger.debug(f"Calling {func.__name__}({signature})")
            value = func(*args, **kwargs)
            logger.debug(f"{func.__name__!r} returned {value!r}")
        else:
            value = func(*args, **kwargs)
        return value

    return wrapper_debug


def profile_func(
    output_file: str = None, sort_by: str = "cumulative", lines_to_print: int = None, strip_dirs: bool = False
) -> Callable:
    """A time profiler decorator.

    Args:
        output_file: str or None. Default is None
            Path of the output file. If only name of the file is given, it's
            saved in the current directory.
            If it's None, the name of the decorated function is used.
        sort_by: str or SortKey enum or tuple/list of str/SortKey enum
            Sorting criteria for the Stats object.
            For a list of valid string and SortKey refer to:
            https://docs.python.org/3/library/profile.html#pstats.Stats.sort_stats
        lines_to_print: int or None
            Number of lines to print. Default (None) is for all the lines.
            This is useful in reducing the size of the printout, especially
            that sorting by 'cumulative', the time consuming operations
            are printed toward the top of the file.
        strip_dirs: bool
            Whether to remove the leading path info from file names.
            This is also useful in reducing the size of the printout

    Returns:
        Profile of the decorated function

    Note:
        This code was taken from this gist: [a profile
        decorator](https://gist.github.com/ekhoda/2de44cf60d29ce24ad29758ce8635b78).

        Inspired by and modified the profile decorator of Giampaolo Rodola:
        [profile decorato](http://code.activestate.com/recipes/577817-profile-decorator/).


    """

    def inner(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _output_file = output_file or func.__name__ + ".prof"
            pr = cProfile.Profile()
            pr.enable()
            retval = func(*args, **kwargs)
            pr.disable()
            pr.dump_stats(_output_file)

            with open(_output_file, "w") as f:
                ps = pstats.Stats(pr, stream=f)
                if strip_dirs:
                    ps.strip_dirs()
                if isinstance(sort_by, (tuple, list)):
                    ps.sort_stats(*sort_by)
                else:
                    ps.sort_stats(sort_by)
                ps.print_stats(lines_to_print)
            return retval

        return wrapper

    return inner


def profile(func):
    """
    Prints the function signature and return value to stdout.

    This function checks the `Settings.profiling()` value and only prints out
    profiling information if this returns True.

    Profiling can be activated with `Settings.set_profiling(True)`.
    """
    if not hasattr(profile, "counter"):
        profile.counter = 0

    @functools.wraps(func)
    def wrapper_profile(*args, **kwargs):
        if Settings.profiling():
            profile.counter += 1
            args_repr = [repr(a) for a in args]
            kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
            signature = ", ".join(args_repr + kwargs_repr)
            caller = get_caller_info(level=2)
            prefix = f"PROFILE[{profile.counter}]: "
            rich.print(f"{prefix}Calling {func.__name__}({signature})")
            rich.print(f"{prefix}    from {caller.filename} at {caller.lineno}.")
            value = func(*args, **kwargs)
            rich.print(f"{prefix}{func.__name__!r} returned {value!r}")
            profile.counter -= 1
        else:
            value = func(*args, **kwargs)
        return value

    return wrapper_profile


class Profiler:
    """
    A simple profiler class that provides some useful functions to profile a function.

    - count: count the number of times this function is executed
    - duration: measure the total and average duration of the function [seconds]

    Examples:
          >>> from egse.decorators import Profiler
          >>> @Profiler.count()
          ... def square(x):
          ...     return x**2

          >>> x = [square(x) for x in range(1_000_000)]

          >>> print(f"Function 'square' called {square.get_count()} times.")
          >>> print(square)

          >>> @Profiler.duration()
          ... def square(x):
          ...     time.sleep(0.1)
          ...     return x**2

          >>> x = [square(x) for x in range(100)]

          >>> print(f"Function 'square' takes on average {square.get_average_duration():.6f} seconds.")
          >>> print(square)

    """

    class CountCalls:
        def __init__(self, func):
            self.func = func
            self.count = 0

        def __call__(self, *args, **kwargs):
            self.count += 1
            return self.func(*args, **kwargs)

        def get_count(self):
            return self.count

        def reset(self):
            self.count = 0

        def __str__(self):
            return f"Function '{self.func.__name__}' was called {self.count} times."

        # The __get__ method is here to make the decorator work with instance methods (methods inside a class)
        # as well. It ensures that when the decorated method is called on an instance, the self argument is
        # correctly passed to the method.

        def __get__(self, instance, owner):
            if instance is None:
                return self
            else:
                return types.MethodType(self, instance)

    class Duration:
        def __init__(self, func):
            self.func = func
            self.duration = 0
            self.count = 0

        def __call__(self, *args, **kwargs):
            start = time.perf_counter_ns()
            response = self.func(*args, **kwargs)
            self.count += 1
            self.duration += time.perf_counter_ns() - start
            return response

        def get_count(self):
            return self.count

        def get_duration(self):
            return self.duration / 1_000_000_000

        def get_average_duration(self):
            return self.duration / 1_000_000_000 / self.count if self.count else 0.0

        def reset(self):
            self.duration = 0
            self.count = 0

        def __str__(self):
            return f"Function '{self.func.__name__}' takes on average {self.get_average_duration():.6f} seconds."

        # The __get__ method is here to make the decorator work with instance methods (methods inside a class)
        # as well. It ensures that when the decorated method is called on an instance, the self argument is
        # correctly passed to the method.

        def __get__(self, instance, owner):
            if instance is None:
                return self
            else:
                return types.MethodType(self, instance)

    @classmethod
    def count(cls):
        return cls.CountCalls

    @classmethod
    def duration(cls):
        return cls.Duration


def to_be_implemented(func):
    """Print a warning message that this function/method has to be implemented."""

    @functools.wraps(func)
    def wrapper_tbi(*args, **kwargs):
        logger.warning(f"The function/method {func.__name__} is not yet implemented.")
        return func(*args, **kwargs)

    return wrapper_tbi


# Taken and adapted from https://github.com/QCoDeS/Qcodes


def deprecate(reason: Optional[str] = None, alternative: Optional[str] = None) -> Callable:
    """
    Deprecate a function or method. This will print a warning with the function name and where
    it is called from. If the optional parameters `reason` and `alternative` are given, that
    information will be printed with the warning.

    Examples:

        @deprecate(reason="it doesn't follow PEP8", alternative="set_color()")
        def setColor(self, color):
            self.set_color(color)

    Args:
        reason: provide a short explanation why this function is deprecated. Generates 'because {reason}'
        alternative: provides an alternative function/parameters to be used. Generates 'Use {alternative}
            as an alternative'

    Returns:
        The decorated function.
    """

    def actual_decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def decorated_func(*args, **kwargs):
            caller = get_caller_info(2)
            msg = f'The function "{func.__name__}" used at {caller.filename}:{caller.lineno} is deprecated'
            if reason is not None:
                msg += f", because {reason}"
            if alternative is not None:
                msg += f". Use {alternative} as an alternative"
            msg += "."
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        decorated_func.__doc__ = (
            f"This function is DEPRECATED, because {reason}, use {alternative} as an alternative.\n"
        )
        return decorated_func

    return actual_decorator


def singleton(cls):
    """
    Use class as a singleton.

    from:
        [Decorator library: Signleton](https://wiki.python.org/moin/PythonDecoratorLibrary#Singleton)
    """

    cls.__new_original__ = cls.__new__

    @functools.wraps(cls.__new__)
    def singleton_new(cls, *args, **kw):
        it = cls.__dict__.get("__it__")
        if it is not None:
            return it

        cls.__it__ = it = cls.__new_original__(cls, *args, **kw)
        it.__init_original__(*args, **kw)
        return it

    cls.__new__ = singleton_new
    cls.__init_original__ = cls.__init__
    cls.__init__ = object.__init__

    return cls


def borg(cls):
    """
    Use the Borg pattern to make a class with a shared state between its instances and subclasses.

    from:
        [we don't need no singleton](
        http://code.activestate.com/recipes/66531-singleton-we-dont-need-no-stinkin-singleton-the-bo/)
    """

    cls._shared_state = {}
    orig_init = cls.__init__

    def new_init(self, *args, **kwargs):
        self.__dict__ = cls._shared_state
        orig_init(self, *args, **kwargs)

    cls.__init__ = new_init

    return cls


class classproperty:
    """Defines a read-only class property.

    Examples:

        >>> class Message:
        ...     def __init__(self, msg):
        ...         self._msg = msg
        ...
        ...     @classproperty
        ...     def name(cls):
        ...         return cls.__name__

        >>> msg = Message("a simple doctest")
        >>> assert "Message" == msg.name

    """

    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        return self.func(owner)

    def __set__(self, instance, value):
        raise AttributeError(
            f"Cannot change class property '{self.func.__name__}' for class '{instance.__class__.__name__}'."
        )


class Nothing:
    """Just to get a nice repr for Nothing. It is kind of a Null object..."""

    def __repr__(self):
        return "<Nothing>"


def spy_on_attr_change(obj: object, obj_name: str = None) -> None:
    """
    Tweak an object to show attributes changing. The changes are reported as WARNING log messages
    in the `egse.spy` logger.

    Note this is not a decorator, but a function that changes the class of an object.

    Note that this function is a debugging aid and should not be used in production code!

    Args:
        obj (object): any object that you want to monitor
        obj_name (str): the variable name of the object that was given in the code, if None than
            the class name will be printed.

    Example:
        ```python
        class X:
           pass

        x = X()
        spy_on_attr_change(x, obj_name="x")
        x.a = 5
        ```

    From:
        [Adding a dunder to an object](https://nedbatchelder.com/blog/202206/adding_a_dunder_to_an_object.html)
    """
    logger = logging.getLogger("egse.spy")

    class Wrapper(obj.__class__):
        def __setattr__(self, name, value):
            old = getattr(self, name, Nothing())
            logger.warning(f"Spy: in {obj_name or obj.__class__.__name__} -> {name}: {old!r} -> {value!r}")
            return super().__setattr__(name, value)

    class_name = obj.__class__.__name__
    obj.__class__ = Wrapper
    obj.__class__.__name__ = class_name


def retry_with_exponential_backoff(
    max_attempts: int = 5, initial_wait: float = 1.0, backoff_factor: int = 2, exceptions: List = None
) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.

    This decorator can be applied to a function to handle specified exceptions by
    retrying the function execution. It will make up to 'max_attempts' attempts with a
    waiting period that grows exponentially between each attempt (dependent on the backoff_factor).
    Any exception from the list provided in the `exceptions` argument will be ignored for the
    given `max_attempts`.

    If after all attempts still an exception is raised, it will be passed through the
    calling function, otherwise the functions return value will be returned.

    Args:
        max_attempts: The maximum number of attempts to make.
        initial_wait: The initial waiting time in seconds before retrying after the first failure.
        backoff_factor: The factor by which the wait time increases after each failure.
        exceptions: list of exceptions to ignore, if None all exceptions will be ignored `max_attempts`.

    Returns:
        The response from the executed function.
    """

    exceptions = [Exception] if exceptions is None else exceptions

    def actual_decorator(func):
        @functools.wraps(func)
        def decorate_func(*args, **kwargs):
            attempt = 0
            wait_time = initial_wait
            last_exception = None

            while attempt < max_attempts:
                try:
                    response = func(*args, **kwargs)  # Attempt to call the function
                    logger.info(f"{func.__name__} successfully executed.")
                    return response
                except tuple(exceptions) as exc:
                    last_exception = exc
                    attempt += 1
                    logger.info(
                        f"Retry {attempt}: {func.__name__} will be executing again in {wait_time * backoff_factor}s. "
                        f"Received a {last_exception!r}."
                    )
                    time.sleep(wait_time)  # Wait before retrying
                    wait_time *= backoff_factor  # Increase wait time for the next attempt

            # If the loop completes, all attempts have failed, reraise the last exception

            raise last_exception

        return decorate_func

    return actual_decorator


def retry(times: int = 3, wait: float = 10.0, exceptions: List = None) -> Callable:
    """
    Decorator that retries a function multiple times with a delay between attempts.

    This decorator can be applied to a function to handle specified exceptions by
    retrying the function execution. It will make up to 'times' attempts with a
    waiting period of 'wait' seconds between each attempt. Any exception from the
    list provided in the `exceptions` argument will be ignored for the given `times`.

    If after times attempts still an exception is raised, it will be passed through the
    calling function, otherwise the functions return value will be returned.

    Args:
        times (int, optional): The number of retry attempts. Defaults to 3.
        wait (float, optional): The waiting period between retries in seconds. Defaults to 10.0.
        exceptions (List[Exception] or None, optional): List of exception types to catch and retry.
            Defaults to None, which catches all exceptions.

    Returns:
        Callable: The decorated function.

    Example:
        Apply the retry decorator to a function with specific retry settings:

        ```python
        @retry(times=5, wait=15.0, exceptions=[ConnectionError, TimeoutError])
        def my_function():
            # Function logic here
        ```

    Note:
        The decorator catches specified exceptions and retries the function, logging
        information about each retry attempt.

    """

    exceptions = [Exception] if exceptions is None else exceptions

    def actual_decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def decorated_func(*args, **kwargs):
            previous_exception = None
            for n in range(times):
                try:
                    return func(*args, **kwargs)
                except tuple(exceptions) as exc:
                    previous_exception = exc
                if n < times:
                    logger.info(
                        f"Retry {n + 1}: {func.__name__} will be executing again in {wait}s. "
                        f"Received a {previous_exception!r}."
                    )
                    time.sleep(wait)
            raise previous_exception

        return decorated_func

    return actual_decorator


def execution_count(func):
    """Counts the number of times the function has been executed."""
    func._call_count = 0

    def counts():
        return func._call_count

    def reset():
        func._call_count = 0

    func.counts = counts
    func.reset = reset

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func._call_count += 1
        value = func(*args, **kwargs)
        return value

    return wrapper
