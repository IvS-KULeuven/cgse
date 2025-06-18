import asyncio
import csv
import datetime
import logging
import operator
import os
import pprint
import random
import shutil
import textwrap
import time
from pathlib import Path

import pytest
from pytest import approx

from egse.decorators import execution_count
from egse.system import AttributeDict
from egse.system import Periodic
from egse.system import SignalCatcher
from egse.system import Timer
from egse.system import camel_to_kebab
from egse.system import camel_to_snake
from egse.system import check_argument_type
from egse.system import clear_average_execution_times
from egse.system import do_every
from egse.system import duration
from egse.system import env_var
from egse.system import execution_time
from egse.system import filter_by_attr
from egse.system import format_datetime
from egse.system import get_average_execution_time
from egse.system import get_average_execution_times
from egse.system import get_caller_breadcrumbs
from egse.system import get_caller_info
from egse.system import get_full_classname
from egse.system import get_os_name
from egse.system import get_os_version
from egse.system import get_referenced_var_name
from egse.system import get_system_name
from egse.system import get_system_stats
from egse.system import humanize_seconds
from egse.system import is_in
from egse.system import is_module
from egse.system import is_namespace
from egse.system import is_not_in
from egse.system import ping
from egse.system import read_last_line
from egse.system import read_last_lines
from egse.system import replace_environment_variable
from egse.system import save_average_execution_time
from egse.system import touch
from egse.system import wait_until
from egse.system import waiting_for
from fixtures.helpers import create_empty_file
from fixtures.helpers import create_text_file


def test_attr_dict():
    ad = AttributeDict()
    assert not ad
    assert len(ad) == 0

    ad = AttributeDict({})
    assert not ad
    assert len(ad) == 0

    ad = AttributeDict({"a": 1, "b": 2, "c": 3})
    assert ad
    assert len(ad) == 3
    assert ad.a == 1
    assert ad.b == 2
    assert ad.c == 3
    assert ad["a"] == 1
    assert ad["b"] == 2
    assert ad["c"] == 3

    ad = AttributeDict()
    ad.d = 4
    ad.e = 5
    ad.f = 6
    assert len(ad) == 3
    assert ad["d"] == 4
    assert ad["e"] == 5
    assert ad["f"] == 6
    assert ad.d == 4
    assert ad.e == 5
    assert ad.f == 6

    ad = AttributeDict({"a": 1, "b": 2, "c": 3})

    assert hasattr(ad, "a") and "a" in ad
    assert hasattr(ad, "b") and "b" in ad
    assert hasattr(ad, "c") and "c" in ad

    assert not hasattr(ad, "d")
    assert "d" not in ad

    del ad["b"]

    assert not hasattr(ad, "b")
    assert "b" not in ad

    del ad.c

    assert not hasattr(ad, "c")
    assert "c" not in ad

    ad = AttributeDict()

    # It is allowed to add objects to the AttributeDict, but we can not use them as attributes

    ad[1] = "a"
    ad[(7, 3)] = 73

    assert 73 in ad.values()

    with pytest.raises(KeyError):
        assert ad["a"] == 2

    with pytest.raises(AttributeError):
        assert ad.a == "2"


def test_attr_dict_rich():
    import rich

    ad = AttributeDict({"a": 1, "b": 2, "c": 3})
    rich.print(ad)
    assert str(ad) == "AttributeDict({'a':1, 'b':2, 'c':3})"

    ad = AttributeDict({"a": 1, "b": {"B": 2, "BB": 22}, "c": 3}, label="nested dict")
    rich.print(ad)
    assert str(ad) == "AttributeDict({'a':1, 'b':{'B': 2, 'BB': 22}, 'c':3}, label='nested dict')"

    ad = AttributeDict(
        {
            "a": 1,
            "b": {"B": 2, "BB": 22},
            "c": 3,
            "d": 4,
            "e": 5,
            "f": 6,
            "g": 7,
            "h": 8,
            "i": 9,
            "j": 10,
            "k": 11,
            "l": 12,
        },
        label="Long nested label",
    )
    rich.print(ad)
    assert str(ad) == (
        "AttributeDict({'a':1, 'b':{'B': 2, 'BB': 22}, 'c':3, 'd':4, 'e':5, 'f':6, 'g':7, 'h':8, 'i':9, "
        "'j':10, ...}, label='Long nested label')"
    )


