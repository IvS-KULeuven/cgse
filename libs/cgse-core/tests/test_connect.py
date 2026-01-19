import asyncio
import sys
import textwrap
import threading
import time
from asyncio import subprocess
from pathlib import Path
from typing import Optional

import pytest

from egse.connect import AsyncServiceConnector
from egse.connect import BackoffStrategy
from egse.connect import ConnectionState
from egse.connect import JitterStrategy
from egse.connect import get_endpoint
from egse.device import DeviceConnectionError
from egse.log import logging
from egse.registry import is_service_registry_active
from egse.registry.client import RegistryClient
from egse.socketdevice import AsyncSocketDevice

logger = logging.getLogger("egse.test.connect")


@pytest.mark.asyncio
async def test_successful_connection_async():
    """Test that an AsyncServiceConnector establishes and reports a healthy connection.

    Defines a minimal AsyncServiceConnector subclass whose connect_to_service() and health_check() always succeed. A
    background coroutine repeatedly calls attempt_connection() and performs periodic health checks. After a short
    delay the test asserts that the connector is connected and that health_check() returns True, verifying normal
    connection and monitoring behavior.
    """

    from egse.connect import AsyncServiceConnector
    from egse.connect import ConnectionState

    class MyServiceConnector(AsyncServiceConnector):
        def __init__(self, service_name: str):
            super().__init__(service_name)

        async def connect_to_service(self) -> bool:
            return True

        async def health_check(self) -> bool:
            return True

    async def manage_my_service_connection(connector):
        while task_running:
            await connector.attempt_connection()

            # Health check if connected
            if connector.is_connected():
                if not await connector.health_check():
                    connector.state = ConnectionState.DISCONNECTED
                    logger.warning(f"{connector.service_name} health check failed, marking as disconnected.")

            await asyncio.sleep(1)  # Check every second

    async def run_main_test(connector: AsyncServiceConnector):
        assert connector.is_connected()
        assert await connector.health_check()

    task_running = True

    connector = MyServiceConnector("my_service")

    task = asyncio.create_task(manage_my_service_connection(connector))

    await asyncio.sleep(1.0)

    await run_main_test(connector)

    task_running = False

    task.cancel("end-of-test-cancelling")
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Task manage_my_service_connection was cancelled as expected.")


@pytest.mark.asyncio
async def test_unsuccessful_connection_async():
    """Test that an AsyncServiceConnector remains disconnected when connection attempts fail.

    Creates a minimal AsyncServiceConnector whose connect_to_service() always fails and whose health_check() reports
    unhealthy. A background coroutine repeatedly calls attempt_connection() and performs periodic health checks.
    After a short delay the test asserts the connector is not connected and that health_check() returns False,
    verifying failure handling and monitoring.
    """

    from egse.connect import AsyncServiceConnector
    from egse.connect import ConnectionState

    class MyServiceConnector(AsyncServiceConnector):
        def __init__(self, service_name: str):
            super().__init__(service_name)

        async def connect_to_service(self) -> bool:
            logger.warning(f"Couldn't connect to service {self.service_name}")
            return False

        async def health_check(self) -> bool:
            return False

    async def manage_my_service_connection(connector):
        while task_running:
            await connector.attempt_connection()

            # Health check if connected
            if connector.is_connected():
                if not await connector.health_check():
                    connector.state = ConnectionState.DISCONNECTED
                    logger.warning(f"{connector.service_name} health check failed, marking as disconnected.")

            await asyncio.sleep(1)  # Check every second

    async def run_main_test(connector: AsyncServiceConnector):
        assert not connector.is_connected()
        assert not await connector.health_check()

    task_running = True

    connector = MyServiceConnector("my_service")

    task = asyncio.create_task(manage_my_service_connection(connector))

    await asyncio.sleep(1.0)

    await run_main_test(connector)

    task_running = False
    task.cancel("end-of-test-cancelling")
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Task manage_my_service_connection was cancelled as expected.")


