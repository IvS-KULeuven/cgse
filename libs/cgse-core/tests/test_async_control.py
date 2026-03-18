import asyncio
from typing import Any
from typing import cast

try:
    from typing import override
except ImportError:
    try:
        from typing_extensions import override
    except ImportError:

        def override(method, /):
            return method


import pytest
from fixtures.helpers import capture_log_records

from egse.async_control import AcquisitionAsyncControlServer
from egse.async_control import AsyncControlClient
from egse.async_control import AsyncControlServer
from egse.async_control import InitializationError
from egse.async_control import is_control_server_active
from egse.async_dummy import DummyAsyncControlClient
from egse.async_dummy import DummyAsyncControlServer
from egse.log import logging
from egse.logger import remote_logging
from egse.system import type_name

# pytestmark = pytest.mark.skip("Implementation and tests are still a WIP")

logger = logging.getLogger("egse.tests.async_control")


class RecordingAsyncControlServer(AcquisitionAsyncControlServer):
    """Test helper server that records acquisition flow for assertions."""

    def __init__(self):
        """Initialize in-memory buffers used by acquisition tests."""
        super().__init__()
        self.processed_records: list[dict[str, Any]] = []
        self.processed_batches: list[list[dict[str, Any]]] = []
        self.processed_event = asyncio.Event()
        self.expected_records = 0

    @override
    async def handle_acquisition_batch(self, records: list[dict[str, Any]]):
        """Capture batch boundaries before delegating to per-record processing."""
        self.processed_batches.append(records.copy())
        await super().handle_acquisition_batch(records)

    @override
    async def handle_acquisition_record(self, record: dict[str, Any]):
        """Capture records and signal when the expected test count is reached."""
        self.processed_records.append(record)
        if len(self.processed_records) >= self.expected_records:
            self.processed_event.set()


class SequentialExecutionTestServer(AsyncControlServer):
    """Test helper server exposing sequential execution behavior."""

    def __init__(self):
        super().__init__()
        self.execution_order: list[int] = []

    async def append_after(self, token: int, delay: float):
        await asyncio.sleep(delay)
        self.execution_order.append(token)
        return token


@pytest.mark.asyncio
async def test_control_server(caplog):
    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    await asyncio.sleep(0.5)  # give the server time to startup

    try:
        # Now create a control client that will connect to the above server.
        async with AsyncControlClient(service_type="async-control-server") as client:
            caplog.clear()

            # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
            await asyncio.sleep(5.0)

            assert "Sending status updates" in caplog.text  # this should there be 5 times actually

            response = await client.ping()
            logger.debug(f"{response = }")
            assert isinstance(response, str)
            assert response == "pong"

            response = await client.info()
            logger.debug(f"{response = }")
            assert isinstance(response, dict)
            assert "name" in response
            assert "hostname" in response
            assert "device commanding port" in response
            assert "service commanding port" in response

            assert await is_control_server_active(service_type="async-control-server")

            response = await client.stop_server()
            logger.debug(f"{response = }")
            assert isinstance(response, dict)
            assert response["status"] == "terminating"

            assert await is_control_server_active(service_type="async-control-server")
    except InitializationError as exc:
        logger.error(f"Could not create AsyncControlClient: {type_name(exc)}: {exc}")

    server_task.cancel()
    await server_task

    assert not await is_control_server_active(service_type="async-control-server")


@pytest.mark.asyncio
async def test_dummy_control_server():
    """Test DummyAsyncControlServer as an implementation example."""

    with remote_logging():
        server = DummyAsyncControlServer()
        server_task = asyncio.create_task(server.start())

        await asyncio.sleep(0.5)  # give the server time to startup

        # Now create a control client that will connect to the above server.
        async with DummyAsyncControlClient() as client:
            response = await client.ping()
            logger.debug(f"{response = }")
            assert isinstance(response, str)
            assert response == "pong"

            response = await client.echo("dummy")
            logger.debug(f"{response = }")
            assert response == "dummy"

            response = await client.set_value("configured")
            logger.debug(f"{response = }")
            assert response == "configured"

            info_response = await client.info()
            logger.debug(f"{info_response = }")
            assert isinstance(info_response, dict)
            info_response = cast(dict[str, object], info_response)
            assert "name" in info_response
            assert "hostname" in info_response
            assert "device commanding port" in info_response
            assert "service commanding port" in info_response
            assert info_response["service type"] == DummyAsyncControlServer.service_type
            assert info_response["echo count"] == 1
            assert info_response["last value"] == "configured"

            health_response = await client.health()
            logger.debug(f"{health_response = }")
            assert isinstance(health_response, dict)
            assert health_response["status"] == "ok"
            assert health_response["echo count"] == 1
            assert health_response["last value"] == "configured"

            start_response = await client.start_acquisition(interval=0.02)
            logger.debug(f"{start_response = }")
            assert isinstance(start_response, dict)
            assert start_response["running"] is True

            await asyncio.sleep(1.5)  # this should allow for ~75 records to be acquired at 20ms intervals

            stop_response = await client.stop_acquisition()
            logger.debug(f"{stop_response = }")
            assert isinstance(stop_response, dict)
            assert stop_response["running"] is False
            assert int(stop_response["acquisition logged"]) > 0

            health_response = await client.health()
            logger.debug(f"{health_response = }")
            assert isinstance(health_response, dict)
            assert health_response["acquisition running"] is False
            assert int(health_response["acquisition logged"]) > 0

        server_task.cancel()
        await server_task


