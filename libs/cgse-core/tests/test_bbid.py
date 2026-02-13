"""
Unit tests for the observation module building blocks and BBID generation.
"""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from egse.observation import building_block
from egse.observation import end_building_block
from egse.observation import get_bbid_uuid
from egse.observation import start_building_block


def test_building_block_sets_attribute():
    """Test that the decorator sets the __building_block_func attribute."""

    @building_block
    def my_func(x: int) -> int:
        return x * 2

    assert hasattr(my_func, "__building_block_func")
    assert getattr(my_func, "__building_block_func") is True


def test_building_block_preserves_function_name():
    """Test that the decorator preserves the original function name."""

    @building_block
    def my_test_func(x: int) -> int:
        return x

    assert my_test_func.__name__ == "my_test_func"


@patch("egse.observation.ObservationContext")
def test_building_block_executes_function(mock_obs_context):
    """Test that the decorator properly executes the wrapped function."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def add(a: int, b: int) -> int:
        return a + b

    result = add(a=2, b=3)

    assert result == 5

    # Verify that ObservationContext methods were called
    mock_instance.set_bbid.assert_called_once()
    mock_instance.unset_bbid.assert_called_once()


@patch("egse.observation.ObservationContext")
def test_building_block_rejects_positional_arguments(mock_obs_context):
    """Test that the decorator raises ValueError for positional arguments."""

    @building_block
    def my_func(x: int) -> int:
        return x

    with pytest.raises(ValueError, match="can not have positional arguments"):
        my_func(5)


@patch("egse.observation.ObservationContext")
def test_building_block_rejects_missing_kwargs(mock_obs_context):
    """Test that the decorator raises ValueError for missing keyword arguments."""

    @building_block
    def my_func(x: int, y: int) -> int:
        return x + y

    with pytest.raises(ValueError, match="missing arguments"):
        my_func(x=1)  # Missing y


@patch("egse.observation.ObservationContext")
def test_building_block_accepts_all_kwargs(mock_obs_context):
    """Test that the decorator accepts functions with all required kwargs."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def my_func(x: int, y: int) -> int:
        return x + y

    result = my_func(x=1, y=2)

    assert result == 3


@patch("egse.observation.ObservationContext")
def test_building_block_calls_cleanup_on_exception(mock_obs_context):
    """Test that unset_bbid is called even if the function raises an exception."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def failing_func():
        raise RuntimeError("test error")

    with pytest.raises(RuntimeError, match="test error"):
        failing_func()

    # Verify that unset_bbid was still called
    mock_instance.unset_bbid.assert_called_once()


@patch("egse.observation.ObservationContext")
def test_building_block_with_no_parameters(mock_obs_context):
    """Test that the decorator works with functions that have no parameters."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def no_params_func() -> int:
        return 42

    result = no_params_func()

    assert result == 42
    mock_instance.set_bbid.assert_called_once()
    mock_instance.unset_bbid.assert_called_once()


@patch("egse.observation.ObservationContext")
def test_building_block_with_lambda(mock_obs_context):
    """Test that the decorator works with lambda functions."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    decorated_lambda = building_block(lambda x: x * 2)

    result = decorated_lambda(x=5)

    assert result == 10


@patch("egse.observation.ObservationContext")
def test_building_block_function_returning_none(mock_obs_context):
    """Test that building blocks that return None are handled correctly."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def returns_none():
        return None

    result = returns_none()

    assert result is None
    mock_instance.set_bbid.assert_called_once()


