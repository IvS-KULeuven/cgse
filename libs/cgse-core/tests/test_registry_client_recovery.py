"""Tests for the recovery of the registry clients after timeouts, e.g. when the network was down (laptop lid closed)."""

import asyncio
import time

import pytest
import pytest_asyncio
from egse.system import get_host_ip

from egse.registry import MessageType
from egse.registry.backend import AsyncInMemoryBackend
from egse.registry.client import AsyncRegistryClient
from egse.registry.client import RegistryClient
from egse.registry.server import AsyncRegistryServer

REQ_PORT, PUB_PORT, HB_PORT = 15586, 15587, 15588

ENDPOINTS = dict(
    registry_req_endpoint=f"tcp://localhost:{REQ_PORT}",
    registry_sub_endpoint=f"tcp://localhost:{PUB_PORT}",
    registry_hb_endpoint=f"tcp://localhost:{HB_PORT}",
)


async def start_registry():
    backend = AsyncInMemoryBackend()
    await backend.initialize()
    server = AsyncRegistryServer(req_port=REQ_PORT, pub_port=PUB_PORT, hb_port=HB_PORT, backend=backend)
    task = asyncio.create_task(server.start())
    await asyncio.sleep(0.5)
    return server, task


async def stop_registry(server, task):
    server.stop()
    await asyncio.gather(task, return_exceptions=True)


@pytest_asyncio.fixture
async def registry():
    server, task = await start_registry()
    yield server
    await stop_registry(server, task)


@pytest.fixture
def slow_info(registry, monkeypatch):
    """The registry replies to an 'info' request after 0.3s."""
    handle_info = registry._handle_info

    async def slow_handle_info(request):
        await asyncio.sleep(0.3)
        return await handle_info(request)

    monkeypatch.setattr(registry, "_handle_info", slow_handle_info)


async def register(client: AsyncRegistryClient) -> str:
    # The actual host IP, with another address the heartbeat loop would re-register instead of renewing
    return await client.register(name="test_cs", host=get_host_ip(), port=9999, service_type="TEST_CS")


@pytest.mark.asyncio
async def test_async_request_after_a_timeout_gets_its_own_reply(registry, slow_info):
    async with AsyncRegistryClient(**ENDPOINTS, timeout=2.0) as client:
        service_id = await register(client)
        assert service_id

        # The reply to this request arrives after the timeout
        response = await client._send_request(MessageType.REQUEST_WITH_REPLY, {"action": "info"}, timeout=0.1)
        assert response == {"success": False, "error": "Request timed out"}
        await asyncio.sleep(0.5)

        # Without a new socket, this request would read the late reply to the 'info' request
        record = await client.get_service(service_id)
        assert record["id"] == service_id

        await client.deregister()


@pytest.mark.asyncio
async def test_sync_request_after_a_timeout_gets_its_own_reply(registry, slow_info):
    # The sync client blocks, it runs in a thread so the registry keeps serving in the event loop

    def scenario():
        with RegistryClient(**ENDPOINTS, timeout=2.0) as client:
            service_id = client.register(name="test_cs", host=get_host_ip(), port=9999, service_type="TEST_CS")
            assert service_id

            response = client._send_request(MessageType.REQUEST_WITH_REPLY, {"action": "info"}, timeout=0.1)
            assert response == {"success": False, "error": "Request timed out"}
            time.sleep(0.5)

            record = client.get_service(service_id)
            assert record["id"] == service_id

            client.deregister()

    await asyncio.to_thread(scenario)


@pytest.mark.asyncio
async def test_failed_reregistration_keeps_the_service_id(registry, monkeypatch):
    async with AsyncRegistryClient(**ENDPOINTS, timeout=2.0) as client:
        service_id = await register(client)

        async def reply_without_service_id(msg_type, request, timeout=None):
            return {"success": True}  # e.g. the reply to another request

        monkeypatch.setattr(client, "_send_request", reply_without_service_id)

        assert await client.reregister() is None
        assert client._service_id == service_id  # the heartbeat loop keeps running and retries

        monkeypatch.undo()
        await client.deregister()


@pytest.mark.asyncio
async def test_service_registers_again_after_the_registry_was_down():
    server, task = await start_registry()

    async with AsyncRegistryClient(**ENDPOINTS, timeout=1.0) as client:
        service_id = await register(client)
        await client.start_heartbeat(interval=1)

        # The registry is down for a few heartbeats: requests and heartbeats time out
        await stop_registry(server, task)
        await asyncio.sleep(4.0)

        # The new registry doesn't know the service (in-memory backend), the heartbeat loop registers it again
        server, task = await start_registry()
        try:
            for _ in range(20):
                record = await client.get_service(service_id)
                if record:
                    break
                await asyncio.sleep(0.5)

            assert record and record["id"] == service_id
            assert client._service_id == service_id

            await client.stop_heartbeat()
            await client.deregister()
        finally:
            await stop_registry(server, task)


@pytest.mark.asyncio
async def test_heartbeat_keeps_the_host_while_there_is_no_route(registry, monkeypatch):
    routed_ip = None  # e.g. the laptop lid was closed, the Wi-Fi is down
    monkeypatch.setattr("egse.registry.client.get_routed_host_ip", lambda: routed_ip)

    async with AsyncRegistryClient(**ENDPOINTS, timeout=2.0) as client:
        service_id = await client.register(name="test_cs", host="10.9.9.9", port=9999, service_type="TEST_CS")
        await client.start_heartbeat(interval=1)

        await asyncio.sleep(1.5)
        assert (await client.get_service(service_id))["host"] == "10.9.9.9"  # not re-registered

        routed_ip = "10.1.2.3"  # the network is back, with another address
        for _ in range(30):
            if (await client.get_service(service_id))["host"] == "10.1.2.3":
                break
            await asyncio.sleep(0.1)
        assert (await client.get_service(service_id))["host"] == "10.1.2.3"

        await client.stop_heartbeat()
        await client.deregister()


@pytest.mark.asyncio
async def test_heartbeat_waits_the_interval_while_the_registry_doesnt_answer(monkeypatch):
    client = AsyncRegistryClient(**ENDPOINTS)
    client._service_id, client._ttl = "test_cs-1", 30
    health_checks = []

    async def failed_heartbeat(request):
        return {"success": False, "error": "Heartbeat request timed out"}

    async def no_registry():
        health_checks.append(1)
        return False

    monkeypatch.setattr(client, "_send_heartbeat", failed_heartbeat)
    monkeypatch.setattr(client, "health_check", no_registry)

    await client.start_heartbeat(interval=0.1)
    await asyncio.sleep(0.45)
    await client.stop_heartbeat()

    assert 3 <= len(health_checks) <= 6  # one per interval, not as fast as the failures come back


def test_sync_client_sends_one_request_at_a_time(monkeypatch):
    import threading

    client = RegistryClient(**ENDPOINTS)
    active, overlaps = [], []

    def request(msg_type, request, timeout=None):
        active.append(1)
        overlaps.append(len(active) > 1)
        time.sleep(0.05)
        active.pop()
        return {"success": True}

    monkeypatch.setattr(client, "_send_request_locked", request)

    # e.g. the main thread and the heartbeat thread (health check, re-registration)
    threads = [
        threading.Thread(target=client._send_request, args=(MessageType.REQUEST_WITH_REPLY, {"action": "health"}))
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert overlaps == [False] * 4
