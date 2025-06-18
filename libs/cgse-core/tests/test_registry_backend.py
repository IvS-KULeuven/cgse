"""
Unit tests for AsyncRegistryBackend implementations using a unified fixture approach.

This file contains pytest tests for both AsyncSQLiteBackend and AsyncInMemoryBackend.
These tests verify that the backends correctly implement the AsyncRegistryBackend protocol
and functions as expected.

To run:
    uv run pytest -v -s test_registry_backend.py
"""

import asyncio
import logging
import os
import time
from typing import Any
from typing import Dict
from typing import List

import pytest
import pytest_asyncio

# Import the backend implementations
from egse.registry.backend import AsyncInMemoryBackend
from egse.registry.backend import AsyncSQLiteBackend

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-12s %(lineno)5d:%(module)-20s %(message)s",
)

logger = logging.getLogger("test_registry_backend")

# Use pytest-asyncio for async tests by default
pytestmark = pytest.mark.asyncio

# Test data
TEST_DB_PATH = "test_registry.db"
TEST_SERVICE_ID = "test-service-1"
TEST_SERVICE_INFO = {
    "name": "test-service",
    "host": "localhost",
    "port": 8080,
    "type": "test",
    "metadata": {"version": "1.0.0"},
    "tags": ["test", "unit-test"],
}


@pytest_asyncio.fixture(params=["sqlite", "memory"])
async def backend(request):
    """
    Parameterized fixture that yields initialized backends of different types.

    This fixture will run all tests twice - once with the SQLite backend and once
    with the in-memory backend.
    """
    if request.param == "sqlite":
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

        backend = AsyncSQLiteBackend(TEST_DB_PATH)
        await backend.initialize()

        yield backend

        await backend.close()
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    elif request.param == "memory":
        backend = AsyncInMemoryBackend()
        await backend.initialize()

        yield backend

        await backend.close()


# no need to specify @pytest.mark.asyncio because we have defined the `pytestmark` variable above.


async def test_register_service_plain(backend):
    success = await backend.register("my-unique-service-id-1234", {})
    assert success, "Service registration should succeed"

    service = await backend.get_service("my-unique-service-id-1234")

    logger.info(f"{success = }")
    logger.info(f"{service = }")


async def test_register_service_with_type(backend):
    success = await backend.register("my-unique-service-id-1234", {"type": "plain"})
    assert success, "Service registration should succeed"

    service = await backend.get_service("my-unique-service-id-1234")

    logger.info(f"{success = }")
    logger.info(f"{service = }")


async def test_register_service(backend):
    """Test registering a service."""

    success = await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)
    assert success, "Service registration should succeed"

    # Verify the service was registered
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service is not None, "Should be able to retrieve the registered service"
    assert service["id"] == TEST_SERVICE_ID, "Service ID should match"
    assert service["name"] == TEST_SERVICE_INFO["name"], "Service name should match"
    assert service["host"] == TEST_SERVICE_INFO["host"], "Service host should match"
    assert service["port"] == TEST_SERVICE_INFO["port"], "Service port should match"
    assert "test" in service["tags"], "Service tags should be preserved"
    assert service["health"] == "passing", "New service should have passing health"


async def test_deregister_service(backend):
    """Test de-registering a service."""

    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)

    success = await backend.deregister(TEST_SERVICE_ID)
    assert success, "Service de-registration should succeed"

    # Verify the service was deregistered
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service is None, "Deregistered service should not be found"


async def test_renew_service(backend):
    """Test renewing a service's TTL."""

    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO, ttl=5)

    # Get the initial heartbeat time
    service = await backend.get_service(TEST_SERVICE_ID)
    initial_heartbeat = service["last_heartbeat"]

    # Wait a bit
    await asyncio.sleep(1)

    # Renew the service
    success = await backend.renew(TEST_SERVICE_ID)
    assert success, "Service renewal should succeed"

    # Get the updated heartbeat time
    service = await backend.get_service(TEST_SERVICE_ID)
    updated_heartbeat = service["last_heartbeat"]

    # Check that the heartbeat was updated
    assert updated_heartbeat > initial_heartbeat, "Heartbeat time should be updated after renewal"


async def test_list_services(backend):
    """Test listing all services."""

    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)
    await backend.register(
        service_id="test-service-2",
        service_info={**TEST_SERVICE_INFO, "name": "second-test-service", "port": 8081, "type": "api"},
    )

    services = await backend.list_services()
    assert len(services) == 2, "Should list all registered services"

    # Check names to ensure we have both services
    service_names = [s["name"] for s in services]
    assert "test-service" in service_names, "First service should be in the list"
    assert "second-test-service" in service_names, "Second service should be in the list"