def test_get_call_sequence():
    assert get_caller_breadcrumbs().startswith("call stack: test_get_call_sequence[")
    assert len(get_caller_breadcrumbs().split(" <- ")) == 5

    assert get_caller_breadcrumbs(prefix="XXX: ").startswith("XXX: test_get")
    assert "<-" not in get_caller_breadcrumbs(limit=1)

    assert "test_system.py" in get_caller_breadcrumbs(with_filename=True)


def test_caller():
    assert "test_caller" in get_caller_info()
    assert "test_caller" == get_caller_info().function
    assert __file__ in get_caller_info()
    assert __file__ in get_caller_info().filename
    assert type(get_caller_info().lineno) is int

    assert get_caller_info(level=0).filename.endswith("/egse/system.py")
    assert "get_caller_info" == get_caller_info(level=0).function

    # boundary test, eventually we end up at the <module> level

    assert get_caller_info(level=50).function == "<module>"
    assert get_caller_info(level=250).function == "<module>"

    def internal_function():
        return get_caller_info()

    assert "internal_function" in internal_function()
    assert __file__ in internal_function()

    class MyClass:
        def a_function(self):
            return get_caller_info(level=1)

    assert "a_function" in MyClass().a_function()
    assert __file__ in MyClass().a_function()


def test_var_names():
    a_var = 42
    assert get_referenced_var_name(a_var) == ["a_var"]

    b_var = a_var  # noqa
    assert "b_var" in get_referenced_var_name(a_var)
    assert "a_var" in get_referenced_var_name(a_var)

    # A function is also an object...

    assert get_referenced_var_name(test_var_names) == ["test_var_names"]

    # Test the use of this function inside a class, e.g. for reporting

    class MyClass:
        def __str__(self):
            return ", ".join(get_referenced_var_name(self))

    my_class = this_class = MyClass()  # noqa

    assert "my_class" in f"{my_class}"
    assert "this_class" in f"{my_class}"

    # There is no reference to an 'anonymous' instance of MyClass

    assert "" == f"{MyClass()}"


def test_ping():
    assert ping("10.0.0.1") is False
    assert ping("127.0.0.1") is True
    assert ping("localhost") is True


def test_timer():
    with Timer("Testing Timer context manager", precision=4) as timer:
        time.sleep(1.0)
        timer.log_elapsed()
        timer.log_elapsed()
        time.sleep(1.0)
        timer.log_elapsed()
        timer.log_elapsed()

    # Confirm that the elapsed time is not increased any more

    elapsed = timer()
    assert elapsed > 2.0
    time.sleep(1.0)
    assert elapsed == timer()

    timer.log_elapsed()
    timer.log_elapsed()


def test_system_stats():
    with Timer():
        stats = get_system_stats()

    print("\nget_system_stats() = ", end="")
    pprint.pprint(stats)

    assert stats["cpu_count"] > 1
    assert stats["cpu_load"][2] < 100
    assert stats["total_ram"] > 8.0
    assert stats["avail_ram"] > 0.0


def test_wait_until():
    class SleepUntilCount:
        def __init__(self, end):
            self._end = end
            self._count = 0

        def __call__(self, *args, **kwargs):
            self._count += 1
            return self._count >= self._end

        def check_count(self):
            return self.__call__()

    assert wait_until(SleepUntilCount(10), interval=0.5) is True
    assert wait_until(SleepUntilCount(10), timeout=10) is False
    assert wait_until(SleepUntilCount(10).check_count, timeout=10) is False

    assert wait_until(lambda x: x, 0, interval=0.5, timeout=1) is True
    assert wait_until(lambda x: x, 1) is False


def test_waiting_for():
    class SleepUntilCount:
        def __init__(self, end):
            self._end = end
            self._count = 0

        def __call__(self, *args, **kwargs):
            self._count += 1
            return self._count >= self._end

        def check_count(self):
            return self.__call__()

    with pytest.raises(TimeoutError):
        waiting_for(SleepUntilCount(10), interval=0.5)

    assert waiting_for(SleepUntilCount(10), timeout=10)

    assert waiting_for(SleepUntilCount(10).check_count, timeout=10)

    with pytest.raises(TimeoutError):
        waiting_for(lambda x: x, 0, interval=0.5, timeout=1)

    assert waiting_for(lambda x: x, 1)


