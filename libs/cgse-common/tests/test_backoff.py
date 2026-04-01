from contextlib import nullcontext

import pytest

from egse.backoff import BackoffStrategy
from egse.backoff import JitterStrategy
from egse.backoff import calculate_retry_interval


@pytest.mark.parametrize(
    "attempt_number,base_interval,max_interval,expected",
    [
        (-1, 0, 0, pytest.raises(ValueError, match="attempt_number shall be a non-negative integer")),
        (0, 1.0, 10.0, nullcontext(1.0)),
        (1, 1.0, 10.0, nullcontext(2.0)),
        (2, 1.0, 10.0, nullcontext(4.0)),
        (3, 1.0, 10.0, nullcontext(8.0)),
        (4, 1.0, 10.0, nullcontext(10.0)),
        (10, 1.0, 10.0, nullcontext(10.0)),
        (11, 1.0, 10.0, nullcontext(10.0)),
    ],
)
def test_calculate_retry_interval_exponential_without_jitter(attempt_number, base_interval, max_interval, expected):

    with expected as expected_interval:
        interval = calculate_retry_interval(
            attempt_number=attempt_number,
            base_interval=base_interval,
            max_interval=max_interval,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_strategy=JitterStrategy.NONE,
        )

        assert interval == expected_interval


def test_calculate_retry_interval_exponential_with_custom_factor():
    interval = calculate_retry_interval(
        attempt_number=3,
        base_interval=0.5,
        max_interval=10.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        jitter_strategy=JitterStrategy.NONE,
        exponential_factor=1.5,
    )

    assert interval == pytest.approx(1.6875)


@pytest.mark.parametrize(
    "attempt_number,base_interval,max_interval,expected",
    [
        (-1, 0, 0, pytest.raises(ValueError, match="attempt_number shall be a non-negative integer")),
        (0, 1.0, 10.0, nullcontext(1.0)),
        (1, 1.0, 10.0, nullcontext(2.0)),
        (2, 1.0, 10.0, nullcontext(3.0)),
        (10, 1.0, 10.0, nullcontext(10.0)),
        (11, 1.0, 10.0, nullcontext(10.0)),
    ],
)
def test_calculate_retry_interval_linear_without_jitter(attempt_number, base_interval, max_interval, expected):

    with expected as expected_interval:
        interval = calculate_retry_interval(
            attempt_number=attempt_number,
            base_interval=base_interval,
            max_interval=max_interval,
            backoff_strategy=BackoffStrategy.LINEAR,
            jitter_strategy=JitterStrategy.NONE,
        )
        print(f"Calculated interval: {interval}, Expected interval: {expected_interval}")
        assert interval == expected_interval


def test_calculate_retry_interval_fixed_without_jitter():
    interval = calculate_retry_interval(
        attempt_number=9,
        base_interval=0.5,
        max_interval=10.0,
        backoff_strategy=BackoffStrategy.FIXED,
        jitter_strategy=JitterStrategy.NONE,
    )

    assert interval == 0.5


def test_calculate_retry_interval_caps_at_max_interval():
    interval = calculate_retry_interval(
        attempt_number=8,
        base_interval=1.0,
        max_interval=5.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        jitter_strategy=JitterStrategy.NONE,
    )

    assert interval == 5.0


def test_calculate_retry_interval_equal_jitter_uses_upper_half(monkeypatch):
    monkeypatch.setattr("egse.backoff.random.uniform", lambda low, high: high)

    interval = calculate_retry_interval(
        attempt_number=2,
        base_interval=1.0,
        max_interval=10.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        jitter_strategy=JitterStrategy.EQUAL,
    )

    assert interval == 4.0


def test_calculate_retry_interval_percent10_jitter_boundaries(monkeypatch):
    monkeypatch.setattr("egse.backoff.random.uniform", lambda low, high: low)

    interval = calculate_retry_interval(
        attempt_number=2,
        base_interval=1.0,
        max_interval=10.0,
        backoff_strategy=BackoffStrategy.EXPONENTIAL,
        jitter_strategy=JitterStrategy.PERCENT_10,
    )

    assert interval == pytest.approx(3.6)


def test_calculate_retry_interval_rejects_non_positive_exponential_factor():
    with pytest.raises(ValueError, match="exponential_factor"):
        calculate_retry_interval(
            attempt_number=1,
            base_interval=1.0,
            max_interval=5.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            jitter_strategy=JitterStrategy.NONE,
            exponential_factor=0.0,
        )
