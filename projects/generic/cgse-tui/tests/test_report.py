"""Tests for the status report request, with fake sync and async clients: no services are needed."""

import egse.async_control
import pytest

from cgse_tui.data import report
from cgse_tui.data.model import ServiceInfo

SYNC_REPORT = {"schema_version": 1, "details": {"kind": "sync"}}
ASYNC_REPORT = {"schema_version": 1, "details": {"kind": "async"}}


@pytest.fixture
def clients(monkeypatch):
    """Fake sync and async requests; `calls` records which ones were made, `answers` sets what they return."""
    state = {"calls": [], "answers": {"sync": SYNC_REPORT, "async": ASYNC_REPORT}}

    def sync_report(hostname, port, timeout):
        state["calls"].append("sync")
        answer = state["answers"]["sync"]
        if isinstance(answer, Exception):
            raise answer
        return answer

    class FakeAsyncClient:
        def __init__(self, service_type=None, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def get_status_report(self):
            state["calls"].append("async")
            return state["answers"]["async"]

    monkeypatch.setattr(report, "_sync_status_report", sync_report)
    monkeypatch.setattr(egse.async_control, "AsyncControlClient", FakeAsyncClient)
    return state


def control_server(server_kind=None, service_port=6112):
    return ServiceInfo(
        name="cm_cs", service_type="CM_CS", host="localhost", server_kind=server_kind, service_port=service_port
    )


async def test_known_kind_uses_only_that_client(clients):
    assert await report.request_status_report(control_server("async")) == ASYNC_REPORT
    assert clients["calls"] == ["async"]


async def test_without_server_kind_sync_is_tried_first(clients):
    """A server started with a version that doesn't register `server_kind`."""
    service = control_server(None)

    assert await report.request_status_report(service) == SYNC_REPORT
    assert clients["calls"] == ["sync"]
    assert service.server_kind == "sync"  # remembered, the next request doesn't probe


async def test_without_server_kind_async_when_sync_fails(clients):
    clients["answers"]["sync"] = ConnectionError("Proxy is not connected when entering the context.")
    service = control_server(None)

    assert await report.request_status_report(service) == ASYNC_REPORT
    assert clients["calls"] == ["sync", "async"]
    assert service.server_kind == "async"


async def test_without_server_kind_and_no_answer(clients):
    clients["answers"]["sync"] = ConnectionError("not connected")
    clients["answers"]["async"] = None
    service = control_server(None)

    assert await report.request_status_report(service) is None
    assert service.server_kind is None  # not known yet, probed again next time


async def test_no_service_port_is_not_a_control_server(clients):
    assert await report.request_status_report(control_server(None, service_port=None)) is None
    assert clients["calls"] == []


def test_command_status_asks_a_command_server():
    """The logger and facility_hk answer the pickled string command "status"."""
    import pickle
    import threading

    import zmq

    socket = zmq.Context.instance().socket(zmq.REP)
    port = socket.bind_to_random_port("tcp://127.0.0.1")

    def command_server():
        command = pickle.loads(socket.recv())
        socket.send(pickle.dumps({"status": "ACK", "command": command}))

    thread = threading.Thread(target=command_server)
    thread.start()
    try:
        assert report._command_status("127.0.0.1", port, timeout=2.0) == {"status": "ACK", "command": "status"}
    finally:
        thread.join(timeout=2.0)
        socket.close(linger=0)

    assert report._command_status("127.0.0.1", port, timeout=0.1) is None  # nobody answers


def test_custom_kind():
    from cgse_tui.data.services import custom_kind

    assert custom_kind(ServiceInfo(name="facility_hk", service_type="facility_hk", server_kind="command")) == "command"
    assert custom_kind(ServiceInfo(name="nh_cs", service_type="NH_CS")) == "notifyhub"  # registered without kind
    assert custom_kind(ServiceInfo(name="cm_cs", service_type="CM_CS", server_kind="sync")) is None
