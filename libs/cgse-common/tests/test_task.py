import asyncio
import functools
import time

import pytest

from egse.task import AwaitTask
from egse.task import task


def execution_count(func):
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


@execution_count
def plain_func(msg: str, sleep: float = 1.0):
    time.sleep(sleep)
    return f"plain_func: I got this message: {msg}, waited {sleep}s before executing"


@execution_count
async def async_func(msg: str, sleep: float = 1.0):

    await asyncio.sleep(sleep)
    return f"async_func: I got this message: {msg}, waited {sleep}s before executing"


def test_synchronous():

    plain_func.reset()

    t = task(plain_func, "Hello, plain old Python function", 0.0)
    assert isinstance(t, AwaitTask)
    assert "plain" in t()
    assert "plain" in t.execute()
    assert plain_func.counts() == 2

    async_func.reset()

    t = task(async_func, "hello, async function", 0.0)
    assert isinstance(t, AwaitTask)
    assert "async" in t()
    assert "async" in t.execute()
    assert async_func.counts() == 2


@pytest.mark.asyncio
async def test_asynchronous():

    plain_func.reset()

    t = task(plain_func, "Hello, plain old Python function", 0.0)
    assert isinstance(t, AwaitTask)
    assert "plain" in await t
    assert "plain" in t()
    assert "plain" in t.execute()
    assert plain_func.counts() == 3

    async_func.reset()

    t = task(async_func, "Hello, async function", 0.0)
    assert isinstance(t, AwaitTask)
    assert "async" in await t
    assert "async" in await t()
    assert "async" in await t.execute()
    assert async_func.counts() == 3