def test_os_name_and_version():
    # We test primarily for 'unknown' because if this happens, the code needs to be updated.

    assert get_os_name() != "unknown"
    assert get_os_name() in ("centos", "macos", "ubuntu")

    assert get_system_name() in ("linux", "darwin", "windows")

    # Here we test for version numbers of the os, which is expected to be up-to-date

    assert get_os_version() != "unknown"
    if get_os_name() == "macos":
        assert float(get_os_version()) > 10.14
    if get_os_name() == "centos":
        assert float(get_os_version()) >= 7.0


def test_humanize_seconds():
    assert humanize_seconds(0) == "00s.000"
    assert humanize_seconds(0.123) == "00s.123"
    assert humanize_seconds(53.43) == "53s.430"
    assert humanize_seconds(92) == "01m32s.000"
    assert humanize_seconds(92, include_micro_seconds=False) == "01m32s"

    assert humanize_seconds(60 * 60 + 120 + 3.002) == "01h02m03s.002"

    assert humanize_seconds(24 * 60 * 60 + 32.42) == "1d 32s.420"

    assert humanize_seconds(3 * 24 * 60 * 60 + 0 * 60 * 60 + 24 * 60 + 0.020) == "3d 24m00s.020"

    assert humanize_seconds(365 * 24 * 60 * 60 + 14 * 60 * 60 + 0 * 60 + 16 + 0.7) == "365d 14h00m16s.700"

    assert humanize_seconds(2351 * 24 * 60 * 60) == "2351d 00s.000"
    assert humanize_seconds(2351 * 24 * 60 * 60, include_micro_seconds=False) == "2351d 00s"

    with Timer("Timing 10_000 humanize_seconds() calls"):
        for d in range(10_000):
            humanize_seconds(d * 24 * 60 * 60 + 14 * 60 * 60 + 0 * 60 + 16 + 0.7)


def test_replace_environment_variable():
    assert replace_environment_variable("PLAIN_STRING") == "PLAIN_STRING"

    os.environ["DATA_STORAGE_LOCATION"] = "/Users/rik/data/CSL"
    assert replace_environment_variable("ENV['DATA_STORAGE_LOCATION']") == "/Users/rik/data/CSL"

    os.environ["DATA_STORAGE_LOCATION"] = "/Users/rik/data"
    assert replace_environment_variable("ENV['DATA_STORAGE_LOCATION']/CSL") == "/Users/rik/data/CSL"


class X:
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


def test_filter_by_attr():
    x0 = X({"a": 1, "b": 1})
    x1 = X({"a": 1, "b": 2})
    x2 = X({"a": 1, "b": 3, "c": 1})

    a_list = [x0, x1, x2]

    result = filter_by_attr(a_list, a=1)
    assert result == [x0, x1, x2]

    result = filter_by_attr(a_list, b=2)
    assert result == [x1]

    result = filter_by_attr(a_list, a=1, b=2)
    assert result == [x1]

    result = filter_by_attr(a_list, a=1, b=3, c=1)
    assert result == [x2]

    result = filter_by_attr(a_list, b=(is_in, (1, 2)))
    assert result == [x0, x1]

    result = filter_by_attr(a_list, b=(is_not_in, (1, 2)))
    assert result == [x2]

    result = filter_by_attr(a_list, b=(operator.ne, 2))
    assert result == [x0, x2]

    result = filter_by_attr(a_list, b=(operator.gt, 2))
    assert result == [x2]

    result = filter_by_attr(a_list, c=1, d=4)
    assert result == []

    result = filter_by_attr(a_list, d=4)
    assert result == []


def test_filter_by_attr_with_attribute_dict():
    a_list = [
        AttributeDict({"a": 1, "b": 1}),
        AttributeDict({"a": 1, "b": 2}),
        AttributeDict({"a": 1, "b": 3, "c": 1}),
    ]

    result = filter_by_attr(a_list, a=1)
    assert len(result) == 3

    result = filter_by_attr(a_list, b=2)
    assert len(result) == 1

    result = filter_by_attr(a_list, a=1, b=2)
    assert len(result) == 1

    result = filter_by_attr(a_list, a=1, b=3, c=1)
    assert len(result) == 1

    result = filter_by_attr(a_list, b=(lambda a, b: a in b, (1, 2)))
    assert len(result) == 2

    result = filter_by_attr(a_list, c=1, d=4)
    assert len(result) == 0

    result = filter_by_attr(a_list, d=4)
    assert len(result) == 0


