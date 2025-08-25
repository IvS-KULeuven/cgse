"""
Unit tests for AsyncRegistryServer and AsyncRegistryClient.

These tests verify the functionality of the ZeroMQ-based service registry components.

"""

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
import pytest_asyncio
import zmq
import zmq.asyncio

from egse.log import logger
from egse.registry import MessageType
from egse.registry.backend import AsyncInMemoryBackend
from egse.registry.client import AsyncRegistryClient
from egse.registry.server import AsyncRegistryServer
from egse.system import type_name
from fixtures.helpers import is_service_registry_running

# Constants for testing
TEST_REQ_PORT = 15556
TEST_PUB_PORT = 15557

# Wait timeout for the server to start (seconds)
SERVER_STARTUP_TIMEOUT = 5

pytestmark = pytest.mark.skipif(
    is_service_registry_running, reason="This test starts the registry server, so it can not be running"
)

################################################################################
# Fixed Helper Functions
################################################################################


async def send_request(msg_type: MessageType, socket, request, timeout=5.0):
    """
    Send a request to the server and get response with proper timeout.

    This improved version includes:
    - Timeout handling
    - Error handling
    - Diagnostic information
    """
    # Record start time for diagnostics
    start_time = time.time()

    try:
        # Send the request - add timeout to detect send failures
        try:
            await asyncio.wait_for(
                socket.send_multipart([msg_type.value, json.dumps(request).encode()]), timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timeout sending request: {request}")

        logger.info(f"Request sent: {request}")

        # Wait for response with timeout
        if await socket.poll(timeout=timeout * 1000) == 0:
            raise TimeoutError(f"Timeout waiting for response to {request.get('action')} after {timeout} seconds")

        # Receive the response with timeout
        try:
            message_parts = await asyncio.wait_for(socket.recv_multipart(), timeout=timeout)

            if len(message_parts) >= 2:
                message_type = MessageType(message_parts[0])
                message_data = message_parts[1]

                return json.loads(message_data)
            else:
                return {
                    "success": False,
                    "error": f"not enough parts received: {len(message_parts)}",
                    "data": message_parts,
                }

        except asyncio.TimeoutError:
            raise TimeoutError(f"Timeout receiving response for {request.get('action')}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON response: {exc}")

    except KeyboardInterrupt as exc:
        logger.info("Caught Keyboard Interrupt", exc_info=True)
    except Exception as exc:
        # Add diagnostics to the error
        elapsed = time.time() - start_time
        diagnostic_msg = f"Error in send_request after {elapsed:.2f}s: {str(exc)}"
        print(diagnostic_msg)  # Print for immediate feedback during test run
        raise RuntimeError(diagnostic_msg) from exc


async def wait_for_event(socket, timeout=2.0):
    """
    Wait for an event from the server with timeout.

    This improved version includes better error handling.
    """
    # Wait for a message with timeout
    if await socket.poll(timeout=timeout * 1000) == 0:
        return None

    try:
        # Get the message with a timeout
        _, data = await asyncio.wait_for(socket.recv_multipart(), timeout=timeout)

        # Parse and return only the data part, type was for subscribers and is also included in data
        return json.loads(data.decode("utf-8"))

    except asyncio.TimeoutError:
        return None
    except Exception as e:
        print(f"Error in wait_for_event: {e}")
        return None


async def server_health_check(zmq_context) -> bool:
    """server_health_check
    Verify if the server is ready by testing the health endpoint/action.
    """

    start_time = time.time()
    test_socket = zmq_context.socket(zmq.DEALER)
    test_socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages on close()
    test_socket.setsockopt(zmq.IDENTITY, "health-check-id".encode())
    test_socket.connect(f"tcp://localhost:{TEST_REQ_PORT}")

    server_ready = False
    msg_type = MessageType.REQUEST_WITH_REPLY
    health_request = {"action": "health"}

    # Try several times to connect to the server
    for attempt in range(1, 11):  # 10 attempts
        logger.info(f"Attempt to connect to the server: {attempt}")
        try:
            if time.time() - start_time > SERVER_STARTUP_TIMEOUT:
                break

            # Send health check request
            await test_socket.send_multipart([msg_type.value, json.dumps(health_request).encode()])

            # Wait for response
            if await test_socket.poll(timeout=1000):
                message_parts = await test_socket.recv_multipart()

                if len(message_parts) >= 2:
                    message_type = MessageType(message_parts[0])
                    message_data = message_parts[1]

                    response = json.loads(message_data)

                    if response.get("success"):
                        server_ready = True
                        logger.info(f"Server ready after {attempt} attempts")
                        break

        except Exception as exc:
            logger.error(f"ERROR: Attempt {attempt} failed: {exc}", exc_info=True)

        # Wait before trying again
        await asyncio.sleep(0.5)

    # Clean up test socket
    test_socket.close()

    return server_ready


################################################################################
# Fixtures
################################################################################


@pytest_asyncio.fixture
async def in_memory_backend():
    """Function-scoped fixture for an in-memory backend."""
    backend = AsyncInMemoryBackend()
    await backend.initialize()
    yield backend
    await backend.close()


@pytest_asyncio.fixture
async def server(in_memory_backend, zmq_context):
    """
    Function-scoped fixture for AsyncRegistryServer that verifies the server
    is ready before proceeding.
    """
    # Create server with specified ports
    server = AsyncRegistryServer(
        req_port=TEST_REQ_PORT,
        pub_port=TEST_PUB_PORT,
        backend=in_memory_backend,
        cleanup_interval=1,  # Fast cleanup for testing
    )

    # Start the server in a task to run in the background
    server_task = asyncio.create_task(server.start())

    server_ready = await server_health_check(zmq_context)

    if not server_ready:
        # Stop the server if it failed to start properly and raise a RuntimeError
        server.stop()
        try:
            await asyncio.wait_for(server_task, timeout=2.0)
        except asyncio.TimeoutError:
            pass
        except Exception as exc:
            msg = f"Caught {type_name(exc)}: {exc}"
            if str(exc).startswith("Address already in use"):
                msg += " – the Registry server is probably already running."
            logger.error(msg)

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


@pytest_asyncio.fixture
async def client(server, zmq_context):
    """
    Function-scoped fixture for AsyncRegistryClient with proper setup and teardown.
    """
    with AsyncRegistryClient(
        registry_req_endpoint=f"tcp://localhost:{TEST_REQ_PORT}",
        registry_sub_endpoint=f"tcp://localhost:{TEST_PUB_PORT}",
        request_timeout=5000,  # 5 second timeout
    ) as client:
        # Verify client can connect to server
        health = await client.health_check()
        if not health:
            raise RuntimeError("Client failed to connect to server")

        yield client

        # Proper cleanup
        # await client.close()


@pytest_asyncio.fixture
async def zmq_context():
    """
    Function-scoped fixture that provides the ZeroMQ Context.
    """
    context = zmq.asyncio.Context().instance()
    logger.info("Yielding zmq context...")
    yield context
    logger.info("Terminating zmq context...")
    context.term()


@pytest_asyncio.fixture
async def req_socket(zmq_context):
    """
    Function-scoped fixture for a DEALER socket with proper timeout settings.
    """
    socket = zmq_context.socket(zmq.DEALER)
    # Set timeouts to avoid hanging
    socket.setsockopt(zmq.LINGER, 0)  # Don't wait when closing
    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second receive timeout
    socket.setsockopt(zmq.SNDTIMEO, 5000)  # 5 second send timeout
    socket.setsockopt(zmq.IDENTITY, f"client-{uuid.uuid4()}".encode())
    socket.connect(f"tcp://localhost:{TEST_REQ_PORT}")

    yield socket

    # Properly close the socket
    socket.close(linger=0)


@pytest_asyncio.fixture
async def sub_socket(zmq_context):
    """
    Function-scoped fixture for a SUB socket with proper timeout settings.
    """
    socket = zmq_context.socket(zmq.SUB)
    # Set timeouts
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVTIMEO, 5000)

    socket.connect(f"tcp://localhost:{TEST_PUB_PORT}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages

    # Wait a moment for subscription to be established
    await asyncio.sleep(0.1)

    yield socket

    # Properly close the socket
    socket.close(linger=0)


@pytest.mark.asyncio
async def test_server_initialization(server):
    """Test that the server initializes correctly."""
    assert server.req_port == TEST_REQ_PORT
    assert server.pub_port == TEST_PUB_PORT
    assert server._running is True


@pytest.mark.asyncio
async def test_server_is_running(server):
    # Sleep for 10s and investigate the log, server should have printed some log messages
    logger.info("Sleeping for 10s, server shall post some debug log messages...")
    await asyncio.sleep(10.0)


@pytest.mark.asyncio
async def test_server_health_check(server, req_socket):
    """Test the server's health check."""
    response = await send_request(MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "health"})

    assert response["success"] is True
    assert response["status"] == "ok"
    assert "timestamp" in response