@pytest.mark.asyncio
async def test_retries_connection_async():
    """Test that an AsyncServiceConnector eventually connects after transient failures.

    Defines a connector that simulates a fixed number of failed connect_to_service() attempts
    before succeeding and exposing a connection object. A background task calls attempt_connection()
    repeatedly and runs health checks. The test asserts the initial disconnected state, waits
    long enough for retries to complete, then asserts the connector is connected, health_check()
    is True, and the returned connection object matches the expected value.
    """

    from egse.connect import AsyncServiceConnector
    from egse.connect import ConnectionState

    class MyServiceConnector(AsyncServiceConnector):
        def __init__(self, service_name: str, max_attempts: int = 3):
            super().__init__(service_name)
            self.attempts = 0
            self.max_attempts = max_attempts
            self.connection = None

        async def connect_to_service(self) -> bool:
            if self.attempts < self.max_attempts:
                logger.warning(f"Couldn't connect to service {self.service_name}")
                self.attempts += 1
            else:
                # self.attempts = 0
                logger.info(f"Connected to {self.service_name}.")
                self.connection = "I am a socket or transport object"

            return self.connection is not None

        async def disconnect_from_service(self) -> None:
            logger.info(f"Disconnecting from {self.service_name}..")
            self.connection = None
            self.state = ConnectionState.DISCONNECTED

        async def health_check(self) -> bool:
            if self.is_connected():
                return True
            else:
                return False

        def get_connection(self):
            return self.connection

    async def manage_my_service_connection(connector):
        while task_running:
            await connector.attempt_connection()

            # Health check if connected
            if connector.is_connected():
                if not await connector.health_check():
                    connector.state = ConnectionState.DISCONNECTED
                    logger.warning("service health check failed, marking as disconnected")

            await asyncio.sleep(1.0)  # Check every second

    async def run_main_test(connector: AsyncServiceConnector):
        assert not connector.is_connected()
        assert not await connector.health_check()

        logger.info("Waiting for service to connect...")
        await asyncio.sleep(15.0)

        assert connector.is_connected()
        assert await connector.health_check()
        # FIXME: this method should be a method of the Connector base class, a connector
        #        should always be able to return its underlying connection object.
        assert connector.get_connection() == "I am a socket or transport object"

    task_running = True

    # Beware this test illustrates the exponential backoff + equal jitter strategies.
    # So, for 3 attempts, you should calculate a sleep() time of about 15s in the
    # run_main_test() before the service will be connected.

    connector = MyServiceConnector("my_service", max_attempts=3)

    task = asyncio.create_task(manage_my_service_connection(connector))

    await asyncio.sleep(1.0)

    await run_main_test(connector)

    task_running = False

    task.cancel("end-of-test-cancelling")
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Task manage_my_service_connection was cancelled as expected.")

    await connector.disconnect_from_service()


