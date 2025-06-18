"""
ZeroMQ tests with proper resource sharing between tests.

Usage:
    $ uv run py tests/script_test_service_registry_server.py
"""

import asyncio
import json
import logging
import random
import re
import time

import pytest
import zmq
import zmq.asyncio

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-12s %(lineno)5d:%(module)-20s %(message)s",
)

logger = logging.getLogger("zmq_test")

# Use dynamic test ports to avoid conflicts between test runs
TEST_REQ_PORT = random.randint(15000, 16000)
TEST_PUB_PORT = TEST_REQ_PORT + 1

logger.info(f"Using test ports - REQ: {TEST_REQ_PORT}, PUB: {TEST_PUB_PORT}")

# Test-specific socket options
SOCKET_OPTIONS = {
    zmq.LINGER: 0,  # Don't wait when closing sockets
    zmq.RCVTIMEO: 5000,  # 5 second receive timeout
    zmq.SNDTIMEO: 5000,  # 5 second send timeout
    zmq.IMMEDIATE: 1,  # Don't queue messages if no connection
}

# Use pytest-asyncio for async tests
pytestmark = pytest.mark.asyncio


def test_uuid_response_with_regex(response, prefix: str = "test-service"):
    # Define the expected pattern: prefix followed by UUID format
    pattern = rf"^{prefix}" + r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

    # Assert the response matches the pattern
    assert re.match(pattern, response), f"Response '{response}' does not match expected pattern"


async def test_basic_zmq_req_rep():
    """
    Simple test of ZeroMQ REQ-REP pattern to verify basic functionality.
    This helps isolate whether the issue is with ZeroMQ itself or something else.
    """
    # Create a context
    context = zmq.asyncio.Context()

    try:
        # Create sockets
        rep_socket = context.socket(zmq.REP)
        for k, v in SOCKET_OPTIONS.items():
            rep_socket.setsockopt(k, v)

        # Bind to a random port
        port = rep_socket.bind_to_random_port("tcp://127.0.0.1")
        logger.info(f"Basic test bound to port {port}")

        req_socket = context.socket(zmq.REQ)
        for k, v in SOCKET_OPTIONS.items():
            req_socket.setsockopt(k, v)
        req_socket.connect(f"tcp://127.0.0.1:{port}")

        # Start a task to handle requests
        async def handle_requests():
            while True:
                try:
                    message = await rep_socket.recv_string()
                    logger.info(f"Basic test received: {message}")
                    await rep_socket.send_string(f"REPLY: {message}")
                except zmq.ZMQError as e:
                    if e.errno == zmq.EAGAIN:
                        # Socket closed or timeout
                        break
                    logger.error(f"ZMQ error in handler: {e}")
                    break
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in handler: {e}")
                    break

        # Start the handler task
        handler_task = asyncio.create_task(handle_requests())

        # Send a request
        await req_socket.send_string("HELLO")
        logger.info("Basic test sent request")

        # Get the response with timeout
        if await req_socket.poll(timeout=5000):
            response = await req_socket.recv_string()
            logger.info(f"Basic test got response: {response}")
            assert response == "REPLY: HELLO"
        else:
            logger.error("Timeout waiting for response in basic test")
            assert False, "ZeroMQ basic test failed - no response"

        # Clean up
        handler_task.cancel()
        await asyncio.gather(handler_task, return_exceptions=True)
    finally:
        # Clean up sockets
        rep_socket.close()
        req_socket.close()
        context.term()


async def setup_registry_server():
    """
    Set up the registry server and return it along with its task.

    Returns:
        Tuple of (server, server_task, backend)
    """
    from egse.registry.backend import AsyncInMemoryBackend
    from egse.registry.server import AsyncRegistryServer

    logger.info("Setting up registry server")

    # Create backend
    backend = AsyncInMemoryBackend()
    await backend.initialize()

    # Create server with test ports
    server = AsyncRegistryServer(req_port=TEST_REQ_PORT, pub_port=TEST_PUB_PORT, backend=backend)

    # Start server
    server_task = asyncio.create_task(server.start())
    logger.info(f"Server starting on ports {TEST_REQ_PORT}/{TEST_PUB_PORT}")

    # Wait a bit for server to start
    await asyncio.sleep(0.5)

    return server, server_task, backend


async def cleanup_registry_server(server, server_task, backend):
    """
    Clean up the registry server resources.
    """
    logger.info("Cleaning up registry server")
    server.stop()
    await asyncio.gather(server_task, return_exceptions=True)
    await backend.close()
    logger.info("Registry server cleaned up")


