"""Tests for the collector, with a fake registry, fake monitoring and fake requests: no services are needed."""

import asyncio
import logging

from cgse_tui.data.collector import Collector
from cgse_tui.data.model import ServiceState
from cgse_tui.data.monitor import process_fields
from cgse_tui.data.services import REGISTRY_SERVICE_TYPE

SYNC_MONITORING = {
    "timestamp": "…",
    "delay": 1000,
    "PID": 42,
    "Up": 12.5,
    "CPU%": 3.0,
    "CPU User": 1.5,
    "CPU System": 0.5,
    "RSS": 1024,
    "USS": 768,
    "obsid": None,
}
ASYNC_MONITORING = {"schema_version": 1, "delay": 2000, "process": {"PID": 43, "Up": 7.0, "CPU%": 1.0, "RSS": 2048}}

REPORT = {
    "schema_version": 1,
    "control_server": {"device_id": "AWG-01"},
    "process": {"pid": 42, "uptime_s": 10.0, "cpu_percent": 2.0, "rss": 512, "uss": 256},
    "device": {"connected": True, "sim_mode": True},
    "details": {},
}


def record(service_type, name=None, host="10.0.0.1", port=1000, **metadata):
    return {
        "name": name or service_type.lower(),
        "host": host,
        "port": port,
        "metadata": {"type": service_type, **metadata},
    }


class FakeRegistry:
    def __init__(self):
        self.healthy = True
        self.records = []

    async def health_check(self):
        return self.healthy

    async def list_services(self, service_type=None):
        return list(self.records)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Fakes:
    """Records the subscriptions and requests of the collector, and lets the test publish monitoring messages."""

    def __init__(self):
        self.subscriptions = {}  # endpoint -> callback
        self.cancelled = []
        self.reports = {}  # service type -> report
        self.custom = {}  # service type -> status

    async def subscribe(self, endpoint, on_status):
        self.subscriptions[endpoint] = on_status
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.append(endpoint)
            raise

    async def request_report(self, service, timeout):
        return self.reports.get(service.service_type)

    async def request_custom_status(self, service, timeout):
        return self.custom.get(service.service_type)


def make_collector(known=None):
    registry, fakes, clock = FakeRegistry(), Fakes(), FakeClock()
    collector = Collector(
        registry=registry,
        known_services={REGISTRY_SERVICE_TYPE: "Service Registry", "SM_CS": "Storage Manager"}
        if known is None
        else known,
        subscribe=fakes.subscribe,
        request_report=fakes.request_report,
        request_custom_status=fakes.request_custom_status,
        clock=clock,
    )
    return collector, registry, fakes, clock


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


def by_type(collector):
    return {service.service_type: service for service in collector.snapshot()}


def test_process_fields_sync_and_async():
    assert process_fields(SYNC_MONITORING) == {
        "pid": 42,
        "uptime_s": 12.5,
        "cpu_percent": 3.0,
        "cpu_user_s": 1.5,
        "cpu_system_s": 0.5,
        "rss": 1024,
        "uss": 768,
        "interval_s": 1.0,
    }
    assert process_fields(ASYNC_MONITORING)["pid"] == 43
    assert process_fields(ASYNC_MONITORING)["interval_s"] == 2.0


async def test_known_services_are_inactive_before_registration():
    collector, registry, fakes, clock = make_collector()
    registry.healthy = False

    await collector.poll()

    services = by_type(collector)
    assert services["SM_CS"].state is ServiceState.INACTIVE
    assert services["SM_CS"].name == "Storage Manager"
    assert services[REGISTRY_SERVICE_TYPE].state is ServiceState.INACTIVE


