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
    """Calculate the next retry interval using backoff and optional jitter.

    Note: The first retry attempt is considered attempt_number=0, which will yield a delay equal to the base_interval
    for all backoff strategies.

    Args:
        attempt_number: The number of the current retry attempt (0-based).
        base_interval: The base interval in seconds for the first retry attempt.
        max_interval: The maximum interval in seconds to cap the retry delay.
        backoff_strategy: The strategy to use for calculating the backoff delay.
        jitter_strategy: The strategy to use for adding jitter to the delay.
        exponential_factor: The factor by which to multiply the base interval for each attempt when using
            exponential backoff.

    Returns:
        The calculated retry interval in seconds, after applying backoff and jitter.

    Raises:
        ValueError: If attempt_number is negative or if exponential_factor is not greater than 0.

    """

    if attempt_number < 0:
        raise ValueError("attempt_number shall be a non-negative integer")

    bounded_base = max(0.0, base_interval)

    # The maximum interval should be at least as large as the base interval to ensure that the backoff strategy
    # can function properly. If the max_interval is smaller than the base_interval, we will use the base_interval as
    # the effective maximum to prevent invalid intervals.
    bounded_max = max(bounded_base, max_interval)

    if backoff_strategy == BackoffStrategy.EXPONENTIAL:
        if exponential_factor <= 0.0:
            raise ValueError("exponential_factor must be > 0")
        interval = min(bounded_base * (exponential_factor**attempt_number), bounded_max)
    elif backoff_strategy == BackoffStrategy.LINEAR:
        interval = min(bounded_base * (attempt_number + 1), bounded_max)
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