async def test_list_services_by_type(backend):
    """Test listing services filtered by type."""

    # Register services with different types
    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)  # this service is of type 'test'
    await backend.register(
        "test-service-2",
        {**TEST_SERVICE_INFO, "name": "second-test-service", "port": 8081, "type": "api", "tags": ["api"]},
    )

    # List services filtered by type
    test_services = await backend.list_services("test")
    assert len(test_services) == 1, "Should filter services by 'test' type"
    assert test_services[0]["name"] == "test-service", "Should find the correct service"

    api_services = await backend.list_services("api")
    assert len(api_services) == 1, "Should filter services by 'api' type"
    assert api_services[0]["name"] == "second-test-service", "Should find the correct service"


async def test_discover_service(backend):
    """Test discovering a service by type."""
    # Register a service
    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)

    # Discover a service by type
    service = await backend.discover_service("test")
    assert service is not None, "Should discover a service of type 'test'"
    assert service["name"] == "test-service", "Should discover the correct service"

    # Try to discover a non-existent service type
    service = await backend.discover_service("nonexistent")
    assert service is None, "Should not discover a service of non-existent type"


async def test_clean_expired_services(backend):
    """Test cleaning up expired services."""
    # Register a service with short TTL
    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO, ttl=1)

    # Verify the service exists
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service is not None, "Service should exist initially"

    # Wait for the service to expire
    await asyncio.sleep(2)

    # Clean expired services
    expired_ids = await backend.clean_expired_services()
    assert TEST_SERVICE_ID in expired_ids, "Service should be in the list of expired IDs"

    # Verify the service was removed
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service is None, "Expired service should be removed"


async def test_health_status(backend):
    """Test health status calculation."""
    # Register a service with short TTL
    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO, ttl=2)

    # Verify initial health is passing
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service["health"] == "passing", "Initial health should be passing"

    # Wait for the service to become critical
    await asyncio.sleep(3)

    # Verify health is now critical
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service is not None, "Service should still exist"
    assert service["health"] == "critical", "Health should become critical after TTL expires"


# Edge cases and error handling


async def test_register_existing_service(backend):
    """Test registering a service with an ID that already exists."""
    # Register a service
    await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)

    # Register a different service with the same ID
    updated_info = {**TEST_SERVICE_INFO, "port": 9090, "metadata": {"version": "2.0.0"}}
    success = await backend.register(TEST_SERVICE_ID, updated_info)
    assert success, "Registering an existing service should succeed (update)"

    # Verify the service was updated
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service["port"] == 9090, "Service port should be updated"
    assert service["metadata"]["version"] == "2.0.0", "Service metadata should be updated"


async def test_deregister_nonexistent_service(backend):
    """Test de-registering a service that doesn't exist."""
    success = await backend.deregister("nonexistent-service")
    assert not success, "De-registering a nonexistent service should fail"


async def test_renew_nonexistent_service(backend):
    """Test renewing a service that doesn't exist."""
    success = await backend.renew("nonexistent-service")
    assert not success, "Renewing a nonexistent service should fail"


async def test_discover_with_multiple_services(backend):
    """Test discovery with multiple services of the same type."""
    # Register multiple services of the same type
    await backend.register("test-service-1", {**TEST_SERVICE_INFO, "name": "test-service-1"})
    await backend.register("test-service-2", {**TEST_SERVICE_INFO, "name": "test-service-2"})

    # Keep track of discovered services
    discovered_services = set()

    # Run multiple discoveries and verify load balancing
    for _ in range(10):
        service = await backend.discover_service("test")
        assert service is not None, "Should discover a service"
        discovered_services.add(service["name"])

    # We should have discovered both services
    assert len(discovered_services) == 2, "Should have discovered both services"
    assert "test-service-1" in discovered_services, "First service should be discovered"
    assert "test-service-2" in discovered_services, "Second service should be discovered"