async def test_control_server_is_followed_on_its_monitoring_port():
    collector, registry, fakes, clock = make_collector()
    registry.records = [record("AWG1", service_port=2001, monitoring_port=2002, server_kind="sync")]
    fakes.reports["AWG1"] = REPORT
    fakes.custom[REGISTRY_SERVICE_TYPE] = {"success": True, "status": "ok"}

    await collector.poll()
    await settle()

    assert "tcp://10.0.0.1:2002" in fakes.subscriptions
    awg = by_type(collector)["AWG1"]
    assert awg.state is ServiceState.OK  # the status report arrived
    assert (awg.connected, awg.sim_mode) == (True, True)
    assert awg.pid == 42 and awg.rss == 512 and awg.uss == 256  # from the report, until the first monitoring message
    assert awg.device_id == "AWG-01"  # from the report, the registration has no device_id
    assert by_type(collector)[REGISTRY_SERVICE_TYPE].state is ServiceState.OK

    fakes.subscriptions["tcp://10.0.0.1:2002"](SYNC_MONITORING)
    awg = by_type(collector)["AWG1"]
    assert (awg.pid, awg.uptime_s, awg.cpu_percent, awg.rss) == (42, 12.5, 3.0, 1024)
    assert (awg.cpu_user_s, awg.cpu_system_s, awg.uss) == (1.5, 0.5, 768)

    clock.t += 4.9
    assert by_type(collector)["AWG1"].state is ServiceState.OK
    clock.t += 0.2  # more than 5 s without a monitoring message
    assert by_type(collector)["AWG1"].state is ServiceState.STALE

    fakes.subscriptions["tcp://10.0.0.1:2002"](SYNC_MONITORING)
    assert by_type(collector)["AWG1"].state is ServiceState.OK

    await collector.stop()


async def test_slow_publisher_gets_a_longer_stale_time():
    collector, registry, fakes, clock = make_collector()
    registry.records = [record("TVAC", service_port=3001, monitoring_port=3002, server_kind="async")]

    await collector.poll()
    await settle()
    fakes.subscriptions["tcp://10.0.0.1:3002"](ASYNC_MONITORING)  # published every 2 s

    clock.t += 5.9
    assert by_type(collector)["TVAC"].state is ServiceState.OK
    clock.t += 0.2
    assert by_type(collector)["TVAC"].state is ServiceState.STALE

    await collector.stop()


async def test_service_without_information_is_unknown():
    collector, registry, fakes, clock = make_collector()
    registry.records = [record("DAQ6510", service_port=4001, monitoring_port=4002, server_kind="async")]

    await collector.poll()
    await settle()

    assert by_type(collector)["DAQ6510"].state is ServiceState.UNKNOWN

    await collector.stop()


async def test_deregistration():
    collector, registry, fakes, clock = make_collector()
    registry.records = [
        record("SM_CS", name="sm_cs", service_port=5001, monitoring_port=5002, server_kind="sync"),
        record("AWG1", service_port=2001, monitoring_port=2002, server_kind="sync"),
    ]
    await collector.poll()
    await settle()
    fakes.subscriptions["tcp://10.0.0.1:5002"](SYNC_MONITORING)
    assert by_type(collector)["SM_CS"].state is ServiceState.OK

    registry.records = []
    await collector.poll()
    await settle()

    services = by_type(collector)
    assert "AWG1" not in services  # not a known service: removed
    assert services["SM_CS"].state is ServiceState.INACTIVE  # core service: stays, without process information
    assert services["SM_CS"].name == "Storage Manager" and services["SM_CS"].pid is None
    assert set(fakes.cancelled) == {"tcp://10.0.0.1:2002", "tcp://10.0.0.1:5002"}

    await collector.stop()


async def test_restart_with_new_ports_follows_the_new_monitoring_port():
    collector, registry, fakes, clock = make_collector()
    registry.records = [record("AWG1", service_port=2001, monitoring_port=2002, server_kind="sync")]
    await collector.poll()
    await settle()

    registry.records = [record("AWG1", service_port=2101, monitoring_port=2102, server_kind="sync")]
    await collector.poll()
    await settle()

    assert "tcp://10.0.0.1:2002" in fakes.cancelled
    assert "tcp://10.0.0.1:2102" in fakes.subscriptions

    await collector.stop()


