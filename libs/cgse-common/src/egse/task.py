# ACKNOWLEDGEMENT: These functions are based on work done by Will McGugan on Textual.
#                  check out: https://textual.textualize.io/blog/2023/03/15/no-async-async-with-python/

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from typing import Callable
from typing import Coroutine
from typing import Generator


def task(todo: Callable, *args, **kwargs) -> AwaitTask:
    """
    The function task can be called in a normal way, or it can be called asynchronously.

    The idea behind this is to provide functions (or tasks) that can be called both
    in a synchronous (a REPL) and asynchronous environment (an async def). The function
    that is passed into `task()` can be a plain old Python function (def) or an
    asynchronous function (async def). Only for async functions you will need to await
    the function call (execution of the task).

    Example:
        def foo(a, b, s):
           ...

        async def bar(a, b, c):
            ...

        t = task(foo, 1, 2, 3)
        result = t()

        t = task(bar, 1, 2, 3)
        result = [await] t()  # await only needed in asynchronous environment

    """
    return AwaitTask(Task(todo, *args, **kwargs))


class Task:
    """
    A Task is a wrapper around a function with arguments and keyword arguments that
    can be either a plain old Python function or an asynchronous function (async def).

    Calling the task will always return the result except when running in an asynchronous
    environment where the event loop is running. Then a coroutine will be returned that
    needs to be awaited.
    """

    def __init__(self, task: Callable, *args, **kwargs):
        self._task = task
        self._args = args
        self._kwargs = kwargs
        self._finish_event = asyncio.Event()

    def __call__(self):
        result = self._task(*self._args, **self._kwargs)

        if inspect.isawaitable(result):
            event_loop = asyncio.get_event_loop()
            if event_loop.is_running():
                return result
            else:
                result = event_loop.run_until_complete(result)

        self._finish_event.set()
        return result


class AwaitTask:
    """
    An *optional* awaitable returned by task.
    """

    def __init__(self, task: Task) -> None:
        self.task = task

    def execute(self) -> Any | Coroutine:
        return self.task()

    def __call__(self) -> Any | Coroutine:
        return self.task()

    def __await__(self) -> Generator[None, None, Any]:
        async def await_task():
            await asyncio.sleep(0.01)
            result = self.task()
            if inspect.isawaitable(result):
                result = await result
            return result

        return await_task().__await__()