@pytest.mark.asyncio
async def test_server_handles_invalid_request(server, req_socket):
    """Test the server's handling of invalid requests."""
    # Missing action
    response = await send_request(MessageType.REQUEST_WITH_REPLY, req_socket, {})
    assert response["success"] is False
    assert "Missing required field: action" in response["error"]

    # Unknown action
    response = await send_request(MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "unknown_action"})
    assert response["success"] is False
    assert "Unknown action" in response["error"]

    # Invalid JSON - can't test directly with send_request as it uses json.dumps
    # This would require a lower-level test with raw socket


@pytest.mark.asyncio
async def test_server_register_service(server, req_socket, sub_socket):
    """Test registering a service."""

    service_info = {
        "name": "test-service",
        "host": "localhost",
        "port": 8080,
        "type": "test",
        "tags": ["test"],
        "metadata": {"version": "1.0.0"},
    }

    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "register", "service_info": service_info}
    )

    assert response["success"] is True
    assert "service_id" in response

    # Verify a registration event was published
    event = await wait_for_event(sub_socket)
    assert event is not None
    assert event["type"] == "register"
    assert "service_id" in event["data"]
    assert event["data"]["service_info"]["name"] == "test-service"


@pytest.mark.asyncio
async def test_server_get_service(server, req_socket):
    """Test getting a service by ID."""

    service_info = {"name": "test-service", "host": "localhost", "port": 8080}

    register_response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "register", "service_info": service_info}
    )

    service_id = register_response["service_id"]

    # Now get the service
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    assert response["success"] is True
    assert response["service"]["id"] == service_id
    assert response["service"]["name"] == "test-service"
    assert response["service"]["host"] == "localhost"
    assert response["service"]["port"] == 8080

    # Try to get a non-existent service
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": "nonexistent"}
    )

    assert response["success"] is False
    assert "Service not found" in response["error"]