async def test_custom_servers_are_polled():
    collector, registry, fakes, clock = make_collector(known={REGISTRY_SERVICE_TYPE: "Service Registry"})
    registry.records = [record("NH_CS", name="nh_cs", port=6001, pub_port=6002)]
    fakes.custom["NH_CS"] = {"success": True, "status": "ok", "statistics": {"events_received": 3}}

    await collector.poll()
    await settle()

    nh = by_type(collector)["NH_CS"]
    assert nh.state is ServiceState.OK
    assert nh.report["statistics"]["events_received"] == 3
    assert nh.has_device is False
    assert not fakes.subscriptions  # no monitoring port

    fakes.custom.pop("NH_CS")  # stops answering
    clock.t += 7.9  # three polls of 2 s plus one request timeout of 2 s: one lost request is tolerated
    assert by_type(collector)["NH_CS"].state is ServiceState.OK
    clock.t += 0.2
    assert by_type(collector)["NH_CS"].state is ServiceState.STALE

    await collector.stop()


async def test_refresh_report():
    collector, registry, fakes, clock = make_collector()
    registry.records = [record("AWG1", service_port=2001, monitoring_port=2002, server_kind="sync")]
    await collector.poll()
    await settle()

    fakes.reports["AWG1"] = {**REPORT, "device": {"connected": False, "sim_mode": False}}
    service = await collector.refresh_report("AWG1")

    assert (service.connected, service.sim_mode) == (False, False)
    assert await collector.refresh_report("UNKNOWN_TYPE") is None

    await collector.stop()


async def test_every_poll_uses_a_new_registry_client(monkeypatch):
    """A reused AsyncRegistryClient can read the replies to earlier requests after a timeout, see `Collector`."""
    import egse.registry.client

    clients = []

    class FakeClient(FakeRegistry):
        def __init__(self, registry_req_endpoint=None, timeout=None):
            super().__init__()
            self.endpoint = registry_req_endpoint
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

    monkeypatch.setattr(egse.registry.client, "AsyncRegistryClient", FakeClient)
    fakes = Fakes()
    collector = Collector(
        registry_endpoint="tcp://registry-host:6100",
        known_services={REGISTRY_SERVICE_TYPE: "Service Registry"},
        subscribe=fakes.subscribe,
        request_report=fakes.request_report,
        request_custom_status=fakes.request_custom_status,
    )

    await collector.poll()
    await collector.poll()

    assert len(clients) == 2 and clients[0] is not clients[1]
    assert clients[0].endpoint == "tcp://registry-host:6100"
    registry_row = collector.services[REGISTRY_SERVICE_TYPE]
    assert (registry_row.host, registry_row.port) == ("registry-host", 6100)

    await collector.stop()


async def test_state_changes_are_logged_and_requests_are_quiet(caplog):
    from cgse_tui.logs import BufferedLogHandler

    collector, registry, fakes, clock = make_collector(known={REGISTRY_SERVICE_TYPE: "Service Registry"})
    registry.records = [record("NH_CS", name="nh_cs", port=6001)]

    async def failing_custom_status(service, timeout):
        logging.getLogger("egse.notifyhub").warning("Request timed out after 2.00s")
        return None

    collector._request_custom_status = failing_custom_status
    handler = BufferedLogHandler()
    logging.getLogger().addHandler(handler)
    try:
        with caplog.at_level(logging.INFO, logger="cgse_tui"):
            await collector.poll()
            await settle()
            collector.snapshot()  # first state of nh_cs: not logged
            assert by_type(collector)["NH_CS"].state is ServiceState.UNKNOWN

            clock.t += 10  # registered, but never answered
            collector.snapshot()
    finally:
        logging.getLogger().removeHandler(handler)

    assert [r.getMessage() for r in caplog.records if r.name.startswith("cgse_tui")] == ["nh_cs: unknown → stale"]
    texts = [message for _, message in handler.drain()]
    assert not any("Request timed out" in text for text in texts)  # logged during a request of the collector
    assert any("nh_cs: unknown → stale" in text for text in texts)

    await collector.stop()


