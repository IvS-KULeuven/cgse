"""
This module implements a random walk that can be used in simulators for devices like temperature sensors or power meter.
"""

from __future__ import annotations

import random
import sys
from typing import Optional


# Re-implement based on:
#
# 1. https://isquared.digital/blog/2020-04-12-random-walk/
# 2. https://isquared.digital/blog/2020-04-16-brownian-motion/
# 3. https://isquared.digital/blog/2020-05-01-drifted-brownian-motion/


class RandomWalk:
    """
    This class implements a random walk.

    The RandomWalk is an iterator which can be used in a for loop:

    ```Python
    import matplotlib.pyplot as plt
    values = [value for value in RandomWalk(start=15.0, boundary=(-100, 25), scale=0.01, count=10000)]
    plt.plot(values)
    plt.show()
    ```

    The code above will create a plot like below, where 10000 values are plot in a random walk between -100 and 25,
    starting at 15:

    ![Random Walk example](../../img/screenshot-randomwalk.png)

    When you need a random walk that will return values infinitely, set count = 0.

    By default, the returned values will represent a random walk between -1.0 and 1.0 in a step of 1.0.
    """

    def __init__(
        self,
        start: float = 0.0,
        boundary: tuple = (-1.0, 1.0),
        threshold: tuple | float = 0.5,
        scale: float = 1.0,
        count: int = 1000,
        seed: Optional[int] = None,
    ):
        """

        Args:
            start: the start value for the random walk [default = 0.0]
            boundary: the lower and upper boundaries [default = (-1.0, 1.0)]
            threshold: the probability to move up or down [default = 0.5]
            scale: scale the step size [default = 1.0]
            count: the number of iterations, when <= 0 count will be basically infinite [default = 1000]
            seed: seed for the initialization of the random generator [default = None]
        """
        self._threshold_up = threshold[1] if isinstance(threshold, tuple) else threshold
        self._threshold_down = threshold[0] if isinstance(threshold, tuple) else threshold
        self._boundary = boundary
        self._min_value, self._max_value = boundary
        self._count = count if count > 0 else sys.maxsize
        self._start = start
        self._last = start
        self._scale = scale
        self._seed = seed
        self._random = random.Random()

        if seed is not None:
            self._random.seed(seed)

    def __iter__(self):
        return self

    def __next__(self):
        if self._count > 0:
            probability = self._random.random()
            if probability > self._threshold_up:
                distance_to_limit = self._max_value - self._last
                step = self._random.uniform(0.0, distance_to_limit / 10)
                value = self._last + self._scale * step
                value = min(value, self._max_value)
            elif probability < self._threshold_down:
                distance_to_limit = self._last - self._min_value
                step = self._random.uniform(0.0, distance_to_limit / 10)
                value = self._last - self._scale * step
                value = max(value, self._min_value)
            else:
                value = self._last
            self._last = value
            self._count -= 1
            return value
        raise StopIteration

    def x__next__(self):
        if self._count > 0:
            probability = self._random.random()
            if probability > self._threshold_up:
                value = self._last + self._scale
                value = min(value, self._max_value)
            elif probability < self._threshold_down:
                value = self._last - self._scale
                value = max(value, self._min_value)
            else:
                value = self._last
            self._last = value
            self._count -= 1
            return value
        raise StopIteration


if __name__ == "__main__":
    # https://towardsdatascience.com/generating-synthetic-time-series-data-with-random-walks-8701bb9a56a8

    import matplotlib.pyplot as plt

    # Random Walk, each time a different seed by default

    y1 = RandomWalk(start=50.0, boundary=(0, 100), threshold=0.50, scale=0.5, count=1_000_000)
    # y1 = RandomWalk(start=50.0, boundary=(0, 100), threshold=(0.25, 0.70), scale=1, count=10_000)
    # y2 = RandomWalk(start=50.0, boundary=(0, 100), threshold=0.49, scale=0.05, count=100000, seed=0)
    # y3 = RandomWalk(start=50.0, boundary=(0, 100), threshold=0.48, scale=0.01, count=100000, seed=0)
    # plt.plot(list(zip(y1, y2, y3)))
    plt.plot(list(y1))
    plt.show()

    y1 = RandomWalk(start=50.0, boundary=(0, 100), threshold=0.5, scale=0.2, count=100000, seed=0)
    y2 = RandomWalk(start=50.0, boundary=(0, 100), threshold=0.51, scale=0.2, count=100000, seed=0)
    y3 = RandomWalk(start=50.0, boundary=(0, 100), threshold=0.52, scale=0.2, count=100000, seed=0)
    plt.plot(list(zip(y1, y2, y3)))
    plt.show()

    y1 = RandomWalk(start=75.0, boundary=(0, 100), threshold=0.5, scale=0.2, count=100000, seed=0)
    y2 = RandomWalk(start=50.0, boundary=(0, 100), threshold=0.5, scale=0.2, count=100000, seed=0)
    y3 = RandomWalk(start=25.0, boundary=(0, 100), threshold=0.5, scale=0.2, count=100000, seed=0)
    plt.plot(list(zip(y1, y2, y3)))
    plt.show()

    rng0 = RandomWalk(start=15.0, boundary=(-20, 25), scale=1.0, count=1000, seed=1)
    rng1 = RandomWalk(start=15.0, boundary=(-20, 25), scale=0.8, count=1000, seed=10)
    rng2 = RandomWalk(start=15.0, boundary=(-20, 25), scale=0.5, count=1000, seed=100)
    rng3 = RandomWalk(start=15.0, boundary=(-20, 25), scale=0.3, count=1000, seed=1000)

    values = list(zip(rng0, rng1, rng2, rng3))
    plt.plot(values)
    plt.ylim(-20, 25)
    plt.show()

    # Example 1:

    rw = RandomWalk(start=25.0, boundary=(-100, 100), scale=0.2, count=0, seed=42)
    values = [next(rw) for _ in range(1000000)]
    plt.plot(values)
    plt.show()

    # Example 2: should give the same output as example 1

    plt.plot(
        list(
            RandomWalk(
                start=25.0,
                boundary=(-100, 100),
                scale=0.2,
                count=1000000,
                seed=42,
            )
        )
    )
    plt.show()

    # Example 3:

    for i, value in enumerate(RandomWalk(start=25.0, boundary=(-100, 100), threshold=0.5, scale=2, count=20)):
        print(f"{i}, {value}")
