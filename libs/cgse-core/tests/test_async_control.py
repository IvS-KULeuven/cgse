import asyncio
import inspect
import textwrap
from typing import Any
from typing import cast

try:
    from typing import override  # type: ignore
except ImportError:
    from typing_extensions import override


import pytest
from egse.log import logging
from egse.system import type_name

from egse.async_control import CONTROL_SERVER_SERVICE_TYPE
from egse.async_control import AcquisitionAsyncControlServer
from egse.async_control import AsyncControlClient
from egse.async_control import AsyncControlServer
from egse.async_control import InitializationError
from egse.async_control import is_control_server_active
from egse.async_dummy import DummyAsyncControlClient
from egse.async_dummy import DummyAsyncControlServer
from egse.logger import remote_logging

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
        async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
            caplog.clear()

            # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
            await asyncio.sleep(5.0)

            # These logging messages are send by the control server, so if they are in the logs,
            # it means the server is running and sending status updates as expected.
            # Note that the messages are sent every second, so in 5 seconds we should see 5 of them.
            # We check for at least one occurrence to avoid flaky test failures due to timing issues,
            # but in practice there should be 5 of them.
            # Its important to note the log level is set to INFO in the control server, so if the
            # test logs are configured to show INFO level logs, we should see these messages.
            # If the test logs are configured to show only WARNING or higher level logs,
            # we won't see these messages and the assertion will fail.
            # So make sure the test logging configuration includes INFO level logs for this assertion
            # to work as intended.
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

            assert await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)

            response = await client.stop_server()
            logger.debug(f"{response = }")
            assert isinstance(response, dict)
            assert response["status"] == "terminating"

            await asyncio.sleep(0.5)  # give the server time to shutdown

            assert not await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)

    except InitializationError as exc:
        logger.error(f"Could not create AsyncControlClient: {type_name(exc)}: {exc}")

    server_task.cancel()
    await server_task

    assert not await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)


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
async def test_invalid_client_device_commands():
    """Test that invalid commands are handled gracefully by the control server."""
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    await asyncio.sleep(0.5)  # give the server time to startup

    try:
        async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
            response = await client.do("non_existent_string_command")
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "Unknown command: non_existent_string_command"

            response = await client.do({"command": "non_existent_command"})
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "Unknown command: non_existent_command"

            response = await client.do({"command": ""})
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "no command field provided, don't know what to do."

            response = await client.do({})
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "no command field provided, don't know what to do."

            response = await client.do(None)  # type: ignore
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert (
                response.get("message", "")
                == "request argument shall be a string or a dictionary, not <class 'NoneType'>."
            )
    finally:
        server_task.cancel()
        await server_task


@pytest.mark.asyncio
async def test_invalid_client_service_commands():
    """Test that invalid commands are handled gracefully by the control server."""
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    await asyncio.sleep(0.5)  # give the server time to startup

    try:
        async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
            response = await client.handle("non_existent_string_command")
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "Unknown command: non_existent_string_command"

            response = await client.handle({"command": "non_existent_command"})
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "Unknown command: non_existent_command"

            response = await client.handle({"command": ""})
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "no command field provided, don't know what to do."

            response = await client.handle({})
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert response.get("message", "") == "no command field provided, don't know what to do."

            response = await client.handle(None)  # type: ignore
            assert isinstance(response, dict)
            assert response.get("success") is False
            assert (
                response.get("message", "")
                == "request argument shall be a string or a dictionary, not <class 'NoneType'>."
            )
    finally:
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


