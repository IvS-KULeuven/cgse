"""
Test to verify the server is running in the background.

Start the test as follows:

    $ uv run pytest -v --setup-show tests/test_server_running_with_fixture.py

"""

import asyncio
import json
import time

import pytest
import pytest_asyncio
import zmq
import zmq.asyncio

from egse.log import logger
from egse.registry.backend import AsyncInMemoryBackend
from egse.registry.server import AsyncRegistryServer
from fixtures.helpers import is_service_registry_running

TEST_REQ_PORT = 15556
TEST_PUB_PORT = 15557

SERVER_STARTUP_TIMEOUT = 5

pytestmark = pytest.mark.skipif(is_service_registry_running, reason="this file is not ready for testing yet")


async def server_health_check(zmq_context):
    # Verify server is ready by testing the health endpoint
    start_time = time.time()
    test_socket = zmq_context.socket(zmq.REQ)
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
            await test_socket.send_string(json.dumps(health_request))

            # Wait for response
            if await test_socket.poll(timeout=1000):
                response_json = await test_socket.recv_string()
                response = json.loads(response_json)

                if response.get("success"):
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


@pytest_asyncio.fixture(scope="session")
async def zmq_context():
    """Session-scoped fixture for ZeroMQ context."""
    context = zmq.asyncio.Context()
    logger.info("Yielding zmq context...")
    yield context
    logger.info("Terminating zmq context...")
    context.term()


@pytest_asyncio.fixture(scope="session")
async def in_memory_backend():
    """Fixture for an in-memory backend."""
    backend = AsyncInMemoryBackend()
    await backend.initialize()
    yield backend
    await backend.close()


@pytest_asyncio.fixture(scope="module")
async def server(zmq_context, in_memory_backend):
    """
    Session-scoped fixture for AsyncRegistryServer that verifies the server
    is ready before proceeding.
    """

    # Create server with specified ports
    server = AsyncRegistryServer(
        req_port=TEST_REQ_PORT,
        pub_port=TEST_PUB_PORT,
        backend=in_memory_backend,
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

    yield server

    # Clean shutdown
    logger.info("Stopping server...")

    server.stop()

    try:
        await asyncio.wait_for(server_task, timeout=2.0)
    except asyncio.TimeoutError:
        logger.warning("WARNING: Server task didn't complete in time during shutdown")


@pytest.mark.asyncio
async def test_server_running_with_fixture(server):
    # Wait to see log messages from the server appearing

    await asyncio.sleep(10.0)