def test_filter_by_attr_with_class():
    class X:
        def __init__(self, x, y, z):
            self.x = x
            self.y = y
            self.z = z

    class Y:
        def __init__(self, a, b, c):
            self.a = a
            self.b = b
            self.c = c

    x0 = X(1, 2, 3)
    x1 = X(1, 3, 3)
    x2 = X(1, 2, 2)
    x3 = X(2, 3, 4)
    x4 = X(2, Y(1, 2, 3), 4)

    a_list = [x0, x1, x2, x3, x4]

    result = filter_by_attr(a_list, x=1)
    assert len(result) == 3

    result = filter_by_attr(a_list, y=2)
    assert len(result) == 2

    result = filter_by_attr(a_list, y__b=2)
    assert len(result) == 1

    result = filter_by_attr(a_list, y__a=(hasattr, True))
    assert len(result) == 1

    result = filter_by_attr(a_list, y__a=(hasattr, False))
    assert len(result) == 4

    x2 = X(1, Y(2, 3, 3), 3)
    a_list = [x0, x1, x2, x3, x4]

    result = filter_by_attr(a_list, y__b=(is_in, (1, 2)))
    assert len(result) == 1 and result == [x4]


def test_filter_by_attr_has():
    """Test if iterable has an attribute."""

    x0 = X({"a": 1, "b": 1, "d": 1})
    x1 = X({"a": 1, "b": 2, "d": 2})
    x2 = X({"a": 1, "b": 3, "c": 1, "d": 3})

    a_list = [x0, x1, x2]

    result = filter_by_attr(a_list, b=(hasattr, True))
    assert result == [x0, x1, x2]

    result = filter_by_attr(a_list, b=(hasattr, False))
    assert result == []

    result = filter_by_attr(a_list, c=(hasattr, True))
    assert result == [x2]

    result = filter_by_attr(a_list, c=(hasattr, False))
    assert result == [x0, x1]

    result = filter_by_attr(a_list, b=(hasattr, True), d=2, a=(operator.le, 1))
    assert result == [x1]

    result = filter_by_attr(a_list, b=(hasattr, True), d=2, a=(operator.lt, 1))
    assert result == []

    result = filter_by_attr(a_list, c=(hasattr, False), d=2, a=(operator.le, 1))
    assert result == [x1]


def test_filter_by_attr_has_with_attribute_dict():
    """Test if iterable has an attribute."""

    a_list = [
        AttributeDict({"a": 1, "b": 1}),
        AttributeDict({"a": 1, "b": 2}),
        AttributeDict({"a": 1, "b": 3, "c": 1}),
    ]

    result = filter_by_attr(a_list, b=(hasattr, True))
    assert len(result) == 3

    result = filter_by_attr(a_list, c=(hasattr, False))
    assert len(result) == 2


def test_read_last_line():
    # non-existing file

    line = read_last_line("/xxx")
    assert line is None

    prefix = Path(__file__).parent
    filename = prefix / "data/tmp/empty_data_file.txt"

    with create_empty_file(filename, create_folder=True):
        line = read_last_line(filename)
    assert line == ""

    filename = prefix / "data/tmp/data_file.txt"

    with create_text_file(
        filename,
        textwrap.dedent(
            """\
                001 002 003
                002 003 001
                003 002 001
                """
        ),
    ):
        line = read_last_line(filename)
    assert line == "003 002 001"


def test_read_last_lines():
    with pytest.raises(AssertionError, match="a positive number or zero"):
        _ = read_last_lines("/xxx", -1)

    assert read_last_lines("/xxx", 0) == []
    assert read_last_lines("/xxx", 1) == []

    prefix = Path(__file__).parent
    filename = prefix / "data/tmp/empty_data_file.txt"

    with create_empty_file(filename, create_folder=True):
        line = read_last_lines(filename, 3)
    assert line == []

    filename = prefix / "data/tmp/data_file.txt"

    with create_text_file(
        filename,
        textwrap.dedent(
            """\
                001 002 003
                002 003 001
                003 002 001
                """
        ),
    ):
        lines = read_last_lines(filename, 0)
        assert lines == [""]

        lines = read_last_lines(filename, 1)
        assert lines == ["003 002 001"]

        lines = read_last_lines(filename, 2)
        assert lines == ["002 003 001", "003 002 001"]

        lines = read_last_lines(filename, 10)
        assert lines == ["001 002 003", "002 003 001", "003 002 001"]