@pytest.mark.asyncio
async def test_server_list_services(server, req_socket):
    """Test listing services."""

    # Register a couple of services
    await send_request(
        MessageType.REQUEST_WITH_REPLY,
        req_socket,
        {
            "action": "register",
            "service_info": {"name": "service-1", "host": "localhost", "port": 8081, "type": "type-a"},
        },
    )

    await send_request(
        MessageType.REQUEST_WITH_REPLY,
        req_socket,
        {
            "action": "register",
            "service_info": {"name": "service-2", "host": "localhost", "port": 8082, "type": "type-b"},
        },
    )

    # List all services
    response = await send_request(MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "list"})

    assert response["success"] is True
    assert len(response["services"]) >= 2

    # List services by type
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "list", "service_type": "type-a"}
    )

    assert response["success"] is True
    assert len(response["services"]) >= 1
    assert any(s["name"] == "service-1" for s in response["services"])
    assert not any(s["name"] == "service-2" for s in response["services"])


@pytest.mark.asyncio
async def test_server_discover_service(server, req_socket):
    """Test discovering a service by type."""

    await send_request(
        MessageType.REQUEST_WITH_REPLY,
        req_socket,
        {
            "action": "register",
            "service_info": {"name": "test-service", "host": "localhost", "port": 8080, "type": "discovery-test"},
        },
    )

    # Discover a service
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "discover", "service_type": "discovery-test"}
    )

    assert response["success"] is True
    assert response["service"]["name"] == "test-service"
    assert response["service"]["host"] == "localhost"
    assert response["service"]["port"] == 8080

    # Try to discover a non-existent service type
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "discover", "service_type": "nonexistent"}
    )

    assert response["success"] is False
    assert "No healthy service" in response["error"]


@pytest.mark.asyncio
async def test_server_deregister_service(server, req_socket, sub_socket):
    """Test de-registering a service."""

    register_response = await send_request(
        MessageType.REQUEST_WITH_REPLY,
        req_socket,
        {"action": "register", "service_info": {"name": "test-service", "host": "localhost", "port": 8080}},
    )

    service_id = register_response["service_id"]

    # Now deregister the service
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "deregister", "service_id": service_id}
    )

    assert response["success"] is True

    # Verify a de-registration event was published, the first event is the
    # registration which we will skip.
    event = await wait_for_event(sub_socket)
    assert event["type"] == "register"
    event = await wait_for_event(sub_socket)
    assert event is not None
    assert event["type"] == "deregister"
    assert event["data"]["service_id"] == service_id

    # Verify the service was deregistered
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    assert response["success"] is False


