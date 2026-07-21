"""Unit tests for ThermalVacController._run_scan_loop's retry/backoff behaviour."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from egse.ivs.tvac import tvac_acs
from egse.ivs.tvac.tvac_acs import ThermalVacController


def make_fake_controller():
    """A minimal duck-typed stand-in exposing only what `_run_scan_loop` touches, so the test doesn't
    need to construct a full `ThermalVacController` (which requires a real control server / ZMQ setup).
    """

    fake = MagicMock()
    fake.scan_stop_event = asyncio.Event()
    fake.daq.is_running.return_value = True
    fake.daq.stop_scan = MagicMock()
    fake._cs.logger = MagicMock()
    return fake


@pytest.mark.asyncio
async def test_scan_loop_retries_on_read_failure_instead_of_dying(monkeypatch):
    """A failed `read_buffer_chunk()` must not end the scan: the loop keeps retrying (with backoff) until
    a read succeeds, instead of the previous behaviour of logging one ERROR and returning for good.
    """

    monkeypatch.setattr(tvac_acs, "SAMPLE_INTERVAL", 0.01)
    monkeypatch.setattr(tvac_acs, "SCAN_RETRY_BACKOFF_MAX", 0.02)

    fake = make_fake_controller()
    fake.daq.read_buffer_chunk = AsyncMock(
        side_effect=[ConnectionError("client is disconnected"), ConnectionError("client is disconnected"), {"ok": 1}]
    )

    def stop_after_first_success(*args, **kwargs):
        fake.scan_stop_event.set()

    fake._cs.on_acquisition_data = MagicMock(side_effect=stop_after_first_success)

    await asyncio.wait_for(ThermalVacController._run_scan_loop(fake), timeout=5)

    assert fake.daq.read_buffer_chunk.call_count == 3
    assert fake._cs.logger.error.call_count == 2  # one per failed read
    fake._cs.on_acquisition_data.assert_called_once_with(
        {"ok": 1}, source="tvac-buffer", metadata={"mode": "buffered-scan"}
    )
    fake.daq.stop_scan.assert_called_once()


@pytest.mark.asyncio
async def test_scan_loop_stops_retrying_once_scan_is_stopped(monkeypatch):
    """Setting `scan_stop_event` while the loop is backed off waiting to retry must interrupt that wait
    promptly, rather than blocking for the full backoff duration.
    """

    monkeypatch.setattr(tvac_acs, "SAMPLE_INTERVAL", 0.01)
    monkeypatch.setattr(tvac_acs, "SCAN_RETRY_BACKOFF_MAX", 30.0)  # deliberately large

    fake = make_fake_controller()
    fake.daq.read_buffer_chunk = AsyncMock(side_effect=ConnectionError("client is disconnected"))
    fake._cs.on_acquisition_data = MagicMock()

    async def stop_soon():
        await asyncio.sleep(0.05)
        fake.scan_stop_event.set()

    stopper = asyncio.create_task(stop_soon())

    # If the stop event didn't interrupt the backoff wait, this would block for ~30s and hit the timeout.
    await asyncio.wait_for(ThermalVacController._run_scan_loop(fake), timeout=2)
    await stopper

    fake._cs.on_acquisition_data.assert_not_called()
    fake.daq.stop_scan.assert_called_once()


@pytest.mark.asyncio
async def test_scan_loop_still_ends_on_unexpected_non_read_error(monkeypatch):
    """Errors outside the read path (e.g. a bug in `on_acquisition_data`) are not retried indefinitely —
    the outer safety net still logs and ends the loop, same as before this change.
    """

    monkeypatch.setattr(tvac_acs, "SAMPLE_INTERVAL", 0.01)
    monkeypatch.setattr(tvac_acs, "SCAN_RETRY_BACKOFF_MAX", 0.02)

    fake = make_fake_controller()
    fake.daq.read_buffer_chunk = AsyncMock(return_value={"ok": 1})
    fake._cs.on_acquisition_data = MagicMock(side_effect=RuntimeError("bug, not a connectivity issue"))

    await asyncio.wait_for(ThermalVacController._run_scan_loop(fake), timeout=5)

    fake.daq.read_buffer_chunk.assert_called_once()
    fake._cs.logger.error.assert_called_once()
    assert "Buffered scan loop failed" in fake._cs.logger.error.call_args.args[0]
    fake.daq.stop_scan.assert_called_once()