def test_read_last_lines_from_big_data_file(tmp_path):
    temp_file = tmp_path / "data.csv"

    fixed_data = generate_big_data_file(temp_file)

    with Timer(name="log-file", precision=6):
        lines = read_last_lines(temp_file, 5)
        assert len(lines) == 5

    assert lines == fixed_data[-5:]


def test_format_datetime():
    dt = datetime.datetime(2020, 6, 13, 14, 45, 45, 696138)

    dts = format_datetime(dt=dt)
    assert dts == "2020-06-13T14:45:45.696"

    dts = format_datetime(dt=dt, fmt="%Y-%m-%d %H:%M:%S")
    assert dts == "2020-06-13 14:45:45"

    dts = format_datetime(dt=dt, fmt="%y%m%d_%H%M%S")
    assert dts == "200613_144545"

    # Tests added to fix issue #1441 about incorrect timestamps

    dt = datetime.datetime(2020, 6, 13, 14, 45, 59, 999500)

    dts = format_datetime(dt=dt)
    assert dts == "2020-06-13T14:45:59.999"

    dts = format_datetime(dt=dt, precision=6)
    assert dts == "2020-06-13T14:45:59.999500"

    dt = datetime.datetime(2020, 6, 13, 14, 45, 59, 999501, tzinfo=datetime.timezone.utc)

    dts = format_datetime(dt=dt)
    assert dts == "2020-06-13T14:45:59.999+0000"

    dts = format_datetime(dt=dt, precision=6)
    assert dts == "2020-06-13T14:45:59.999501+0000"

    dts_today = format_datetime("today")
    dts_yesterday = format_datetime("yesterday")
    dts_day_before_yesterday = format_datetime("day before yesterday")
    dts_tomorrow = format_datetime("tomorrow")

    dt_today = datetime.datetime.strptime(dts_today, "%Y%m%d")
    dt_yesterday = datetime.datetime.strptime(dts_yesterday, "%Y%m%d")
    dt_day_before_yesterday = datetime.datetime.strptime(dts_day_before_yesterday, "%Y%m%d")
    dt_tomorrow = datetime.datetime.strptime(dts_tomorrow, "%Y%m%d")

    assert dt_today - dt_yesterday == datetime.timedelta(days=1)
    assert dt_today - dt_day_before_yesterday == datetime.timedelta(days=2)
    assert dt_today - dt_tomorrow == datetime.timedelta(days=-1)

    with pytest.raises(ValueError):
        _ = format_datetime("another day")

    dts = format_datetime()

    assert dts.startswith(format_datetime("today", fmt="%Y-%m-%d"))


def test_full_classname():
    assert get_full_classname(print) == "builtins.print"
    assert get_full_classname(int) == "builtins.int"
    assert get_full_classname(get_full_classname) == "egse.system.get_full_classname"
    assert get_full_classname(int(2)) == "builtins.int"
    assert get_full_classname(3.14) == "builtins.float"
    assert get_full_classname(3 + 6j) == "builtins.complex"
    assert get_full_classname(AttributeDict) == "egse.system.AttributeDict"
    assert get_full_classname(AttributeDict()) == "egse.system.AttributeDict"
    assert get_full_classname(datetime.datetime(2020, 6, 13, 14, 45, 45, 696138)) == "datetime.datetime"


def test_argument_type():
    check_argument_type("a string", "name", (int, str), allow_none=True)
    check_argument_type(None, "name", (int, str), allow_none=True)
    with pytest.raises(TypeError):
        check_argument_type(None, "name", (int, str), allow_none=False)
        print("Shouldn't have reached this line, check the code!")

    with pytest.raises(TypeError):
        check_argument_type(3.14, "name", (int, str), allow_none=True)
        print("Shouldn't have reached this line, check the code!")


def test_signals():
    killer = SignalCatcher()

    pid = os.getpid()

    os.kill(pid, 15)  # send a TERM signal to this process

    while not killer.term_signal_received:
        time.sleep(1.0)

    assert killer.signal_number == 15
    assert killer.signal_name == "SIGTERM"

    killer.clear(term=True)

    os.kill(pid, 30)  # send a SIGUSR1 signal to this process

    while not killer.user_signal_received:
        time.sleep(1.0)

    assert killer.signal_number == 30
    assert killer.signal_name == "SIGUSR1"

    killer.clear()