@pytest.mark.asyncio
async def test_server_renew_service(server, req_socket):
    """Test renewing a service's TTL."""

    register_response = await send_request(
        MessageType.REQUEST_WITH_REPLY,
        req_socket,
        {"action": "register", "service_info": {"name": "test-service", "host": "localhost", "port": 8080}, "ttl": 5},
    )

    service_id = register_response["service_id"]

    # Get the initial service data
    service_response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    initial_heartbeat = service_response["service"]["last_heartbeat"]

    # Wait a moment
    await asyncio.sleep(1.0)

    # Renew the service
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "renew", "service_id": service_id}
    )

    assert response["success"] is True

    # Verify the heartbeat was updated
    service_response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    assert service_response["service"]["last_heartbeat"] > initial_heartbeat


@pytest.mark.timeout(10)
@pytest.mark.asyncio
async def test_server_cleanup_expired_services(req_socket, sub_socket, server):
    """Test cleanup of expired services."""

    # Register a service with a short TTL
    register_response = await send_request(
        MessageType.REQUEST_WITH_REPLY,
        req_socket,
        {
            "action": "register",
            "service_info": {"name": "short-lived-service", "host": "localhost", "port": 8080},
            "ttl": 2,  # Very short TTL
        },
    )

    service_id = register_response["service_id"]

    # Wait for the service to expire and be cleaned up
    # Should take about 2-3 seconds (TTL + cleanup interval)
    expire_event = None
    for _ in range(5):  # Try a few times
        event = await wait_for_event(sub_socket, timeout=1.0)
        if event and event["type"] == "expire" and event["data"]["service_id"] == service_id:
            expire_event = event
            break

    assert expire_event is not None, "Service expiration event not received"

    # Verify the service was removed
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    assert response["success"] is False, "Service should have been removed"


@pytest.mark.asyncio
async def test_server_shutdown(server):
    """Test server shutdown."""

    assert server._running is True

    # Stop the server
    server.stop()

    await asyncio.sleep(0.5)  # Allow the server some time to shut down

    # Verify the server is no longer running
    assert server._running is False


# ######################################################################################################################
# Tests for AsyncRegistryClient
# ######################################################################################################################


@pytest.mark.asyncio
async def test_async_client_initialization(client):
    """Test that the client initializes correctly."""
    assert client.registry_req_endpoint == f"tcp://localhost:{TEST_REQ_PORT}"
    assert client.registry_sub_endpoint == f"tcp://localhost:{TEST_PUB_PORT}"


@pytest.mark.asyncio
async def test_async_client_register(client, server):
    """Test service registration."""

    service_id = await client.register(
        "test-client-service", "localhost", 8080, service_type="test-client", metadata={"version": "1.0.0"}
    )

    assert service_id is not None
    assert client._service_id == service_id
    assert client._service_info is not None
    assert client._service_info["name"] == "test-client-service"
    assert client._service_info["type"] == "test-client"


@pytest.mark.asyncio
async def test_client_deregister(client, server):
    """Test service de-registration."""

    # First register
    service_id = await client.register("test-client-service", "localhost", 8080)

    assert service_id is not None

    # Then deregister
    success = await client.deregister()

    assert success is True
    assert client._service_id is None


@pytest.mark.asyncio
async def test_client_heartbeat(client, server, req_socket):
    """Test service heartbeat."""

    # Register the service
    service_id = await client.register("heartbeat-test-service", "localhost", 8080, ttl=5)

    # Get initial heartbeat time
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    initial_heartbeat = response["service"]["last_heartbeat"]

    # Start heartbeat with a short interval
    await client.start_heartbeat(interval=1)

    # Wait for heartbeat to happen
    await asyncio.sleep(1.5)

    # Check if heartbeat was updated
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    assert response["service"]["last_heartbeat"] > initial_heartbeat

    # Stop heartbeat
    await client.stop_heartbeat()