@pytest.mark.asyncio
async def test_circuit_break_async():
    """Test that an AsyncServiceConnector ends up in a circuit break after # failures.

    Defines a connector that simulates a fixed number of failed connect_to_service() attempts
    before going into a circuit break. A background task calls attempt_connection()
    repeatedly and runs health checks. The test asserts the initial disconnected state, waits
    long enough for retries to complete, then asserts the connector still not connected, health_check()
    is False, and the state is in circuit break.
    """

    from egse.connect import AsyncServiceConnector
    from egse.connect import ConnectionState

    class MyServiceConnector(AsyncServiceConnector):
        def __init__(self, service_name: str):
            super().__init__(service_name)
            self.attempts = 0
            self.max_attempts = 6  # > max_failures_before_circuit_break
            self.connection = None

        async def connect_to_service(self) -> bool:
            if self.attempts < self.max_attempts:
                logger.warning(f"Couldn't connect to service {self.service_name}")
                self.attempts += 1
            else:
                # self.attempts = 0
                logger.info(f"Connected to {self.service_name}.")
                self.connection = "I am a socket or transport object"

            return self.connection is not None

        async def disconnect_from_service(self) -> None:
            logger.info(f"Disconnecting from {self.service_name}..")
            self.connection = None
            self.state = ConnectionState.DISCONNECTED

        async def health_check(self) -> bool:
            if self.is_connected():
                return True
            else:
                return False

        def get_connection(self):
            return self.connection

    async def manage_my_service_connection(connector):
        while task_running:
            await connector.attempt_connection()

            # Health check if connected
            if connector.is_connected():
                if not await connector.health_check():
                    connector.state = ConnectionState.DISCONNECTED
                    logger.warning("service health check failed, marking as disconnected")
            else:
                logger.warning(f"Service {connector.service_name} is not connected")

            await asyncio.sleep(1.0)  # Check every second

    async def run_main_test(connector: MyServiceConnector):
        assert not connector.is_connected()
        assert not await connector.health_check()

        await asyncio.sleep(30.0)

        assert not connector.is_connected()
        assert not await connector.health_check()
        assert connector.state == ConnectionState.CIRCUIT_OPEN

        await asyncio.sleep(connector.circuit_break_duration)

        connector.max_attempts = 3

        await asyncio.sleep(15.0)

        assert connector.is_connected()
        assert await connector.health_check()

    task_running = True

    # Beware this test illustrates the exponential backoff + equal jitter strategies.
    # So, for 3 attempts, you should calculate a sleep() time of about 15s in the
    # run_main_test() before the service will be connected.

    connector = MyServiceConnector("my_service")

    task = asyncio.create_task(manage_my_service_connection(connector))

    await asyncio.sleep(1.0)

    await run_main_test(connector)

    task_running = False

    task.cancel("end-of-test-cancelling")
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Task manage_my_service_connection was cancelled as expected.")

    await connector.disconnect_from_service()


@pytest.mark.asyncio
async def test_socket_connection_async():
    class AsyncSocketServiceConnector(AsyncServiceConnector):
        """
        Async connector that uses AsyncSocketDevice (no threads).
        """

        def __init__(self, service_name: str, hostname: str, port: int, connect_timeout: float = 3.0):
            super().__init__(service_name)
            self.hostname = hostname
            self.port = port
            self.connect_timeout = connect_timeout
            self.device: Optional[AsyncSocketDevice] = None

        async def connect_to_service(self) -> bool:
            try:
                self.device = AsyncSocketDevice(self.hostname, self.port, connect_timeout=self.connect_timeout)
                await self.device.connect()
                return self.device.is_connected()
            except Exception as exc:
                logger.warning(f"{self.service_name}: connect_to_service failed: {exc}")
                self.device = None
                return False

        async def disconnect_from_service(self) -> None:
            if self.device:
                await self.device.disconnect()
            self.state = ConnectionState.DISCONNECTED

        async def health_check(self) -> bool:
            if not self.device or not self.device.is_connected():
                device_name = self.device.device_name if self.device else "unknown"
                logger.warning(f"Device {device_name} not connected.")
                return False
            try:
                # lightweight ping; adjust protocol as needed
                resp = await asyncio.wait_for(self.device.trans("PING\x03"), timeout=1.0)
                return bool(resp)
            except (DeviceConnectionError, asyncio.TimeoutError, Exception):
                logger.debug(f"{self.service_name}: health_check failed, cleaning up")
                if self.device:
                    try:
                        await self.device.disconnect()
                    except Exception:
                        pass
                    self.device = None
                return False

        def get_device(self) -> Optional[AsyncSocketDevice]:
            return self.device

    async def manage_my_service_connection(connector):
        while task_running:
            await connector.attempt_connection()

            # Health check if connected
            if connector.is_connected():
                if not await connector.health_check():
                    connector.state = ConnectionState.DISCONNECTED
                    logger.warning("service health check failed, marking as disconnected")

            await asyncio.sleep(1.0)  # Check every second

    async def run_main_test(connector: AsyncServiceConnector):
        assert connector.is_connected()
        assert await connector.health_check()

        await asyncio.sleep(10.0)

        assert connector.is_connected()
        assert await connector.health_check()
        device: AsyncSocketDevice = connector.get_device()
        assert device.is_connected()
        response = await device.trans("some_command: pars\x03")
        logger.info(f"Response received: {response}")
        assert response.decode().startswith("ACK")

    server = None
    task_running = True

    connector = AsyncSocketServiceConnector("my_simple_unix_server", "localhost", 5555)

    task = asyncio.create_task(manage_my_service_connection(connector))

    await asyncio.sleep(5.0)  # have a few failures to connect

    # Needs the simple_server running on localhost, 5555
    # Simulate that the server is coming alive only now.
    server = await simple_server()

    # wait for the manage_my_service_connection to connect
    while not connector.is_connected():
        await asyncio.sleep(0.1)

    try:
        await run_main_test(connector)
    finally:
        task_running = False
        task.cancel("end-of-test-cancelling")
        while not task.done():
            await asyncio.sleep(0.1)
        await connector.disconnect_from_service()
        server and server.terminate()