def test_env_var_context_manager():
    os.environ["TEST_ENV_VAR_1"] = "before context manager"

    assert os.environ.get("TEST_ENV_VAR_1") == "before context manager"
    assert os.environ.get("TEST_ENV_VAR_2") is None

    with env_var(TEST_ENV_VAR_1="within context manager", TEST_ENV_VAR_2="new variable"):
        assert os.environ.get("TEST_ENV_VAR_1") == "within context manager"
        assert os.environ.get("TEST_ENV_VAR_2") == "new variable"

    assert os.environ.get("TEST_ENV_VAR_1") == "before context manager"
    assert os.environ.get("TEST_ENV_VAR_2") is None


# The following is a slow test, it takes about 8s.
# You can deselect this test by running: `pytest -m 'not slow' src/tests/test_system.py`


@pytest.mark.slow
def test_function_timing():
    print()

    def one_second():
        time.sleep(1.0)

    def incr(count):
        time.sleep(count)
        return count + 1

    @execution_time
    def wait_seconds(wait_time: float):
        time.sleep(wait_time)

    x = 0
    for _ in range(2):
        x = save_average_execution_time(incr, x)

    assert get_average_execution_time(incr) == approx(0.5, abs=0.005, rel=0.005)

    for _ in range(10):
        save_average_execution_time(time.sleep, 0.2)

    assert get_average_execution_time(time.sleep) == approx(0.2, abs=0.005, rel=0.005)

    for _ in range(3):
        save_average_execution_time(one_second)

    assert get_average_execution_time(one_second) == approx(1.0, abs=0.01, rel=0.01)

    for _ in range(2):
        save_average_execution_time(save_average_execution_time, one_second)

    assert get_average_execution_time(one_second) == approx(1.0, abs=0.01, rel=0.01)

    print(get_average_execution_times())

    clear_average_execution_times()

    assert len(get_average_execution_times()) == 0

    for _ in range(3):
        wait_seconds(0.3)

    print(get_average_execution_times())

    assert get_average_execution_time(wait_seconds) == approx(0.3, abs=0.01, rel=0.01)


def test_get_module_location():
    import egse
    from egse.system import get_module_location
    import multiprocessing.dummy

    # egse is a namespace package which can have different locations!
    assert get_module_location(egse) is None
    assert get_module_location("egse") is None

    # egse.system is a module (.py file) and its location is in the `egse` module/namespace
    assert get_module_location(egse.system) == Path(egse.system.__file__).parent
    assert get_module_location("egse.system") == Path(egse.system.__file__).parent

    # get_module_location is a function, its location is in the system module in the egse namespace
    assert get_module_location(get_module_location) == Path(egse.system.__file__).parent

    # multiprocessing.dummy is a package, so its location is in the multiprocessing folder
    assert get_module_location(multiprocessing.dummy) == Path(multiprocessing.dummy.__file__).parent
    assert get_module_location("multiprocessing.dummy") == Path(multiprocessing.dummy.__file__).parent


def test_get_system_architecture():
    from egse.system import get_system_architecture

    assert "x86" in get_system_architecture() or "arm" in get_system_architecture()


def test_duration():
    dt = datetime.datetime
    td = datetime.timedelta
    tz = datetime.timezone

    now = dt.now(tz=tz.utc)
    dt_start = format_datetime(now)

    dt_end = format_datetime(now + td(seconds=2, milliseconds=500))

    assert duration(dt_start, dt_end).seconds == 2
    assert duration(dt_start, dt_end).total_seconds() == approx(2.5)
    assert duration(dt_start, dt_end) == duration(dt_end, dt_start)

    # The following calls just should raise an exception

    now_plus_half_a_second = now + td(milliseconds=500)
    assert duration(now, now_plus_half_a_second).total_seconds() == approx(0.5)
    assert duration(now_plus_half_a_second, now).total_seconds() == approx(0.5)

    date_1963 = format_datetime(dt(1963, 2, 16, 12, 00, 00, tzinfo=tz.utc))
    date_2023 = format_datetime(dt(2023, 2, 16, 12, 00, 00, tzinfo=tz.utc))
    date_2024 = format_datetime(dt(2024, 2, 16, 12, 00, 00, tzinfo=tz.utc))
    assert str(duration(date_2024, date_1963)) == "22280 days, 0:00:00"
    assert str(duration(date_2024, date_2023)) == "365 days, 0:00:00"

    yesterday = now - td(days=1)
    assert str(duration(now, yesterday)) == "1 day, 0:00:00"
    assert str(duration(now + td(minutes=3.0, seconds=27), yesterday)) == "1 day, 0:03:27"


