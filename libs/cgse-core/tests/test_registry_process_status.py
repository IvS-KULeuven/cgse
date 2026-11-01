"""Tests for the process information in the registry: PID and start time at registration, status with heartbeats."""

import asyncio
import os
import sqlite3

import psutil
import pytest
import pytest_asyncio
from egse.process import process_identity
from egse.process import process_status
from egse.system import get_host_ip

from egse.registry.backend import AsyncInMemoryBackend
from egse.registry.backend import AsyncSQLiteBackend
from egse.registry.client import AsyncRegistryClient
from egse.registry.server import AsyncRegistryServer

REQ_PORT, PUB_PORT, HB_PORT = 15576, 15577, 15578

SERVICE_INFO = {"name": "test_cs", "host": "127.0.0.1", "port": 9999, "type": "TEST_CS", "metadata": {"pid": 42}}
STATUS = {"pid": 42, "uptime_s": 12.0, "rss": 1024, "cpu_user_s": 0.5, "cpu_system_s": 0.1, "cpu_percent": 3.0}


def test_process_identity_and_status():
    identity = process_identity()
    assert identity == {"pid": os.getpid(), "start_time": psutil.Process().create_time()}

    process = psutil.Process()
    status = process_status(process)
    assert set(status) == {"pid", "uptime_s", "rss", "cpu_user_s", "cpu_system_s", "cpu_percent"}
    assert status["pid"] == os.getpid() and status["uptime_s"] > 0 and status["rss"] > 0


@pytest_asyncio.fixture(params=["memory", "sqlite"])
async def backend(request, tmp_path):
    backend = AsyncInMemoryBackend() if request.param == "memory" else AsyncSQLiteBackend(str(tmp_path / "test.db"))
    await backend.initialize()
    yield backend
    await backend.close()


@pytest.mark.asyncio
async def test_backend_keeps_the_status_of_the_heartbeat(backend):
    assert await backend.register("id-1", SERVICE_INFO)
    assert (await backend.get_service("id-1"))["status"] == {}

    assert await backend.renew("id-1", status=STATUS)
    assert (await backend.get_service("id-1"))["status"] == STATUS
    assert (await backend.list_services())[0]["status"] == STATUS

    assert await backend.renew("id-1")  # a heartbeat without status (an older client) keeps the last status
    assert (await backend.get_service("id-1"))["status"] == STATUS


@pytest.mark.asyncio
async def test_sqlite_database_without_status_column_is_migrated(tmp_path):
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as connection:  # the table as created by an earlier version
        connection.execute(
            "CREATE TABLE services (id TEXT PRIMARY KEY, name TEXT NOT NULL, host TEXT NOT NULL, "
            "port INTEGER NOT NULL, metadata TEXT, ttl INTEGER NOT NULL, last_heartbeat INTEGER NOT NULL, tags TEXT)"
        )
        connection.execute(
            "INSERT INTO services VALUES ('id-1', 'old_cs', '127.0.0.1', 9998, '{}', 30, 4102444800, '[]')"
        )

    backend = AsyncSQLiteBackend(str(db_path))
    await backend.initialize()
    try:
        assert (await backend.get_service("id-1"))["status"] == {}
        assert await backend.renew("id-1", status=STATUS)
        assert (await backend.get_service("id-1"))["status"] == STATUS
    finally:
        await backend.close()


@pytest_asyncio.fixture
async def registry():
    backend = AsyncInMemoryBackend()
    await backend.initialize()
    server = AsyncRegistryServer(req_port=REQ_PORT, pub_port=PUB_PORT, hb_port=HB_PORT, backend=backend)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.5)
    yield server
    server.stop()
    await asyncio.gather(task, return_exceptions=True)


def client():
    return AsyncRegistryClient(
        registry_req_endpoint=f"tcp://localhost:{REQ_PORT}",
        registry_sub_endpoint=f"tcp://localhost:{PUB_PORT}",
        registry_hb_endpoint=f"tcp://localhost:{HB_PORT}",
        timeout=2.0,
    )


@pytest.mark.asyncio
async def test_registration_and_heartbeat_carry_the_process_information(registry):
    async with client() as service:
        # The actual host IP, with another address the heartbeat loop would re-register instead of renewing
        service_id = await service.register(
            name="test_cs", host=get_host_ip(), port=9999, service_type="TEST_CS", metadata={"service_port": 9998}
        )
        assert service_id

        record = await service.get_service(service_id)
        assert record["metadata"]["pid"] == os.getpid()  # added by the client at registration
        assert record["metadata"]["start_time"] == psutil.Process().create_time()
        assert record["metadata"]["service_port"] == 9998
        assert record["status"] == {}

        await service.start_heartbeat(interval=1)
        await asyncio.sleep(0.5)  # the first heartbeat is sent right away

        (record,) = await service.list_services("TEST_CS")
        assert record["status"]["pid"] == os.getpid()
        assert set(record["status"]) == {"pid", "uptime_s", "rss", "cpu_user_s", "cpu_system_s", "cpu_percent"}

        await service.stop_heartbeat()
        await service.deregister()


@pytest.mark.asyncio
async def test_registry_info_has_its_own_process_information(registry):
    async with client() as tool:
        info = await tool.server_status()

    assert info["pid"] == os.getpid()  # the registry runs in this test process
    assert info["start_time"] == psutil.Process().create_time()
    assert info["process"]["pid"] == os.getpid()
    assert info["status"] == "ok"
