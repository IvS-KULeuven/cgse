"""
A collection of useful decorator functions.
"""
import cProfile
import functools
import logging
import pstats
import time
import warnings
from typing import Callable
from typing import Optional

import rich

from egse.settings import Settings
from egse.system import get_caller_info

_LOGGER = logging.getLogger(__name__)


def static_vars(**kwargs):
    """Define static variables in a function."""
    def decorator(func):
        for kw in kwargs:
            setattr(func, kw, kwargs[kw])
        return func
    return decorator


def dynamic_interface(func):
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
    """Adds a static variable `__query_command` to a method.
    """

    setattr(func, "__query_command", True)
    return func


def transaction_command(func):
    """Adds a static variable `__transaction_command` to a method.
    """

    setattr(func, "__transaction_command", True)
    return func


def read_command(func):
    """Adds a static variable `__read_command` to a method.
    """

    setattr(func, "__read_command", True)
    return func


def write_command(func):
    """Adds a static variable `__write_command` to a method.
    """

    setattr(func, "__write_command", True)
    return func


def timer(*, level: int = logging.INFO, precision: int = 4):
    """
    Print the runtime of the decorated function.

    Args:
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
            _LOGGER.log(level, f"Finished {func.__name__!r} in {run_time:.{precision}f} secs")
            return value

        return wrapper_timer
    return actual_decorator


def time_it(count: int = 1000):
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

    Returns:
        value: the return value of the last function execution.

    See also:
        the ``Timer`` context manager located in ``egse.system``.

    Usage:
        @time_it(count=10000)
        def function(args):
            pass

        time_it(10000)(function)(args)
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
            logging.info(f"Finished {func.__name__!r} in {run_time/count:.4f} secs (total time: {run_time:.2f}s, "
                         f"count: {count})")
            return value

        return wrapper_timer
    return actual_decorator


def debug(func):
    """Print the function signature and return value"""

    @functools.wraps(func)
    def wrapper_debug(*args, **kwargs):
        if __debug__:
            args_repr = [repr(a) for a in args]
            kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
            signature = ", ".join(args_repr + kwargs_repr)
            _LOGGER.debug(f"Calling {func.__name__}({signature})")
            value = func(*args, **kwargs)
            _LOGGER.debug(f"{func.__name__!r} returned {value!r}")
        else:
            value = func(*args, **kwargs)
        return value

    return wrapper_debug


def profile_func(output_file=None, sort_by='cumulative', lines_to_print=None, strip_dirs=False):
    """A time profiler decorator.

    This code was taken from: https://gist.github.com/ekhoda/2de44cf60d29ce24ad29758ce8635b78

    Inspired by and modified the profile decorator of Giampaolo Rodola:
    http://code.activestate.com/recipes/577817-profile-decorator/

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
    """

    def inner(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            _output_file = output_file or func.__name__ + '.prof'
            pr = cProfile.Profile()
            pr.enable()
            retval = func(*args, **kwargs)
            pr.disable()
            pr.dump_stats(_output_file)

            with open(_output_file, 'w') as f:
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


def to_be_implemented(func):
    """Print a warning message that this function/method has to be implemented."""

    @functools.wraps(func)
    def wrapper_tbi(*args, **kwargs):
        _LOGGER.warning(f"The function/method {func.__name__} is not yet implemented.")
        return func(*args, **kwargs)

    return wrapper_tbi


# Taken and adapted from https://github.com/QCoDeS/Qcodes

def deprecate(reason: Optional[str] = None,
              alternative: Optional[str] = None) -> Callable:
    """
    Deprecate a function or method. This will print a warning with the function name and where
    it is called from. If the optional parameters `reason` and `alternative` are given, that
    information will be printed with the warning.

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
            msg = f'The function \"{func.__name__}\" used at {caller.filename}:{caller.lineno} is deprecated'
            if reason is not None:
                msg += f', because {reason}'
            if alternative is not None:
                msg += f'. Use {alternative} as an alternative'
            msg += '.'
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

    from: https://wiki.python.org/moin/PythonDecoratorLibrary#Singleton
    """

    cls.__new_original__ = cls.__new__

    @functools.wraps(cls.__new__)
    def singleton_new(cls, *args, **kw):
        it = cls.__dict__.get('__it__')
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

    from: http://code.activestate.com/recipes/66531-singleton-we-dont-need-no-stinkin-singleton-the-bo/
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

    Usage:

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
            f"Cannot change class property '{self.func.__name__}' for class '{instance.__class__.__name__}'.")


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

    Examples:

        >>> class X:
        ...    pass
        >>> x = X()
        >>> spy_on_attr_change(x, obj_name="x")
        >>> x.a = 5

    From: https://nedbatchelder.com/blog/202206/adding_a_dunder_to_an_object.html
    """
    logger = logging.getLogger("egse.spy")

    class Wrapper(obj.__class__):

        def __setattr__(self, name, value):
            old = getattr(self, name, Nothing())
            logger.warning(
                f"Spy: in {obj_name or obj.__class__.__name__} -> {name}: {old!r} -> {value!r}")
            return super().__setattr__(name, value)

    class_name = obj.__class__.__name__
    obj.__class__ = Wrapper
    obj.__class__.__name__ = class_name