def test_connection_sync(attempts: int = 2):
    """Test that a synchronous ServiceConnector retries in a background thread until connected.

    Implements a ServiceConnector whose connect_to_service() fails for the first few attempts
    and succeeds thereafter. A background thread repeatedly calls attempt_connection() with sleeps
    between tries. The test starts the thread and waits, asserting that the connector becomes
    connected within the test's waiting loop, demonstrating retry behavior in a threaded context.
    """
    from egse.connect import ServiceConnector

    class MyDeviceConnector(ServiceConnector):
        def connect_to_service(self) -> bool:
            logger.info(f"Attempting to connect to {self.service_name}...{self.failure_count=}")
            # Simulate a connection attempt (succeeds after 3 tries)
            if self.failure_count >= attempts:
                logger.info("Connection successful!")
                return True
            logger.info("Connection failed.")
            return False

    def background_connect(connector: ServiceConnector):
        logger.info("Establishing connection...")

        count = 0
        while not connector.is_connected():
            logger.info(f"In background waiting for connection....try {count}")
            connector.attempt_connection()
            time.sleep(0.5)
            count += 1

        logger.info("Connection established.")

    connector = MyDeviceConnector("my_device")

    thread = threading.Thread(target=background_connect, args=(connector,))
    thread.daemon = True
    thread.start()

    while not connector.is_connected():
        logger.info("Waiting for connection...")
        time.sleep(2.0)

    time.sleep(1.0)

    connector.disconnect_from_service()


async def single_connection_client(host="127.0.0.1", port=5555):
    # This coroutine connects to a simple_server that needs to be started separately from a terminal.
    # The simple server reside in this same folder in the test area.
    # This function served the purpose of demonstrating that there is only a single connection
    # created with the server.
    try:
        reader, writer = await asyncio.open_connection(host, port)

        print("client: connected once")

        try:
            for msg in ("PING\x03", "some_command: pars\x03", "QUIT\x03"):
                writer.write(msg.encode())
                await writer.drain()
                data = await asyncio.wait_for(reader.readuntil(separator=b"\x03"), timeout=2.0)
                print("client got:", data)
                await asyncio.sleep(0.2)
        finally:
            # We only need to close the writer since it owns the underlying transport (socket).
            # When we read after these calls, the reader will get an EOF.
            writer.close()
            await writer.wait_closed()
            print("client: connection closed")

    except ConnectionRefusedError as exc:
        print(f"ConnectionRefusedError: {exc}")


async def simple_server():
    cmd = Path(__file__).parent / "simple_server.py"
    server = await subprocess.create_subprocess_exec(sys.executable, cmd)
    await asyncio.sleep(0.2)  # give the server time to start up

    logger.info(f"simple_server process should be running: {server=}")

    return server


def test_get_endpoint():
    if not is_service_registry_active():
        pytest.xfail("This test expects the Registry Service to be running.")

    # This test also assumes the log server is running and registered to the service registry

    assert get_endpoint("LOG_CS").startswith("tcp://")
    assert get_endpoint("LOG_CS").endswith(":6106")

    with pytest.raises(RuntimeError, match="No service registered as"):
        assert get_endpoint(service_type="")
    with pytest.raises(RuntimeError, match="No service registered as"):
        assert get_endpoint(service_type=None)
    with pytest.raises(RuntimeError, match="No service registered as"):
        assert get_endpoint(hostname="localhost", port=0)

    assert get_endpoint("localhost", port=6106) == "tcp://localhost:6106"