async def send_request(request, timeout=5.0):
    """
    Send a request with a fresh socket each time.

    Args:
        request: The request to send
        timeout: Timeout in seconds

    Returns:
        The response as a dictionary
    """
    logger.debug(f"Sending request: {request}")
    start_time = time.time()

    # Create a fresh socket for this request
    context = zmq.asyncio.Context.instance()
    socket = context.socket(zmq.REQ)
    for k, v in SOCKET_OPTIONS.items():
        socket.setsockopt(k, v)

    socket.connect(f"tcp://localhost:{TEST_REQ_PORT}")
    logger.debug("Connected fresh socket")

    try:
        # Send the request
        logger.debug(f"Sending: {json.dumps(request)}")
        await asyncio.wait_for(socket.send_string(json.dumps(request)), timeout=timeout)
        logger.debug("Request sent, waiting for response")

        # Wait for response with poll and timeout
        if await socket.poll(timeout=timeout * 1000) == 0:
            logger.error(f"Timeout polling for response to {request.get('action')}")
            raise TimeoutError(f"Timeout waiting for response to {request.get('action')}")

        # Receive the response
        logger.debug("Poll successful, receiving response")
        response_json = await asyncio.wait_for(socket.recv_string(), timeout=timeout)
        logger.debug(f"Response received: {response_json[:100]}...")

        # Parse and return
        return json.loads(response_json)

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Error in send_request after {elapsed:.2f}s: {str(e)}")
        raise
    finally:
        # Clean up
        socket.close(linger=0)
        logger.debug("Request socket closed")


async def test_registry_server_health():
    """
    Test the registry server's health check endpoint.
    """
    # Send health check request
    response = await send_request({"action": "health"})
    logger.info(f"Health check response: {response}")

    # Verify response
    assert response.get("success") is True
    assert "status" in response
    assert response["status"] == "ok"

    return True


async def test_registry_server_registration():
    """
    Test registering a service with the registry.
    """
    # Service info
    service_info = {
        "name": "test-service",
        "host": "localhost",
        "port": 8080,
        "type": "test",
        "tags": ["test"],
        "metadata": {"version": "1.0.0"},
    }

    # Register the service
    response = await send_request({"action": "register", "service_info": service_info})
    logger.info(f"Registration response: {response}")

    # Verify response
    assert response.get("success") is True
    assert "service_id" in response

    # Get the service ID for future use
    service_id = response["service_id"]

    # Now try to get the service
    response = await send_request({"action": "get", "service_id": service_id})
    logger.info(f"Get service response: {response}")

    # Verify response
    assert response.get("success") is True
    assert "service" in response
    assert response["service"]["name"] == "test-service"

    return service_id


async def test_registry_server_listing():
    """
    Test listing services from the registry.
    """
    # List all services
    response = await send_request({"action": "list"})
    logger.info(f"List services response: {response}")

    # Verify response
    assert response.get("success") is True
    assert "services" in response

    # There should be at least one service (from the registration test)
    assert len(response["services"]) >= 1

    return True


async def run_all_tests():
    """
    Run all tests in sequence, properly sharing resources.
    """
    # First test basic ZeroMQ functionality
    logger.info("\n=== Testing basic ZeroMQ functionality ===")
    await test_basic_zmq_req_rep()

    # Now test the registry server
    logger.info("\n=== Setting up registry server ===")
    server, server_task, backend = await setup_registry_server()

    try:
        # Wait for 10s to inspect logs coming from the server

        logger.info("\n=== Waiting 10s to inspect server logs ===")
        await asyncio.sleep(10.0)

        # Test server health
        logger.info("\n=== Testing registry server health ===")
        await test_registry_server_health()

        # Test registration
        logger.info("\n=== Testing service registration ===")
        service_id = await test_registry_server_registration()
        test_uuid_response_with_regex(service_id)

        # Test listing
        logger.info("\n=== Testing service listing ===")
        await test_registry_server_listing()

        # More tests can be added here...

        logger.info("\n=== All tests passed successfully! ===")
        return 0
    except Exception as e:
        logger.error(f"\n=== Test failed: {e} ===")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        # Clean up resources
        logger.info("\n=== Cleaning up resources ===")
        await cleanup_registry_server(server, server_task, backend)


if __name__ == "__main__":
    # This allows running these tests directly without pytest
    import sys

    sys.exit(asyncio.run(run_all_tests()))