async def test_registry_gone_drops_the_registrations():
    collector, registry, fakes, clock = make_collector()
    registry.records = [
        record("SM_CS", name="sm_cs", service_port=5001, monitoring_port=5002, server_kind="sync"),
        record("DAQ6510", service_port=4001, monitoring_port=4002, server_kind="async"),
    ]
    fakes.custom[REGISTRY_SERVICE_TYPE] = {"success": True, "status": "ok"}
    await collector.poll()
    await settle()
    fakes.subscriptions["tcp://10.0.0.1:5002"](SYNC_MONITORING)
    assert by_type(collector)[REGISTRY_SERVICE_TYPE].state is ServiceState.OK

    registry.healthy = False  # everything is stopped, including the registry
    fakes.custom.clear()

    clock.t += 20
    await collector.poll()
    services = by_type(collector)
    assert services[REGISTRY_SERVICE_TYPE].state is ServiceState.STALE  # a short gap
    assert services["SM_CS"].state is ServiceState.STALE  # still registered as far as we know
    assert "DAQ6510" in services

    clock.t += 11  # more than 30 s without an answer from the registry
    await collector.poll()
    await settle()
    services = by_type(collector)
    assert services[REGISTRY_SERVICE_TYPE].state is ServiceState.INACTIVE
    assert services["SM_CS"].state is ServiceState.INACTIVE
    assert "DAQ6510" not in services  # not a core service: removed
    assert {"tcp://10.0.0.1:5002", "tcp://10.0.0.1:4002"} <= set(fakes.cancelled)

    registry.healthy = True  # the registry and the services are started again
    fakes.custom[REGISTRY_SERVICE_TYPE] = {"success": True, "status": "ok"}
    await collector.poll()
    await settle()
    services = by_type(collector)
    assert services[REGISTRY_SERVICE_TYPE].state is ServiceState.OK
    assert services["SM_CS"].registered and "DAQ6510" in services

    await collector.stop()


async def test_server_kind_found_by_the_report_is_kept():
    """A server that registered without `server_kind`: the kind found by the report request is kept on every poll."""
    collector, registry, fakes, clock = make_collector()
    registry.records = [record("CM_CS", name="cm_cs", service_port=6112, monitoring_port=6111)]

    async def request_report(service, timeout):
        service.server_kind = "sync"  # like report.request_status_report() does after a successful sync request
        return REPORT

    collector._request_report = request_report
    await collector.poll()
    await settle()
    await collector.poll()
    await settle()

    assert by_type(collector)["CM_CS"].server_kind == "sync"
    assert by_type(collector)["CM_CS"].report == REPORT

    await collector.stop()


async def test_report_without_device():
    collector, registry, fakes, clock = make_collector()
    registry.records = [
        record("SM_CS", name="sm_cs", service_port=5001, monitoring_port=5002, server_kind="sync"),
        record("AWG1", service_port=2001, monitoring_port=2002, server_kind="sync"),
    ]
    fakes.reports["SM_CS"] = {**REPORT, "device": None}
    fakes.reports["AWG1"] = REPORT

    await collector.poll()
    await settle()

    services = by_type(collector)
    assert services["SM_CS"].has_device is False
    assert services["AWG1"].has_device is True and services["AWG1"].connected is True

    await collector.stop()


async def test_command_server_gets_its_process_information_from_the_registry():
    """A service that is not a control server, recognised by its `server_kind` (e.g. facility_hk)."""
    collector, registry, fakes, clock = make_collector(known={REGISTRY_SERVICE_TYPE: "Service Registry"})
    heartbeat = {"pid": 777, "uptime_s": 60.0, "rss": 2048, "cpu_percent": 0.5}
    registry.records = [
        {**record("facility_hk", name="facility_hk", port=6201, server_kind="command"), "status": heartbeat}
    ]
    fakes.custom["facility_hk"] = {"status": "ACK", "host": "10.0.0.1", "command_port": 6201}

    await collector.poll()
    await settle()

    service = by_type(collector)["facility_hk"]
    assert service.state is ServiceState.OK  # polled like the other custom servers
    assert (service.pid, service.uptime_s, service.rss, service.cpu_percent) == (777, 60.0, 2048, 0.5)
    assert not fakes.subscriptions  # no monitoring port

    await collector.stop()