async def cs_test_device_command_timeouts():
    """
    This test is about timeouts on the client and blocking commands on the server
    for *device commands*.

    We start a control server which will register to the service registry and
    send out heartbeats.

    We start a control client that will connect to the server through its service type.
    Then we send the following commands, from the client perspective:

    - send a 'block' device command of 8s and a timeout of 3s. This will block the
      device commanding part on the server for ten seconds. The client will
      time out on this command after three seconds.
    - sleep for ten seconds.
    - send a 'say' command with a timeout of 2s. This will return immediately.

    The client should properly discard the server reply from the timed out block
    command. You should see a warning message saying a reply was received from a
    previous command. The 'say' command should receive its response as expected.

    """

    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    logger.info("Starting Asynchronous Control Server ...")

    # Give the control server the time to start up
    logger.info("Sleep for 0.5s...")
    await asyncio.sleep(0.5)

    # As of now, the server_task is running 'in the background' in the event loop.

    # Now create a control client that will connect to the above server.
    async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 5s...")
        await asyncio.sleep(5.0)

        logger.info("Send a blocking device command, duration is 8s, timeout is 3s.")
        response = await client.do({"command": "block", "sleep": 8}, timeout=3)
        logger.info(f"block: {response=}")

        if response["success"] or "timed out" not in response["message"]:
            logger.error(f"Did not get expected message from server: {response['message']}")

        logger.info("Sleep for 10s...")
        await asyncio.sleep(10.0)

        logger.info("Send a 'say' device command, timeout is 2s.")
        response = await client.do({"command": "say", "message": "Hello, World!"}, timeout=2.0)
        logger.info(f"say: {response=}")

        if not response["success"] or "Hello, World!" not in response["message"]:
            logger.error(f"Did not get expected message from server: {response['message']}")

        is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
        logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

        logger.info("Sleeping 1s before terminating the server...")
        await asyncio.sleep(1.0)

        logger.info("Terminating the server.")
        response = await client.stop_server()
        logger.info(f"stop_server: {response = }")

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

    await server_task

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")


async def cs_test_service_command_timeouts():
    """
    This test is about timeouts on the client and blocking commands on the server
    for *service commands*.

    We start a control server which will register to the service registry and
    send out heartbeats.

    We start a control client that will connect to the server through its service type.
    Then we send the following commands, from the client perspective:

    - send a 'block' service command of 8s and a timeout of 3s. This will block the
      service commanding part on the server for ten seconds. The client will
      time out on this command after three seconds.
    - sleep for ten seconds.
    - send a 'info' command with a timeout of 2s. This will return immediately.

    The client should properly discard the server reply from the timed out block
    command. You should see a warning message saying a reply was received from a
    previous command. The 'info' command should receive its response as expected.

    """

    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    logger.info("Starting Asynchronous Control Server ...")

    # Give the control server the time to start up
    logger.info("Sleep for 0.5s...")
    await asyncio.sleep(0.5)

    # As of now, the server_task is running 'in the background' in the event loop.

    # Now create a control client that will connect to the above server.
    async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 5s...")
        await asyncio.sleep(5.0)

        logger.info("Send a blocking service command, duration is 8s, timeout is 3s.")
        response = await client.block(sleep=8, timeout=3)
        logger.info(f"service block: {response=}")

        logger.info("Sleep for 10s...")
        await asyncio.sleep(10.0)

        logger.info("Get info on the control server.")
        response = await client.info()
        logger.info(f"service info: {response=}")

        is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
        logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

        logger.info("Sleeping 1s before terminating the server...")
        await asyncio.sleep(1.0)

        logger.info("Terminating the server.")
        response = await client.stop_server()
        logger.info(f"stop_server: {response = }")

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

    await server_task

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")


