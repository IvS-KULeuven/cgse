import logging
import time
from pathlib import Path

import pytest

from egse.decorators import debug
from egse.decorators import dynamic_interface
from egse.decorators import profile
from egse.decorators import profile_func
from egse.decorators import query_command
from egse.decorators import read_command
from egse.decorators import spy_on_attr_change
from egse.decorators import static_vars
from egse.decorators import time_it
from egse.decorators import timer
from egse.decorators import to_be_implemented
from egse.decorators import transaction_command
from egse.decorators import write_command
from egse.settings import Settings

MODULE_LOGGER = logging.getLogger(__name__)

from egse.decorators import (
    singleton,
    deprecate,
    classproperty,
    borg,
)


def test_static_vars():

    @static_vars(counter=-1)
    def increment(amount: int = 1):
        increment.counter += amount
        return increment.counter

    assert increment() == 0
    assert increment(5) == 5
    assert increment() == 6


def test_timer(caplog):

    caplog.set_level(logging.INFO)

    @timer(level=logging.INFO, precision=1)
    def func(seconds: float = 1.0):
        time.sleep(seconds)

    func()
    assert "Finished 'func' in 1.0 secs" in caplog.text

    func(2.3)
    assert "Finished 'func' in 2.3 secs" in caplog.text


def test_time_it(caplog):

    caplog.set_level(logging.INFO)

    @time_it(count=1000_000)
    def func(x: float = 1.0):
        return x ** 2

    func()
    assert "Finished 'func' in " in caplog.text


def test_debug(caplog):
    caplog.set_level(level=logging.DEBUG)

    @debug
    def func1():
        pass

    func1()
    assert "Calling func1()" in caplog.text

    @debug
    def func2(x, y):
        return x*y

    func2(2, 3)
    assert "Calling func2(2, 3)" in caplog.text

    func2('#', 5)
    assert "Calling func2('#', 5)" in caplog.text
    assert "'func2' returned '#####'"


def test_to_be_implemented(caplog):

    @to_be_implemented
    def func():
        pass

    func()
    assert 'WARNING' in caplog.text
    assert 'func is not yet implemented'


def test_profile(capsys):

    @profile
    def func(name: str = "World"):
        return f"hello, {name}!"

    Settings.set_profiling(False)

    func()

    captured = capsys.readouterr()
    assert "PROFILE" not in captured.out

    Settings.set_profiling(True)

    func()

    captured = capsys.readouterr()
    assert "PROFILE" in captured.out

    Settings.set_profiling(False)


def test_profile_func(caplog):

    caplog.set_level(level=logging.DEBUG)

    def power(x: float, exp: int = 2):
        return x ** exp

    output_file = "profiling_func.prof"

    @profile_func(output_file=output_file, strip_dirs=True, sort_by=('calls', 'cumulative'))
    def func(x: int = 0):
        return power(x)

    func()

    assert Path(output_file).exists()

    # TODO: add some more checks on the content of the profiling output

    Path(output_file).unlink()


def test_dynamic_interface():

    @dynamic_interface
    def func():
        return func.__dynamic_interface
    assert func() is True

    @query_command
    def query():
        return query.__query_command
    assert query() is True

    @transaction_command
    def transaction():
        return transaction.__transaction_command
    assert transaction() is True

    @read_command
    def read():
        return read.__read_command
    assert read() is True

    @write_command
    def write():
        return write.__write_command
    assert write() is True


def test_classproperty():
    class Message:
        _msg_cache = set()

        def __init__(self):
            self.prefix = "msg> "

        @classproperty
        def messages_count(cls):
            return len(cls._msg_cache)

        @classproperty
        def name(cls):
            return cls.__name__

        @classmethod
        def add_message(cls, msg):
            cls._msg_cache.add(msg)

    msg = Message()

    assert msg.messages_count == 0

    msg.add_message("message 1")

    assert msg.messages_count == 1

    assert "Message" in msg.name

    with pytest.raises(AttributeError):
        msg.name = "SomethingElse"

    assert "Something" not in msg.name


def test_borg():
    @borg
    class BorgOne:
        _dry_run = False

        @classmethod
        def is_dry_run(cls) -> bool:
            return cls._dry_run

        @classmethod
        def set_dry_run(cls, flag: bool):
            cls._dry_run = flag

    assert BorgOne.is_dry_run() is False
    assert BorgOne().is_dry_run() is False

    BorgOne.set_dry_run(True)

    assert BorgOne.is_dry_run() is True
    assert BorgOne().is_dry_run() is True

    BorgOne().set_dry_run(False)
    assert BorgOne.is_dry_run() is False
    assert BorgOne().is_dry_run() is False

    assert BorgOne() is not BorgOne()  # it's not a singleton


def test_singleton():
    @singleton
    class Foo:
        def __new__(cls):
            cls.x = 10
            return object.__new__(cls)

        def __init__(self):
            assert self.x == 10
            self.x = 15

    assert Foo().x == 15

    foo = Foo()

    assert foo.x == 15

    foo.x = 20

    assert foo.x == 20
    assert Foo().x == 20

    assert Foo() == foo == Foo()
    assert Foo() is foo is Foo()


def test_deprecation():
    """
    Simple tests for the @deprecate decorator.

    If you want to check how the warning message looks like, you can use

        with pytest.deprecated_call() as record:
            deprecated_function()
            MODULE_LOGGER.debug(record[0].message)

    """

    @deprecate(
        reason="we are testing the @deprecate decorator " "on a simple function without arguments",
        alternative="the new_function() instead",
    )
    def deprecated_function():
        # delegate to new_function()
        return new_function()

    def new_function():
        pass

    # This is how we check that indeed the Warning was issued?

    with pytest.deprecated_call():
        deprecated_function()

    class Foo:
        @deprecate(
            reason="we need to test if the @deprecate decorator also works "
            "properly with (class) methods"
        )
        def is_deprecated(self):
            return True

    foo = Foo()

    with pytest.deprecated_call():
        foo.is_deprecated()


def test_spy_on_attr_change(caplog):

    class X:
        ...

    class Y:
        ...

    # Check if the changes are reported in the log messages

    spy_on_attr_change(x := X())

    x.a = 42
    assert "in X -> a: <Nothing> -> 42" in caplog.text
    x.b = 37
    assert "in X -> b: <Nothing> -> 37" in caplog.text
    x.a = 5
    assert "in X -> a: 42 -> 5" in caplog.text

    caplog.clear()

    xx = X()

    # Another instance of class X should not be monitored

    xx.aa = 77
    assert "in xx -> aa: <Nothing> -> 77" not in caplog.text

    spy_on_attr_change(xx, obj_name="xx")

    # now this instance is also monitored and change reported in the log

    xx.aa = 55
    assert "in xx -> aa: 77 -> 55" in caplog.text

    caplog.clear()

    spy_on_attr_change(y := Y())

    # These tests are mainly to confirm that the name of the class is correct
    # even with multiple calls to the `spy_on_attr_change()` function.

    x.b = 3
    assert "in X -> b: 37 -> 3" in caplog.text
    y.a = 8
    assert "in Y -> a: <Nothing> -> 8" in caplog.text
    xx.bb = 11
    assert "Spy: in xx -> bb: <Nothing> -> 11" in caplog.text
