"""Tests for the status report of synchronous and asynchronous control servers."""

import json
import threading
import uuid

import pytest
import zmq
from egse.process import ProcessStatus
from egse.zmq_ser import bind_address
from egse.zmq_ser import get_port_number

from egse.async_control import AsyncControlServer
from egse.control import ControlServer
from egse.protocol import CommandProtocol
from egse.services import ServiceProxy

CONTROL_SERVER_KEYS = {
    "name",
    "service_type",
    "device_id",
    "hostname",
    "device_commanding_port",
    "service_commanding_port",
    "monitoring_port",
}

PROCESS_KEYS = {
    "pid",
    "uptime_s",
    "uuid",
    "rss",
    "uss",
    "cpu_user_s",
    "cpu_system_s",
    "cpu_count",
    "cpu_percent",
}


class StatusTestProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__(control_server)
        self.fail = False

    def get_bind_address(self):
        return bind_address("tcp", 0)

    def get_status(self) -> dict:
        if self.fail:
            raise RuntimeError("device not connected")
        status = super().get_status()
        status.update({"extra": 42})
        return status

    def get_housekeeping(self) -> dict:
        return {}


class StatusTestControlServer(ControlServer):
    """A control server on dynamic ports that is not registered and does not serve."""

    def __init__(self):
        super().__init__(device_id="DEV-1")

        self.service_type = "STATUS_TEST"
        self.service_name = "status_test_cs"

        self.device_protocol = StatusTestProtocol(self)
        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

    def get_communication_protocol(self):
        return "tcp"

    def get_commanding_port(self):
        return 0

    def get_service_port(self):
        return 0

    def get_monitoring_port(self):
        return 0

    def close(self):
        for sock in (self.dev_ctrl_cmd_sock, self.dev_ctrl_service_sock, self.dev_ctrl_mon_sock):
            sock.close(linger=0)
        self.event_subscription.disconnect()
        self.registry.disconnect()


@pytest.fixture
def sync_server(monkeypatch):
    # The ProcessStatus of a ControlServer registers its metrics without a prefix in the global Prometheus registry,
    # which allows only one ControlServer per process. A unique prefix avoids clashes with other tests.
    monkeypatch.setattr(
        "egse.control.ProcessStatus", lambda: ProcessStatus(metrics_prefix=f"status_test_{uuid.uuid4().hex[:8]}")
    )
    server = StatusTestControlServer()
    yield server
    server.close()


def assert_common_layout(report: dict):
    assert report["schema_version"] == 1
    assert set(report["control_server"]) == CONTROL_SERVER_KEYS
    assert set(report["process"]) == PROCESS_KEYS
    assert isinstance(report["process"]["uuid"], str)
    assert "details" in report

    json.dumps(report)  # the report shall be JSON-safe


def test_sync_status_report(sync_server):
    report = sync_server.get_status_report()

    assert_common_layout(report)

    control_server = report["control_server"]
    assert control_server["name"] == "status_test_cs"
    assert control_server["service_type"] == "STATUS_TEST"
    assert control_server["device_id"] == "DEV-1"
    assert control_server["service_commanding_port"] == get_port_number(sync_server.dev_ctrl_service_sock)
    assert control_server["service_commanding_port"] > 0

    # Only the entries that the device protocol adds to the base status.
    assert report["details"] == {"extra": 42}


def test_sync_status_report_when_details_fail(sync_server):
    sync_server.device_protocol.fail = True

    report = sync_server.get_status_report()

    assert_common_layout(report)
    assert report["details"] == {"error": "RuntimeError: device not connected"}


def test_sync_status_report_through_service_proxy(sync_server):
    stop = threading.Event()

    def serve_service_requests():
        while not stop.is_set():
            if sync_server.dev_ctrl_service_sock.poll(50, zmq.POLLIN):
                sync_server.service_protocol.execute()

    thread = threading.Thread(target=serve_service_requests, daemon=True)
    thread.start()

    try:
        port = get_port_number(sync_server.dev_ctrl_service_sock)
        with ServiceProxy(hostname="localhost", port=port) as proxy:
            report = proxy.get_status_report()
    finally:
        stop.set()
        thread.join(timeout=2.0)

    assert_common_layout(report)
    assert report["control_server"]["device_id"] == "DEV-1"
    assert report["details"] == {"extra": 42}


def test_async_status_report():
    server = AsyncControlServer()

    report = server.get_status_report()

    assert_common_layout(report)
    assert report["control_server"]["service_type"] == server.service_type
    assert report["control_server"]["device_id"] is None
    assert "service_command_handlers" in report["details"]
    assert "status_report" in report["details"]["service_command_handlers"]

    # The status on the monitoring channel keeps its original process keys.
    assert "PID" in server.get_status()["process"]


def test_configuration_manager_status_details():
    from types import SimpleNamespace

    from egse.response import Success

    from egse.confman.confman_cs import ConfigurationManagerControlServer

    def make_server(obsid):
        controller = SimpleNamespace(
            get_obsid=lambda: Success("obsid", obsid),
            get_setup_id=lambda: 42,
            get_site_id=lambda: "LAB",
        )
        return SimpleNamespace(device_protocol=SimpleNamespace(controller=controller))

    # Called on a stand-in, so no Configuration Manager is started or registered.
    details = ConfigurationManagerControlServer.get_status_details(make_server(None))
    assert details == {"obsid_active": False, "obsid": None, "setup_id": 42, "site_id": "LAB"}

    details = ConfigurationManagerControlServer.get_status_details(make_server("LAB_00042_00012"))
    assert details["obsid_active"] is True
    assert details["obsid"] == "LAB_00042_00012"
    json.dumps(details)


def test_storage_manager_status_details():
    from types import SimpleNamespace

    from egse.storage.storage_cs import StorageControlServer

    controller = SimpleNamespace(
        get_obsid=lambda: None,
        get_disk_usage=lambda: (1000, 400, 600),
        get_storage_location=lambda: "/data/LAB",
        get_loaded_setup_id=lambda: 42,
        get_registry_names=lambda: ["CM", "DAQ6510"],
    )
    server = SimpleNamespace(device_protocol=SimpleNamespace(controller=controller))

    # Called on a stand-in, so no Storage Manager is started or registered.
    details = StorageControlServer.get_status_details(server)

    assert details == {
        "storage_location": "/data/LAB",
        "disk_usage": {"total": 1000, "used": 400, "free": 600},
        "loaded_setup_id": 42,
        "obsid": None,
        "registrations": ["CM", "DAQ6510"],
    }
    json.dumps(details)


def test_process_manager_status_details():
    from types import SimpleNamespace

    from egse.procman.procman_cs import ProcessManagerControlServer

    controller = SimpleNamespace(get_core_processes=lambda: {"Storage Manager": "SM_CS"})
    server = SimpleNamespace(device_protocol=SimpleNamespace(controller=controller))

    # Called on a stand-in, so no Process Manager is started or registered.
    details = ProcessManagerControlServer.get_status_details(server)

    assert details == {"core_processes": {"Storage Manager": "SM_CS"}}
    json.dumps(details)