async def cs_test_control_server_with_blocking_device_command():
    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    logger.info("Starting Asynchronous Control Server ...")

    # Give the control server the time to start up
    logger.info("Sleep for 0.5s...")
    await asyncio.sleep(0.5)

    # As of now, the server_task is running 'in the background' in the event loop.

    # Now create a control client that will connect to the above server.
    async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 5s...")
        await asyncio.sleep(5.0)

        logger.info("Send a 'ping' service command...")
        response = await client.ping()
        logger.info(f"ping service command: {response = }")  # should be: response = 'pong'

        logger.info("Send an 'info' service command...")
        response = await client.info()
        logger.info(f"info service command: {response = }")  # should be: response = {'name': 'AsyncControlServer', ...

        logger.info("Send an 'info' device command...")
        # info() is a service command and not a device command, so this will fail.
        response = await client.do({"command": "info"})
        # should be: response={'success': False, 'message': 'Unknown command: info', ...
        logger.info(f"info device command: {response=}")

        # this will block commanding since device commands are executed in the same task
        # the do() will timeout after 3s, but the block command will run for 10s on the
        # server, and it will send back an ACK (which will be caught and interpreted by
        # –in this case– the seconds do 'say' command, which will not yet have timed out.
        logger.info("Send a blocking device command, duration is 9s, timeout is 3s.")
        response = await client.do({"command": "block", "sleep": 9}, timeout=3.0)
        # should be: response={'success': False, 'message': 'Request timed out after 3.000s'}
        logger.info(f"Blocking device command: {response=}")

        # ping() is a service command, so this is not blocked by the above block() command
        logger.info("Send a 'ping' service command...")
        response = await client.ping()
        logger.info(f"ping service command: {response=}")

        # say() is a device command and will time out after 2s because the above blocking
        # block() command is still running on the server
        logger.info("Send a 'say' device command, timeout is 2s.")
        response = await client.do({"command": "say", "message": "Hello, World!"}, timeout=2.0)
        logger.info(f"say device command: {response=}")

        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 10s...")
        await asyncio.sleep(10.0)

        # This time we won't let the command time out...
        logger.info("Send a 'say' device command, timeout is 2s.")
        response = await client.do({"command": "say", "message": "Hello, Again!"}, timeout=2.0)
        logger.info(f"say device command: {response=}")

        is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
        logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

        logger.info("Sleeping 1s before terminating the server...")
        await asyncio.sleep(1.0)

        logger.info("Terminating the server.")
        response = await client.stop_server()
        logger.info(f"stop_server: {response = }")

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

    await server_task

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")


if __name__ == "__main__":
    from rich.console import Console

    console = Console()

    # The statement logging.captureWarnings(True) redirects Python's warnings module output
    # (such as warnings.warn(...)) to the logging system, so warnings appear in your logs
    # instead of just printing to stderr. This is useful for unified logging and easier
    # debugging, especially in larger applications.
    logging.captureWarnings(True)

    # You can run the individual tests with `py test_connect.py`
    # Add those tests that are missing when you need them.

    while True:
        print(
            textwrap.dedent(
                """\
                1. cs_test_device_command_timeouts
                2. cs_test_service_command_timeouts
                3. cs_test_control_server_with_blocking_device_command

                0. Exit
                """
            )
        )

        try:
            x = input("Select a number for the test you want to execute: ")
        except KeyboardInterrupt:
            console.print("\nCaught KeyboardInterrupt, please enter a number.", style="orange1")
            continue

        try:
            match int(x.strip()):
                case 0:
                    console.print("Exiting.", style="bold green")
                    break
                case 1:
                    doc = inspect.getdoc(cs_test_device_command_timeouts)
                    if doc:
                        print("-" * 20, " Test Description ", "-" * 100)
                        print(doc)
                        print("-" * 140)
                    asyncio.run(cs_test_device_command_timeouts())
                case 2:
                    asyncio.run(cs_test_service_command_timeouts())
                case 3:
                    asyncio.run(cs_test_control_server_with_blocking_device_command())
                case _:
                    console.print("Invalid selection.", style="bold red")

        except KeyboardInterrupt:
            console.print("\nCaught KeyboardInterrupt, terminating test.", style="orange1")
        except ValueError:
            console.print("\nInvalid input, please enter a number.", style="bold red")
        except asyncio.CancelledError:
            console.print("\nTest cancelled.", style="bold red")
