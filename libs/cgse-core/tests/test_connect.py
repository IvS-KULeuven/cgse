import asyncio
import threading
import time

import pytest

from egse.connect import AsyncServiceConnector
from egse.connect import ConnectionState
from egse.connect import ServiceConnector
from egse.log import logging

logger = logging.getLogger("egse.test.connect")


@pytest.mark.asyncio
async def test_successful_connection_async():
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
                    logger.warning("sm_cs health check failed, marking as disconnected")

            await asyncio.sleep(1)  # Check every second

    async def run_main_test(connector: AsyncServiceConnector):
        assert connector.is_connected()
        assert await connector.health_check()

    task_running = True

    connector = MyServiceConnector("my_service")

    asyncio.create_task(manage_my_service_connection(connector))

    await asyncio.sleep(1.0)

    await run_main_test(connector)

    task_running = False


@pytest.mark.asyncio
async def test_unsuccessful_connection_async():
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
                    logger.warning("sm_cs health check failed, marking as disconnected")

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


@pytest.mark.asyncio
async def test_retries_connection_async():
    class MyServiceConnector(AsyncServiceConnector):
        def __init__(self, service_name: str):
            super().__init__(service_name)
            self.attempts = 0
            self.max_attempts = 3
            self.connection = None

        async def connect_to_service(self) -> bool:
            if self.attempts < self.max_attempts:
                logger.warning(f"Couldn't connect to service {self.service_name}")
                self.attempts += 1
            else:
                # self.attempts = 0
                self.connection = "I am a socket or transport object"

            return self.connection is not None

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

            await asyncio.sleep(1)  # Check every second

    async def run_main_test(connector: AsyncServiceConnector):
        assert not connector.is_connected()
        assert not await connector.health_check()

        await asyncio.sleep(20.0)

        assert connector.is_connected()
        assert await connector.health_check()
        assert connector.get_connection() == "I am a socket or transport object"

    task_running = True

    connector = MyServiceConnector("my_service")

    task = asyncio.create_task(manage_my_service_connection(connector))

    await asyncio.sleep(1.0)

    await run_main_test(connector)

    task_running = False

    task.cancel("end-of-test-cancelling")


def test_connection():
    class MyDeviceConnector(ServiceConnector):
        def connect_to_service(self) -> bool:
            logger.info(f"Attempting to connect to {self.service_name}...{self.failure_count=}")
            # Simulate a connection attempt (succeeds after 3 tries)
            if self.failure_count >= 2:
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

    # time.sleep(10.0)


if __name__ == "__main__":
    test_connection()