def test_log_levels_disabled(caplog):
    print()

    import logging
    from egse.system import all_logging_disabled

    with all_logging_disabled(highest_level=logging.WARNING):
        logging.critical("a critical message")
        logging.error("an error message")
        logging.warning("a warning message")
        logging.info("an info message")
        logging.debug("a debug message")

    assert "critical" in caplog.text
    assert "error" in caplog.text
    assert "warning" not in caplog.text
    assert "info" not in caplog.text
    assert "debug" not in caplog.text

    caplog.clear()

    logger = logging.getLogger("testing_logging_disabled")

    with all_logging_disabled(highest_level=logging.INFO):
        logger.critical("a critical message")
        logger.error("an error message")
        logger.warning("a warning message")
        logger.info("an info message")
        logger.debug("a debug message")

        logging.warning("a logging warning message")
        logging.info("a logging info message")

    assert "critical" in caplog.text
    assert "error" in caplog.text
    assert "warning" in caplog.text
    assert "info" not in caplog.text
    assert "debug" not in caplog.text


def test_get_active_loggers():
    from egse.system import get_active_loggers

    assert "testing_active_loggers" not in get_active_loggers()
    assert "testing" not in get_active_loggers()
    assert "testing.active" not in get_active_loggers()
    assert "testing.active.loggers" not in get_active_loggers()

    _ = logging.getLogger("testing_active_loggers")

    assert "testing_active_loggers" in get_active_loggers()

    _ = logging.getLogger("testing.active.loggers")

    assert "testing" in get_active_loggers()
    assert "testing.active" in get_active_loggers()
    assert "testing.active.loggers" in get_active_loggers()


def test_touch():
    touch(__file__)

    assert Path(__file__).exists()

    fn = Path(__file__).parent / "data/counter_test" / "x.cnt"

    try:
        assert not fn.exists()
        touch(fn)
        assert fn.exists()
    finally:
        shutil.rmtree(fn.parent)


def test_is_module():
    import egse
    import egse.version
    from egse.system import get_os_name

    assert is_module(egse)
    assert is_module("egse")

    assert is_module(egse.version)
    assert is_module("egse.version")

    assert not is_module(get_os_name)
    assert not is_module("non-existing-module")


def test_is_namespace():
    import egse
    import egse.version
    from egse.system import get_os_name

    assert is_namespace(egse)
    assert is_namespace("egse")

    assert not is_namespace(egse.version)
    assert not is_namespace("egse.version")

    assert not is_module(get_os_name)
    assert not is_namespace("non-existing-module")


def test_get_host_ip():
    from egse.system import get_host_ip

    ip = get_host_ip()
    if ip:
        assert "." in ip


def test_do_every(capsys):
    with Timer():
        do_every(0.5, lambda: print(f"{format_datetime()} Hello, World!"), count=0)
    captured = capsys.readouterr()
    assert captured.out == ""

    do_every(0.5, lambda: print(f"{format_datetime()} Hello, World!"), count=1)
    captured = capsys.readouterr()
    assert len(captured.out.rstrip().split("\n")) == 1

    do_every(0.5, lambda: print(f"{format_datetime()} Hello, World!"), count=3)
    captured = capsys.readouterr()
    print("\n".join(captured.out.rstrip().split("\n")))
    assert len(captured.out.rstrip().split("\n")) == 3