@pytest.mark.timeout(10)
@pytest.mark.asyncio
async def test_client_event_listener(client, server, req_socket):
    """Test the client's event listener."""

    # Create a mocked event handler
    event_received = asyncio.Event()
    event_data = {}

    async def event_handler(data):
        event_data.update(data)
        event_received.set()

    # Register the event handler and start the listener
    client.on_event("register", event_handler)
    await client.start_event_listener()

    # Register a service to trigger an event
    await send_request(
        MessageType.REQUEST_WITH_REPLY,
        req_socket,
        {"action": "register", "service_info": {"name": "event-test-service", "host": "localhost", "port": 8080}},
    )

    # Wait for the event to be processed
    await asyncio.wait_for(event_received.wait(), timeout=5.0)

    # Verify the event was received
    assert "service_id" in event_data
    assert "service_info" in event_data
    assert event_data["service_info"]["name"] == "event-test-service"

    # Stop the event listener
    await client.stop_event_listener()


@pytest.mark.asyncio
async def test_client_discover_service(client, server):
    """Test service discovery."""

    # Register a service through the server
    service_id = await client.register("discovery-test-service", "localhost", 8080, service_type="discovery-test")

    # Discover a service
    service = await client.discover_service("discovery-test")

    assert service is not None
    assert service["id"] == service_id
    assert service["name"] == "discovery-test-service"
    assert service["host"] == "localhost"
    assert service["port"] == 8080

    # Try to discover a non-existent service type
    service = await client.discover_service("nonexistent")
    assert service is None


@pytest.mark.asyncio
async def test_client_get_service(client, server):
    """Test getting a service by ID."""

    service_id = await client.register("get-test-service", "localhost", 8080)

    # Get the service
    service = await client.get_service(service_id)

    assert service is not None
    assert service["id"] == service_id
    assert service["name"] == "get-test-service"

    # Try to get a non-existent service
    service = await client.get_service("nonexistent")
    assert service is None


@pytest.mark.asyncio
async def test_client_list_services(client, server):
    """Test listing services."""

    # Register some services
    await client.register("list-test-service-1", "localhost", 8081, service_type="type-a")

    await client.register("list-test-service-2", "localhost", 8082, service_type="type-b")

    # List all services
    services = await client.list_services()

    assert len(services) >= 2
    assert any(s["name"] == "list-test-service-1" for s in services)
    assert any(s["name"] == "list-test-service-2" for s in services)

    # List services by type
    services = await client.list_services("type-a")

    assert len(services) >= 1
    assert any(s["name"] == "list-test-service-1" for s in services)
    assert not any(s["name"] == "list-test-service-2" for s in services)


@pytest.mark.asyncio
async def test_client_health_check(client, server):
    """Test health check."""
    health = await client.health_check()
    assert health is True


@pytest.mark.asyncio
async def test_client_caching(client, server):
    """Test client's service caching."""

    service_id = await client.register("cache-test-service", "localhost", 8080, service_type="cache-test")

    # Look up the service (should populate cache)
    service = await client.get_service(service_id)
    assert service is not None

    # Check if it's in the cache
    async with client._service_cache_lock:
        assert service_id in client._service_cache

    # Look up by type (should use cache when use_cache=True)
    with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
        # First call with use_cache=True should check cache
        service = await client.discover_service("cache-test", use_cache=True)
        assert service is not None
        assert service["id"] == service_id

        # Configure the mock to return a dictionary that matches what _send_request would return
        mock_send.return_value = {
            "success": True,
            "service": {
                "id": service_id,
                "name": "cache-test-service",
                "host": "localhost",
                "port": 8080,
                "type": "cache-test",
            },
        }

        # Second call with use_cache=False should make a request
        service = await client.discover_service("cache-test", use_cache=False)
        assert service is not None
        assert mock_send.called


@pytest.mark.asyncio
async def test_client_register_context(client, server, req_socket):
    """Test the register_context context manager."""

    # Use the context manager
    async with client.register_context(
        "context-test-service", "localhost", 8080, service_type="context-test"
    ) as service_id:
        # Verify the service was registered
        response = await send_request(
            MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
        )

        logger.info(f"----- In test_client_register_context: {response}")

        assert response["success"] is True
        assert response["service"]["name"] == "context-test-service"

    logger.info("----- In test_client_register_context: after context...")

    # After exiting the context, the service should be deregistered
    response = await send_request(
        MessageType.REQUEST_WITH_REPLY, req_socket, {"action": "get", "service_id": service_id}
    )

    assert response["success"] is False