async def test_registry_row_gets_its_process_information_from_the_info_reply():
    collector, registry, fakes, clock = make_collector(known={REGISTRY_SERVICE_TYPE: "Service Registry"})
    fakes.custom[REGISTRY_SERVICE_TYPE] = {
        "success": True,
        "status": "ok",
        "pid": 4141,
        "cgse_object": "reg",
        "process": {"pid": 4141},
    }

    await collector.poll()
    await settle()

    assert by_type(collector)[REGISTRY_SERVICE_TYPE].pid == 4141
    assert by_type(collector)[REGISTRY_SERVICE_TYPE].cgse_object == "reg"

    await collector.stop()


async def test_registration_details_are_kept():
    collector, registry, fakes, clock = make_collector()
    registry.records = [
        {
            **record(
                "AWG2",
                service_port=2001,
                monitoring_port=2002,
                server_kind="sync",
                device_id="AWG-02",
                cgse_object="tgf4000",
            ),
            "id": "awg2-1234",
            "ttl": 30,
            "last_heartbeat": 995,
            "health": "passing",
        }
    ]
    registry.records[0]["metadata"]["start_time"] = 900.0

    await collector.poll()
    await settle()

    awg = by_type(collector)["AWG2"]
    assert (awg.service_id, awg.ttl, awg.last_heartbeat, awg.health) == ("awg2-1234", 30, 995, "passing")
    assert awg.device_id == "AWG-02" and awg.start_time == 900.0
    assert awg.cgse_object == "tgf4000"
    assert awg.metadata["service_port"] == 2001

    await collector.stop()


async def test_core_services_have_their_cgse_command_also_when_not_running():
    collector, registry, fakes, clock = make_collector()

    assert by_type(collector)["SM_CS"].cgse_object == "sm"
    assert by_type(collector)[REGISTRY_SERVICE_TYPE].cgse_object == "reg"

    registry.records = [record("SM_CS", service_port=6101, monitoring_port=6102, server_kind="sync")]
    await collector.poll()
    registry.records = []
    await collector.poll()  # deregistered: the row is reset

    assert by_type(collector)["SM_CS"].cgse_object == "sm"
    await collector.stop()


async def test_wait_until_a_service_is_running():
    collector, registry, fakes, clock = make_collector()

    await collector.poll()
    assert collector.is_running(REGISTRY_SERVICE_TYPE)
    assert not collector.is_running("SM_CS")
    assert not await collector.wait_until("SM_CS", running=True, timeout=0.05, interval=0.01)

    registry.records = [record("SM_CS", service_port=6101, monitoring_port=6102, server_kind="sync")]
    assert await collector.wait_until("SM_CS", running=True, timeout=1.0, interval=0.01)

    registry.healthy = False
    assert await collector.wait_until(REGISTRY_SERVICE_TYPE, running=False, timeout=1.0, interval=0.01)
    await collector.stop()


async def test_status_report_is_requested_again_for_the_device_connection():
    collector, registry, fakes, clock = make_collector()
    registry.records = [record("TVAC", service_port=3001, monitoring_port=3002, server_kind="async")]
    fakes.reports["TVAC"] = {**REPORT, "device": {"connected": False, "sim_mode": None}}  # just started

    await collector.poll()
    await settle()
    assert by_type(collector)["TVAC"].connected is False

    fakes.reports["TVAC"] = {**REPORT, "device": {"connected": True, "sim_mode": True}}  # connected to the device
    clock.t += collector.report_interval - 1
    await collector.poll()
    await settle()
    assert by_type(collector)["TVAC"].connected is False  # not yet asked again

    clock.t += 1
    await collector.poll()
    await settle()
    assert (by_type(collector)["TVAC"].connected, by_type(collector)["TVAC"].sim_mode) == (True, True)

    fakes.reports["TVAC"] = {**REPORT, "device": {"connected": False, "sim_mode": True}}  # the device disconnected
    await collector.poll(reports=True)  # a refresh asks right away
    await settle()
    assert by_type(collector)["TVAC"].connected is False

    await collector.stop()
