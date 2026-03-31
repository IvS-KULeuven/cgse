"""Shared backoff and jitter strategies used for retry logic."""

import random
from enum import Enum


class BackoffStrategy(Enum):
    """Strategy for increasing delay between retry attempts."""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


class JitterStrategy(Enum):
    """Strategy for adding randomization to retry delays."""

    NONE = "none"
    FULL = "full"
    EQUAL = "equal"
    PERCENT_10 = "10%"


def calculate_retry_interval(
    attempt_number: int,
    base_interval: float,
    max_interval: float,
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
    jitter_strategy: JitterStrategy = JitterStrategy.EQUAL,
    exponential_factor: float = 2.0,
) -> float:
    """Calculate the next retry interval using backoff and optional jitter."""

    bounded_base = max(0.0, base_interval)
    bounded_max = max(0.0, max_interval)

    if backoff_strategy == BackoffStrategy.EXPONENTIAL:
        if exponential_factor <= 0.0:
            raise ValueError("exponential_factor must be > 0")
        interval = min(bounded_base * (exponential_factor**attempt_number), bounded_max)
    elif backoff_strategy == BackoffStrategy.LINEAR:
        interval = min(bounded_base + attempt_number, bounded_max)
    else:
        interval = min(bounded_base, bounded_max)

    if jitter_strategy == JitterStrategy.NONE:
        return interval
    if jitter_strategy == JitterStrategy.FULL:
        return random.uniform(0.0, interval)
    if jitter_strategy == JitterStrategy.EQUAL:
        return interval / 2 + random.uniform(0.0, interval / 2)
    if jitter_strategy == JitterStrategy.PERCENT_10:
        jitter_amount = interval * 0.1
        return interval + random.uniform(-jitter_amount, jitter_amount)

    return interval