@patch("egse.observation.ObservationContext")
def test_building_block_with_multiple_parameters(mock_obs_context):
    """Test building block with various parameter types."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def complex_func(a: int, b: str, c: float) -> str:
        return f"{b}: {a + c}"

    result = complex_func(a=1, b="result", c=2.5)

    assert result == "result: 3.5"
    mock_instance.set_bbid.assert_called_once()
    mock_instance.unset_bbid.assert_called_once()


def test_get_bbid_uuid_uppercase_function_name():
    """Test that the function name is converted to uppercase."""

    @building_block
    def my_test_function():
        pass

    name = get_bbid_uuid(my_test_function)

    assert "MY_TEST_FUNCTION" in name


def test_generate_bbid_correct_prefix():
    """Test that generated BBID starts with BBID prefix."""

    @building_block
    def my_func():
        pass

    bbid = get_bbid_uuid(my_func)

    assert bbid.startswith("BBID")


def test_generate_bbid_correct_length():
    """Test that generated BBID has correct length (BBID + 16 hex chars)."""

    @building_block
    def my_func():
        pass

    bbid = get_bbid_uuid(my_func)

    # BBID prefix (4 chars) + '-' + len("my_func") + '-' + 64 hex chars = 77 chars total
    assert len(bbid) == 77


def test_generate_bbid_is_hex_postfix():
    """Test that the BBID suffix is valid hexadecimal."""

    @building_block
    def my_func():
        pass

    bbid = get_bbid_uuid(my_func)
    hex_part = bbid[13:]  # Remove BBID prefix + '_' + len("my_func") + '_' = 13 chars

    # Should not raise ValueError
    int(hex_part, 16)


def test_generate_bbid_consistent():
    """Test that the same function always generates the same BBID."""

    @building_block
    def test_func():
        pass

    bbid1 = get_bbid_uuid(test_func)
    bbid2 = get_bbid_uuid(test_func)

    assert bbid1 == bbid2


def test_generate_bbid_different_functions():
    """Test that different functions generate different BBIDs."""

    @building_block
    def func1():
        pass

    @building_block
    def func2():
        pass

    bbid1 = get_bbid_uuid(func1)
    bbid2 = get_bbid_uuid(func2)

    assert bbid1 != bbid2


def test_generate_bbid_uppercase():
    """Test that BBID is always uppercase."""

    @building_block
    def my_func():
        pass

    bbid = get_bbid_uuid(my_func)

    assert bbid == bbid.upper()


def test_get_bbid_uuid_raises_error_non_callable():
    """Test that get_bbid_uuid raises ValueError for non-callable."""
    with pytest.raises(ValueError, match="should be a function or method"):
        get_bbid_uuid("not a function")  # type: ignore


def test_get_bbid_uuid_raises_error_none():
    """Test that get_bbid_uuid raises ValueError for None."""
    with pytest.raises(ValueError, match="should be a function or method"):
        get_bbid_uuid(None)  # type: ignore


def test_get_bbid_uuid_raises_error_not_building_block():
    """Test that get_bbid_uuid raises ValueError for functions not defined as building blocks."""

    def regular_function():
        pass

    with pytest.raises(ValueError, match="not defined as a building block"):
        get_bbid_uuid(regular_function)


@patch("egse.observation.ObservationContext")
@patch("egse.observation.get_bbid_uuid")
def test_start_building_block_sets_bbid(mock_get_bbid, mock_obs_context):
    """Test that start_building_block sets the BBID in ObservationContext."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance
    mock_get_bbid.return_value = "BBID1234567890ABCDEF"

    def my_func():
        pass

    start_building_block(my_func)

    mock_instance.set_bbid.assert_called_once_with("BBID1234567890ABCDEF")


@patch("egse.observation.ObservationContext")
@patch("egse.observation.get_bbid_uuid")
def test_start_building_block_returns_bbid(mock_get_bbid, mock_obs_context):
    """Test that start_building_block returns the BBID."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance
    mock_get_bbid.return_value = "BBID_TEST_VALUE"

    def my_func():
        pass

    result = start_building_block(my_func)

    assert result == "BBID_TEST_VALUE"


@patch("egse.observation.ObservationContext")
def test_end_building_block_unsets_bbid(mock_obs_context):
    """Test that end_building_block unsets the BBID in ObservationContext."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    end_building_block()

    mock_instance.unset_bbid.assert_called_once()


@patch("egse.observation.ObservationContext")
def test_full_building_block_lifecycle(mock_obs_context):
    """Test the complete lifecycle of a building block execution."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def process_data(value: int) -> int:
        return value * 2

    result = process_data(value=5)

    # Verify function executed correctly
    assert result == 10

    # Verify ObservationContext was properly managed
    mock_instance.set_bbid.assert_called_once()
    mock_instance.unset_bbid.assert_called_once()


@patch("egse.observation.ObservationContext")
def test_multiple_building_blocks(mock_obs_context):
    """Test using multiple decorated functions."""
    mock_instance = MagicMock()
    mock_obs_context.return_value = mock_instance

    @building_block
    def func1(x: int) -> int:
        return x + 1

    @building_block
    def func2(y: int) -> int:
        return y * 2

    result1 = func1(x=5)
    result2 = func2(y=3)

    assert result1 == 6
    assert result2 == 6

    # Each function call should set and unset BBID
    assert mock_instance.set_bbid.call_count == 2
    assert mock_instance.unset_bbid.call_count == 2