@pytest.mark.asyncio
async def test_acquisition_callback_from_thread_is_processed_in_order():
    server = RecordingAsyncControlServer()
    server.expected_records = 3
    server._loop = asyncio.get_running_loop()

    processing_task = asyncio.create_task(server.process_acquisition_data())

    try:
        callback = cast(Any, server.get_acquisition_callback())

        await asyncio.to_thread(callback, {"value": 1}, source="sensor-a", metadata={"index": 1})
        await asyncio.to_thread(callback, {"value": 2}, source="sensor-a", metadata={"index": 2})
        await asyncio.to_thread(callback, {"value": 3}, source="sensor-a", metadata={"index": 3})

        await asyncio.wait_for(server.processed_event.wait(), timeout=1.0)

        assert [record["data"]["value"] for record in server.processed_records] == [1, 2, 3]
        assert [record["metadata"]["index"] for record in server.processed_records] == [1, 2, 3]
        assert all(record["source"] == "sensor-a" for record in server.processed_records)
        assert server.acquisition_dropped_count == 0
        assert len(server.processed_batches) == 3
        assert all(len(batch) == 1 for batch in server.processed_batches)
    finally:
        server.stop()
        processing_task.cancel()
        await asyncio.gather(processing_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_acquisition_callback_same_thread_defaults_to_single_record_processing():
    server = RecordingAsyncControlServer()
    server.expected_records = 3
    server._loop = asyncio.get_running_loop()

    processing_task = asyncio.create_task(server.process_acquisition_data())

    try:
        callback = cast(Any, server.get_acquisition_callback())

        callback("first", source="sensor-local", metadata={"index": 1})
        callback("second", source="sensor-local", metadata={"index": 2})
        callback("third", source="sensor-local", metadata={"index": 3})

        await asyncio.wait_for(server.processed_event.wait(), timeout=1.0)

        assert [record["data"] for record in server.processed_records] == ["first", "second", "third"]
        assert [record["metadata"]["index"] for record in server.processed_records] == [1, 2, 3]
        assert all(record["source"] == "sensor-local" for record in server.processed_records)
        assert server.acquisition_batch_enabled is False
        assert len(server.processed_batches) == 3
        assert all(len(batch) == 1 for batch in server.processed_batches)
    finally:
        server.stop()
        processing_task.cancel()
        await asyncio.gather(processing_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_acquisition_batching_is_optional_and_preserves_order():
    server = RecordingAsyncControlServer()
    server.expected_records = 3
    server.acquisition_batch_enabled = True
    server.acquisition_batch_max_size = 10
    server.acquisition_batch_max_wait_s = 0.2
    server._loop = asyncio.get_running_loop()

    processing_task = asyncio.create_task(server.process_acquisition_data())

    try:
        callback = cast(Any, server.get_acquisition_callback())

        callback("first", source="sensor-b", metadata={"index": 1})
        callback("second", source="sensor-b", metadata={"index": 2})
        callback("third", source="sensor-b", metadata={"index": 3})

        await asyncio.wait_for(server.processed_event.wait(), timeout=1.0)

        assert [record["data"] for record in server.processed_records] == ["first", "second", "third"]
        assert [record["metadata"]["index"] for record in server.processed_records] == [1, 2, 3]
        assert len(server.processed_batches) >= 1
        assert [record["data"] for record in server.processed_batches[0]] == ["first", "second", "third"]
    finally:
        server.stop()
        processing_task.cancel()
        await asyncio.gather(processing_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_acquisition_queue_overflow_increments_drop_count():
    server = RecordingAsyncControlServer()
    server._loop = asyncio.get_running_loop()
    server._acquisition_queue = asyncio.Queue(maxsize=2)

    callback = cast(Any, server.get_acquisition_callback())

    callback("first", source="sensor-overflow")
    callback("second", source="sensor-overflow")
    callback("third", source="sensor-overflow")

    await asyncio.sleep(0)

    assert server._acquisition_queue.qsize() == 2
    assert server.acquisition_dropped_count == 1


@pytest.mark.asyncio
async def test_execute_sequential_serializes_concurrent_submissions_in_enqueue_order():
    server = SequentialExecutionTestServer()
    queue_task = asyncio.create_task(server.process_sequential_queue())

    try:
        tasks = [
            asyncio.create_task(server._execute_sequential(server.append_after(1, 0.03))),
            asyncio.create_task(server._execute_sequential(server.append_after(2, 0.01))),
            asyncio.create_task(server._execute_sequential(server.append_after(3, 0.0))),
        ]

        results = await asyncio.gather(*tasks)

        assert results == [1, 2, 3]
        assert server.execution_order == [1, 2, 3]
    finally:
        server.stop()
        queue_task.cancel()
        await asyncio.gather(queue_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_execute_sequential_propagates_operation_exceptions():
    server = SequentialExecutionTestServer()
    queue_task = asyncio.create_task(server.process_sequential_queue())

    async def failing_operation():
        raise RuntimeError("boom")

    try:
        with pytest.raises(RuntimeError, match="boom"):
            await server._execute_sequential(failing_operation())
    finally:
        server.stop()
        queue_task.cancel()
        await asyncio.gather(queue_task, return_exceptions=True)


if __name__ == "__main__":
    with capture_log_records("egse") as caplog:
        asyncio.run(test_control_server(caplog=caplog))