def generate_big_data_file(filename: Path, total_n_rows: int = 500_000) -> list[str]:
    """
    Generates a big data file containing 500_000 rows (by default) with each row having a
    timestamp and 10 datapoints of randomized temperatures. The last 10 rows have fixed
    deterministic data that can be tested with pytest.

    Returns:
        The function returns the fixed data rows as a list of str with comma separated values.
            The strings are the same as those written in the CSV file.
    """
    total_rows = 500000
    columns = 10  # Number of temperature columns
    start_date = datetime.datetime(2023, 1, 1, 0, 0, 0)
    time_increment = datetime.timedelta(minutes=1)

    # Deterministic data for the last 10 rows
    deterministic_data = [
        [20.0, 21.5, 22.0, 19.8, 23.1, 22.5, 21.8, 20.5, 19.7, 22.3],
        [20.1, 21.6, 22.1, 19.9, 23.2, 22.6, 21.9, 20.6, 19.8, 22.4],
        [20.2, 21.7, 22.2, 20.0, 23.3, 22.7, 22.0, 20.7, 19.9, 22.5],
        [20.3, 21.8, 22.3, 20.1, 23.4, 22.8, 22.1, 20.8, 20.0, 22.6],
        [20.4, 21.9, 22.4, 20.2, 23.5, 22.9, 22.2, 20.9, 20.1, 22.7],
        [20.5, 22.0, 22.5, 20.3, 23.6, 23.0, 22.3, 21.0, 20.2, 22.8],
        [20.6, 22.1, 22.6, 20.4, 23.7, 23.1, 22.4, 21.1, 20.3, 22.9],
        [20.7, 22.2, 22.7, 20.5, 23.8, 23.2, 22.5, 21.2, 20.4, 23.0],
        [20.8, 22.3, 22.8, 20.6, 23.9, 23.3, 22.6, 21.3, 20.5, 23.1],
        [20.9, 22.4, 22.9, 20.7, 24.0, 23.4, 22.7, 21.4, 20.6, 23.2],
    ]

    def generate_random_temperature_data():
        """Generate random temperature data between 15 and 35 ºC."""
        return [round(random.uniform(15.0, 35.0), 1) for _ in range(columns)]

    def format_timestamp(dt):
        """Format datetime to ISO format."""
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"Generating {total_rows} rows of data to {filename}...")

    with open(filename, "w", newline="") as csvfile:
        # Create header: timestamp, temp1, temp2, ..., temp10
        header = ["timestamp"] + [f"temp{i + 1}" for i in range(columns)]

        writer = csv.writer(csvfile)
        writer.writerow(header)

        # Generate random data for most rows
        current_date = start_date
        for i in range(total_rows - 10):
            row_data = [format_timestamp(current_date)] + generate_random_temperature_data()
            writer.writerow(row_data)
            current_date += time_increment

        # Add the last 10 rows with deterministic data
        for i in range(10):
            row_data = [format_timestamp(current_date)] + deterministic_data[i]
            writer.writerow(row_data)
            current_date += time_increment

    return [
        (
            f"{format_timestamp(start_date + time_increment * (total_rows - 10 + i))},"
            f"{','.join([f'{x:3.1f}' for x in row])}"
        )
        for i, row in enumerate(deterministic_data)
    ]


@pytest.mark.asyncio
async def test_periodic():
    count = 0

    def plain_old_function():
        nonlocal count
        logging.info("I'm just a plain old Python function.")
        count += 1
        time.sleep(1.0)

    async def async_function():
        nonlocal count
        logging.info("I'm a brand new async function.")
        count += 1
        await asyncio.sleep(0.5)

    periodic = Periodic(callback=async_function, interval=1.0, skip=False, repeat=5)
    periodic.start()

    # Prevent the test from terminating

    while periodic.is_running():
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            logging.info("periodic_test cancelled")
            logging.info(f"interval ended at {periodic.interval}")
            break

    assert count == 5

    count = 0

    periodic = Periodic(callback=async_function, interval=0.4, skip=True, repeat=5)
    periodic.start()

    # Prevent the test from terminating

    while periodic.is_running():
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            logging.info("periodic_test cancelled")
            logging.info(f"interval ended at {periodic.interval}")
            break

    assert count == 3  # the function call is skipped twice


@pytest.mark.asyncio
async def test_periodic_exception(caplog):
    # So, what happens when a callback throws an exception? Aa error message is logged.

    @execution_count
    def not_good():
        raise ValueError("This is not good!")

    periodic = Periodic(callback=not_good, interval=0.5, skip=True, repeat=2)
    periodic.start()

    await asyncio.sleep(1.2)

    assert "ValueError caught: This is not good!" in caplog.text
    assert not_good.counts() == 2


def test_camel_to_kebab():
    assert camel_to_kebab("ConfigurationControlServer") == "configuration-control-server"
    assert camel_to_kebab("XMLHttpService") == "xml-http-service"
    assert camel_to_kebab("My123BestProject") == "my123-best-project"

    assert camel_to_kebab("is-already-kebab") == "is-already-kebab"


def test_camel_to_snake():
    assert camel_to_snake("ConfigurationControlServer") == "configuration_control_server"
    assert camel_to_snake("XMLHttpService") == "xml_http_service"
    assert camel_to_snake("My123BestProject") == "my123_best_project"

    assert camel_to_snake("is_already_snake") == "is_already_snake"