@pytest.mark.asyncio
async def test_backoff_and_jitter():
    logger.warning("This test_backoff_and_jitter test will take about 45 seconds.")

    from egse.connect import AsyncServiceConnector
    from egse.connect import ConnectionState

    class MyServiceConnector(AsyncServiceConnector):
        def __init__(
            self,
            service_name: str,
            backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
            jitter_strategy: JitterStrategy = JitterStrategy.EQUAL,
        ):
            super().__init__(service_name, backoff_strategy, jitter_strategy=jitter_strategy)
            self.attempts = 0
            self.max_attempts = 3
            self.connection = None

        def __str__(self):
            return self.service_name

        async def connect_to_service(self) -> bool:
            if self.attempts < self.max_attempts:
                logger.warning(f"Couldn't connect to service {self.service_name}")
                self.attempts += 1
            else:
                # self.attempts = 0
                logger.info(f"Connected to {self.service_name}.")
                self.connection = "I am a socket or transport object"

            return self.connection is not None

        async def disconnect_from_service(self) -> None:
            logger.info(f"Disconnecting from {self.service_name}..")
            self.connection = None
            self.state = ConnectionState.DISCONNECTED

        async def health_check(self) -> bool:
            if self.is_connected():
                logger.debug("Service is found to be healthy.")
                return True
            else:
                logger.debug("Service is found to be unhealthy.")
                return False

        def get_connection(self):
            return self.connection

    async def manage_my_service_connection(connector):
        while task_running:
            await connector.attempt_connection()

            # Health check if connected
            if connector.is_connected():
                if not await connector.health_check():
                    connector.state = ConnectionState.DISCONNECTED
                    logger.warning("service health check failed, marking as disconnected")

            await asyncio.sleep(1.0)  # Check every second

    async def run_main_test(connector: AsyncServiceConnector):
        assert not connector.is_connected()
        assert not await connector.health_check()

        await asyncio.sleep(15.0)

        assert connector.is_connected()
        assert await connector.health_check()
        assert connector.get_connection() == "I am a socket or transport object"

    # Beware this test illustrates the exponential backoff + equal jitter strategies.
    # So, for 3 attempts, you should calculate a sleep() time of about 15s in the
    # run_main_test() before the service will be connected.

    for backoff, jitter in (
        (BackoffStrategy.EXPONENTIAL, JitterStrategy.EQUAL),
        (BackoffStrategy.LINEAR, JitterStrategy.NONE),
        (BackoffStrategy.FIXED, JitterStrategy.PERCENT_10),
    ):
        logger.info(f"Starting connector with backoff={backoff.name} and jitter={jitter.name}...")

        connector = MyServiceConnector("my_service", backoff_strategy=backoff, jitter_strategy=jitter)

        task_running = True

        task = asyncio.create_task(manage_my_service_connection(connector))

        await asyncio.sleep(1.0)

        await run_main_test(connector)

        task_running = False

        task.cancel("end-of-test-cancelling")
        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"Task manage_my_service_connection for {connector} was cancelled.")

        await connector.disconnect_from_service()


if __name__ == "__main__":
    # You can run the individual tests with `py test_connect.py`
    # Add those tests that are missing when you need them.

    print(
        textwrap.dedent(
            """\
        1. single_connection_client (simple_server should be running)
        2. test_socket_connection_async
        3. test_circuit_break_async
        4. test_backoff_and_jitter
        5. test_get_endpoint
        6. test_connection_sync
        7. test_retries_connection_async
        """
        )
    )
    x = input("Select a number for the test you want to execute: ")

    try:
        match int(x.strip()):
            case 1:
                asyncio.run(single_connection_client())
            case 2:
                asyncio.run(test_socket_connection_async())
            case 3:
                asyncio.run(test_circuit_break_async())
            case 4:
                asyncio.run(test_backoff_and_jitter())
            case 5:
                test_get_endpoint()
            case 6:
                test_connection_sync()
            case 7:
                asyncio.run(test_retries_connection_async())

    except asyncio.CancelledError:
        pass
