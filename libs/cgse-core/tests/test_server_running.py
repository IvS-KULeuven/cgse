"""
Test to verify the server is running in the background.

Start the test as follows (with pytest):

    $ uv run pytest -v --setup-show tests/test_server_running.py

Start the test wihout pytest:

    $ uv run py tests/test_server_running.py
"""

import asyncio
import json
import time

import pytest
import zmq
import zmq.asyncio
from fixtures.helpers import is_service_registry_running

from egse.log import logger
from egse.registry.backend import AsyncInMemoryBackend
from egse.registry.server import AsyncRegistryServer

TEST_REQ_PORT = 15556
TEST_PUB_PORT = 15557

SERVER_STARTUP_TIMEOUT = 5

pytestmark = pytest.mark.skipif(
    is_service_registry_running(), reason="This test starts its own registry server, so it can not be running."
)


async def server_health_check(zmq_context):
    # Verify server is ready by testing the health endpoint
    start_time = time.time()
    test_socket = zmq_context.socket(zmq.DEALER)
    test_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
    test_socket.setsockopt(zmq.IDENTITY, b"health-check-client")
    test_socket.connect(f"tcp://localhost:{TEST_REQ_PORT}")

    server_ready = False
    health_request = {"action": "health"}

    # Try several times to connect to the server
    for attempt in range(1, 11):  # 10 attempts
        logger.info(f"Attempt to connect to the server: {attempt}")
        try:
            if time.time() - start_time > SERVER_STARTUP_TIMEOUT:
                break

            # Send health check request
            await test_socket.send_multipart([b"REQ", json.dumps(health_request).encode()])

            # Wait for response
            if await test_socket.poll(timeout=1000):
                response_parts = await test_socket.recv_multipart()
                response_type = response_parts[0]
                logger.info(f"Received response type: {response_type=}")
                response_data = json.loads(response_parts[1].decode())
                logger.info(f"Received response data: {response_data=}")

                if response_data.get("success"):
                    server_ready = True
                    logger.info(f"Server ready after {attempt} attempts")
                    break

        except Exception as e:
            logger.error(f"ERROR: Attempt {attempt} failed: {e}")

        # Wait before trying again
        await asyncio.sleep(0.5)

    # Clean up test socket
    test_socket.close()

    return server_ready


async def start_server():
    """
    Session-scoped fixture for AsyncRegistryServer that verifies the server
    is ready before proceeding.
    """
    zmq_context = zmq.asyncio.Context()

    backend = AsyncInMemoryBackend()
    await backend.initialize()

    # Create server with specified ports
    server = AsyncRegistryServer(
        req_port=TEST_REQ_PORT,
        pub_port=TEST_PUB_PORT,
        backend=backend,
        cleanup_interval=1,  # Fast cleanup for testing
    )

    # Start the server in a task
    server_task = asyncio.create_task(server.start())

    server_ready = await server_health_check(zmq_context)

    if not server_ready:
        # Stop the server if it failed to start properly
        server.stop()
        try:
            await asyncio.wait_for(server_task, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        raise RuntimeError(f"Server failed to start after {SERVER_STARTUP_TIMEOUT} seconds")

    logger.info("Server is ready...")

    # Yield the server for tests to use
    return server, server_task


async def stop_server(server, server_task):
    # Clean shutdown
    logger.info("Stopping server...")

    server.stop()

    try:
        await asyncio.wait_for(server_task, timeout=2.0)
    except asyncio.TimeoutError:
        logger.warning("WARNING: Server task didn't complete in time during shutdown")


@pytest.mark.asyncio
async def test_server_running():
    await main()


async def main():
    server, server_task = await start_server()

    await asyncio.sleep(10.0)

    await stop_server(server, server_task)


# This allows you to run the test without using pytest

if __name__ == "__main__":
    asyncio.run(main())