# Test concurrent operations
async def test_concurrent_operations(backend):
    """Test concurrent operations on the backend."""
    # Number of concurrent operations
    num_concurrent = 20

    # Function to register a service
    async def register_task(i: int) -> bool:
        service_id = f"concurrent-service-{i}"
        service_info = {
            "name": f"concurrent-service-{i}",
            "host": "localhost",
            "port": 9000 + i,
            "type": "concurrent",
            "tags": ["concurrent"],
        }
        return await backend.register(service_id, service_info)

    # Function to list services multiple times
    async def list_task(i: int) -> List[Dict[str, Any]]:
        return await backend.list_services()

    # Run concurrent registrations
    start_time = time.time()
    register_tasks = [register_task(i) for i in range(num_concurrent)]
    register_results = await asyncio.gather(*register_tasks)
    register_time = time.time() - start_time

    # All registrations should succeed
    assert all(register_results), "All concurrent registrations should succeed"

    # Run concurrent list operations
    start_time = time.time()
    list_tasks = [list_task(i) for i in range(num_concurrent)]
    list_results = await asyncio.gather(*list_tasks)
    list_time = time.time() - start_time

    # All list operations should return the same count
    counts = [len(result) for result in list_results]
    assert all(count >= num_concurrent for count in counts), "All list operations should find all services"

    # Output concurrency metrics
    print(f"\nConcurrency test results for {backend.__class__.__name__}:")
    print(f"  {num_concurrent} concurrent registrations: {register_time:.4f} seconds")
    print(f"  {num_concurrent} concurrent list operations: {list_time:.4f} seconds")
    print(f"  Total time: {register_time + list_time:.4f} seconds")


# Performance tests
async def test_backend_performance(backend):
    """Test backend performance with many operations."""
    # Number of services to register
    num_services = 100

    # Register many services
    start_time = time.time()
    for i in range(num_services):
        service_id = f"perf-service-{i}"
        service_info = {
            "name": f"performance-service-{i}",
            "host": "localhost",
            "port": 8000 + i,
            "type": "performance",
            "tags": ["performance", f"group-{i % 10}"],
        }
        await backend.register(service_id, service_info)
    register_time = time.time() - start_time

    # List all services
    start_time = time.time()
    services = await backend.list_services()
    list_time = time.time() - start_time
    assert len(services) >= num_services, f"Should list all {num_services} registered services"

    # Get many services
    start_time = time.time()
    for i in range(num_services):
        service_id = f"perf-service-{i}"
        service = await backend.get_service(service_id)
        assert service is not None, f"Should find service {service_id}"
    get_time = time.time() - start_time

    # Discover many times
    start_time = time.time()
    for _ in range(100):  # 100 discoveries
        service = await backend.discover_service("performance")
        assert service is not None, "Should discover a performance service"
    discover_time = time.time() - start_time

    # Output performance metrics
    print(f"\nPerformance test results for {backend.__class__.__name__}:")
    print(f"  Register {num_services} services: {register_time:.4f} seconds")
    print(f"  List all services: {list_time:.4f} seconds")
    print(f"  Get {num_services} services: {get_time:.4f} seconds")
    print(f"  Discover 100 times: {discover_time:.4f} seconds")
    print(f"  Total time: {register_time + list_time + get_time + discover_time:.4f} seconds")


# SQLite-specific tests need their own fixture since they don't use the parameterization
@pytest.fixture
async def sqlite_only():
    """Fixture for SQLite-specific tests."""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    yield

    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.mark.parametrize("drop_db", [True, False])
async def test_sqlite_persistence(sqlite_only, drop_db: bool) -> None:
    """Test SQLite backend persistence across restarts."""
    # First database connection - register a service
    backend1 = AsyncSQLiteBackend(TEST_DB_PATH)
    await backend1.initialize()
    await backend1.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)
    await backend1.close()

    # Optionally delete the database file to test resilience
    if drop_db and os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    # Second database connection - verify service exists
    backend2 = AsyncSQLiteBackend(TEST_DB_PATH)
    await backend2.initialize()

    if drop_db:
        # If we dropped the DB, service should not exist
        service = await backend2.get_service(TEST_SERVICE_ID)
        assert service is None, "Service should not exist after database was dropped"
    else:
        # If we kept the DB, service should exist
        service = await backend2.get_service(TEST_SERVICE_ID)
        assert service is not None, "Service should persist across database connections"
        assert service["name"] == TEST_SERVICE_INFO["name"], "Service details should persist"

    await backend2.close()


async def test_sqlite_backend_resilience(sqlite_only) -> None:
    """Test SQLite backend's resilience to disruptions."""
    # Create a backend without initializing
    backend = AsyncSQLiteBackend(TEST_DB_PATH)

    # Try operations before initialization (should fail gracefully)
    success = await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)
    assert not success, "Operations before initialization should fail gracefully"

    # Initialize the backend
    await backend.initialize()

    # Register a service
    success = await backend.register(TEST_SERVICE_ID, TEST_SERVICE_INFO)
    assert success, "Registration after initialization should succeed"

    # Close the backend
    await backend.close()

    # Try operations after closing (should fail gracefully)
    service = await backend.get_service(TEST_SERVICE_ID)
    assert service is None, "Operations after closing should fail gracefully"


async def test_protocol_implementation(backend):
    assert "implements the AsyncRegistryBackend protocol" in backend.__doc__
    assert backend.verify_protocol_compliance()
