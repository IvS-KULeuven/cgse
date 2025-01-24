import datetime
import operator
import os
import pprint
import textwrap
import time
from pathlib import Path

import pytest
from pytest import approx

from egse.system import AttributeDict
from egse.system import SignalCatcher
from egse.system import Timer
from egse.system import check_argument_type
from egse.system import clear_average_execution_times
from egse.system import env_var
from egse.system import execution_time
from egse.system import filter_by_attr
from egse.system import format_datetime
from egse.system import get_average_execution_time
from egse.system import get_average_execution_times
from egse.system import get_caller_info
from egse.system import get_full_classname
from egse.system import get_os_name
from egse.system import get_os_version
from egse.system import get_referenced_var_name
from egse.system import get_system_name
from egse.system import get_system_stats
from egse.system import humanize_seconds
from egse.system import is_in
from egse.system import is_not_in
from egse.system import ping
from egse.system import read_last_line
from egse.system import replace_environment_variable
from egse.system import save_average_execution_time
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

    b_var = a_var
    assert "b_var" in get_referenced_var_name(a_var)
    assert "a_var" in get_referenced_var_name(a_var)

    # A function is also an object...

    assert get_referenced_var_name(test_var_names) == ["test_var_names"]

    # Test the use of this function inside a class, e.g. for reporting

    class MyClass:
        def __str__(self):
            return ", ".join(get_referenced_var_name(self))

    my_class = this_class = MyClass()

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

    assert humanize_seconds(60 * 60 + 120 + 3.002) == "01h02m03s.002"

    assert humanize_seconds(24 * 60 * 60 + 32.42) == "1d 32s.420"

    assert humanize_seconds(3 * 24 * 60 * 60 + 0 * 60 * 60 + 24 * 60 + 0.020) == "3d 24m00s.020"

    assert (
        humanize_seconds(365 * 24 * 60 * 60 + 14 * 60 * 60 + 0 * 60 + 16 + 0.7)
        == "365d 14h00m16s.700"
    )

    assert humanize_seconds(2351 * 24 * 60 * 60) == "2351d 00s.000"

    with Timer():
        for d in range(10000):
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
    filename = prefix / "data/empty_data_file.txt"

    with create_empty_file(filename, create_folder=True):
        line = read_last_line(filename)
    assert line == ""

    filename = prefix / "data/data_file.txt"

    with create_text_file(filename, textwrap.dedent(
        """\
        001 002 003
        002 003 001
        003 002 001
        """
    )):
        line = read_last_line(filename)
    assert line == "003 002 001"


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

    dts_today = format_datetime('today')
    dts_yesterday = format_datetime('yesterday')
    dts_tomorrow = format_datetime('tomorrow')

    dt_today = datetime.datetime.strptime(dts_today, "%Y%m%d")
    dt_yesterday = datetime.datetime.strptime(dts_yesterday, "%Y%m%d")
    dt_tomorrow = datetime.datetime.strptime(dts_tomorrow, "%Y%m%d")

    assert dt_today - dt_yesterday == datetime.timedelta(days=1)
    assert dt_today - dt_tomorrow == datetime.timedelta(days=-1)

    with pytest.raises(ValueError):
        _ = format_datetime("another day")

    dts = format_datetime()

    assert dts.startswith(format_datetime('today', fmt="%Y-%m-%d"))


def test_full_classname():

    assert get_full_classname(print) == 'builtins.print'
    assert get_full_classname(int) == 'builtins.int'
    assert get_full_classname(get_full_classname) == 'egse.system.get_full_classname'
    assert get_full_classname(int(2)) == 'builtins.int'
    assert get_full_classname(3.14) == 'builtins.float'
    assert get_full_classname(3 + 6j) == 'builtins.complex'
    assert get_full_classname(AttributeDict) == 'egse.system.AttributeDict'
    assert get_full_classname(AttributeDict()) == 'egse.system.AttributeDict'
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
    assert get_module_location('egse.system') == Path(egse.system.__file__).parent

    # get_module_location is a function, its location is in the system module in the egse namespace
    assert get_module_location(get_module_location) == Path(egse.system.__file__).parent

    # multiprocessing.dummy is a package, so its location is in the multiprocessing folder
    assert get_module_location(multiprocessing.dummy) == Path(multiprocessing.dummy.__file__).parent
    assert get_module_location("multiprocessing.dummy") == Path(multiprocessing.dummy.__file__).parent


def test_get_system_architecture():
    from egse.system import get_system_architecture

    assert 'x86' in get_system_architecture() or 'arm' in get_system_architecture()
