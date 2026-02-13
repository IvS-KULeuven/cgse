"""Unit tests for observation.py using function-style pytest tests."""

from collections import deque
from unittest.mock import patch

import pytest

from egse.observation import ObservationContext
from egse.observation import building_block
from egse.observation import end_observation
from egse.observation import execute
from egse.observation import request_obsid
from egse.observation import start_observation
from egse.observation import stringify_args
from egse.observation import stringify_kwargs
from egse.response import Failure
from egse.response import Success


@pytest.fixture
def obs_context():
    ctx = ObservationContext()
    ctx.level = -1
    ctx.bbid_count = 0
    ctx.bbids = deque()
    return ctx


def test_set_bbid_requires_observation_context(obs_context):
    with pytest.raises(RuntimeError, match="outside the scope of an observation"):
        obs_context.set_bbid("BBID-TEST")


def test_set_bbid_rejects_duplicates(obs_context):
    obs_context.level = 0
    obs_context.set_bbid("BBID-TEST")

    with pytest.raises(ValueError, match="already in execution"):
        obs_context.set_bbid("BBID-TEST")


def test_set_and_unset_bbid_updates_state(obs_context):
    obs_context.level = 0

    obs_context.set_bbid("BBID-TEST")
    assert obs_context.get_current_bbid() == "BBID-TEST"
    assert obs_context.get_level() == 1
    assert obs_context.bbid_count == 1

    obs_context.unset_bbid()
    assert obs_context.get_level() == 0
    assert list(obs_context.bbids) == []


def test_get_current_bbid_returns_latest(obs_context):
    obs_context.level = 0
    obs_context.set_bbid("BBID-1")
    obs_context.set_bbid("BBID-2")

    assert obs_context.get_current_bbid() == "BBID-2"


@patch("egse.observation.ConfigurationManagerProxy")
def test_start_observation_success(mock_cm, obs_context):
    mock_cm.return_value.__enter__.return_value.start_observation.return_value = Success("ok", 123)

    rc = obs_context.start_observation({"description": "test"})

    assert rc == 123
    assert obs_context.get_level() == 0


def test_start_observation_rejects_when_active(obs_context):
    obs_context.level = 0

    with pytest.raises(Failure, match="Only one Observation can be active"):
        obs_context.start_observation({"description": "test"})


@patch("egse.observation.ConfigurationManagerProxy")
def test_start_observation_failure_resets_level(mock_cm, obs_context):
    mock_cm.return_value.__enter__.return_value.start_observation.return_value = Failure("nope")

    with pytest.raises(Failure, match="nope"):
        obs_context.start_observation({"description": "test"})

    assert obs_context.get_level() == -1


@patch("egse.observation.ConfigurationManagerProxy")
def test_start_observation_connection_error(mock_cm, obs_context):
    mock_cm.return_value.__enter__.return_value.start_observation.side_effect = ConnectionError("boom")

    with pytest.raises(Failure, match="Couldn't connect"):
        obs_context.start_observation({"description": "test"})

    assert obs_context.get_level() == -1


@patch("egse.observation.ConfigurationManagerProxy")
def test_end_observation_success_resets_state(mock_cm, obs_context):
    obs_context.level = 1
    obs_context.bbid_count = 2
    obs_context.bbids.extend(["BBID-1", "BBID-2"])

    mock_cm.return_value.__enter__.return_value.end_observation.return_value = Success("ok")

    obs_context.end_observation()

    assert obs_context.get_level() == -1
    assert obs_context.bbid_count == 0
    assert list(obs_context.bbids) == []


@patch("egse.observation.ConfigurationManagerProxy")
def test_end_observation_failure_raises(mock_cm, obs_context):
    mock_cm.return_value.__enter__.return_value.end_observation.return_value = Failure("fail")

    with pytest.raises(Failure, match="fail"):
        obs_context.end_observation()


@patch("egse.observation.ConfigurationManagerProxy")
def test_request_obsid_returns_value(mock_cm):
    mock_cm.return_value.__enter__.return_value.get_obsid.return_value = Success("ok", 456)

    assert request_obsid() == 456


@patch("egse.observation.ConfigurationManagerProxy")
def test_request_obsid_raises_failure(mock_cm):
    mock_cm.return_value.__enter__.return_value.get_obsid.return_value = Failure("bad")

    with pytest.raises(Failure, match="bad"):
        request_obsid()


def test_stringify_args_handles_objects():
    class Sample:
        pass

    obj = Sample()
    args = stringify_args([obj, 42])

    assert args[0].endswith(".Sample")
    assert args[1] == "42"


def test_stringify_kwargs_handles_objects():
    class Sample:
        pass

    obj = Sample()
    kwargs = stringify_kwargs({"a": obj, "b": 7})

    assert kwargs["a"].endswith(".Sample")
    assert kwargs["b"] == "7"


@patch("egse.observation.request_obsid", return_value=111)
@patch("egse.observation.ConfigurationManagerProxy")
@patch("egse.observation.ObservationContext")
def test_execute_runs_building_block(mock_obs_ctx, mock_cm, mock_obsid):
    mock_cm.return_value.__enter__.return_value.start_observation.return_value = Success("ok", 123)
    mock_obs_ctx.level = 1

    @building_block
    def bb_func(x: int = 0) -> int:
        return x * 2

    result = execute(bb_func, "desc", x=3)
    assert result == 6


@patch("egse.observation.ObservationContext")
def test_execute_runs_building_block_missing_kwargs(mock_obs_ctx):
    with pytest.raises(ValueError, match="Expected 2 keyword parameters"):

        @building_block
        def bb(x: int = 1, y: int = 2) -> int:
            return x * y

        # This should fail since all kwargs are mandatory for the building block
        _ = execute(bb, "desc")

    end_observation()


@patch("egse.observation.request_obsid", return_value=111)
@patch("egse.observation.ObservationContext.end_observation")
@patch("egse.observation.ObservationContext.start_observation")
@patch("egse.observation.logger.warning")
def test_execute_runs_function_and_warns_when_not_building_block(
    mock_warn,
    mock_start,
    mock_end,
    mock_obsid,
):
    def plain_func(x):
        return x + 1

    result = execute(plain_func, "desc", 1)

    assert result == 2
    mock_warn.assert_called_once()
    mock_end.assert_called_once()


@patch("egse.observation.request_obsid", return_value=111)
@patch("egse.observation.ObservationContext.end_observation")
@patch("egse.observation.ObservationContext.start_observation")
def test_execute_calls_end_observation_on_exception(mock_start, mock_end, mock_obsid):
    def failing_func():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        execute(failing_func, "desc")

    mock_end.assert_called_once()


@patch("egse.observation.request_obsid", return_value=999)
@patch("egse.observation.ObservationContext.start_observation")
def test_start_observation_wrapper_returns_obsid(mock_start, mock_obsid):
    assert start_observation("testing") == 999


@patch("egse.observation.logger.error")
@patch("egse.observation.ObservationContext.start_observation")
def test_start_observation_wrapper_logs_and_raises(mock_start, mock_error):
    mock_start.side_effect = Failure("bad")

    with pytest.raises(Failure, match="bad"):
        start_observation("testing")

    mock_error.assert_called_once()


@patch("egse.observation.ObservationContext.end_observation")
def test_end_observation_wrapper_calls_context(mock_end):
    end_observation()
    mock_end.assert_called_once()
