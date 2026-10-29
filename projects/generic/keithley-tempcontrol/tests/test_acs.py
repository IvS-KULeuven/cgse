"""Tests for the DAQ6510 asynchronous control server logic.

The control server is not started (no sockets, no registry), its controller is driven directly with command
dictionaries. The device is the asynchronous driver talking to a DAQ6510Model with a fake clock.
"""

import asyncio
import datetime
import json
import pickle
from typing import Any

import pytest
import typer

from egse.device import DeviceConnectionError
from egse.device import DeviceError
from egse.device import DeviceTimeoutError
from egse.tempcontrol.keithley import daq6510_acs
from egse.tempcontrol.keithley.daq6510_acs import DAQ6510ControlServer
from egse.tempcontrol.keithley.daq6510_config import ScanConfig
from egse.tempcontrol.keithley.daq6510_config import SensorConfig
from egse.tempcontrol.keithley.daq6510_model import DAQ6510Model
from egse.tempcontrol.keithley.daq6510_model import ModelledDAQ6510

INTERVAL = 1.0
CHANNELS = ["101", "102", "103"]


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class ControlServerUnderTest(DAQ6510ControlServer):
    """Replaces the external dependencies (Setup, Storage Manager, Metrics Hub) by in-memory versions."""

    def __init__(self, daq, config: ScanConfig):
        self.config = config
        self.metrics: list[dict[str, Any]] = []
        super().__init__(daq=daq)

    async def load_scan_config(self) -> ScanConfig:
        return self.config

    def _read_hk_names(self, config: ScanConfig) -> dict[str, str]:
        return {channel: f"TEST_T{channel}" for channel in config.channel_names}

    def is_storage_manager_active(self) -> bool:
        return False

    async def _send_metrics(self, hk: dict[str, Any]) -> bool:
        self.metrics.append(hk)
        return True


def make_config(**kwargs) -> ScanConfig:
    defaults = {
        "channel_list": "(@101:103)",
        "interval": INTERVAL,
        "sensors": [SensorConfig("TEMPERATURE", "(@101:103)", [("TRANSDUCER", "FRTD"), ("RTD:FOUR", "PT100")])],
    }
    defaults.update(kwargs)
    return ScanConfig(**defaults)


def decode(response: list) -> dict:
    message_type, data = response
    if message_type == b"MESSAGE_TYPE:JSON":
        return json.loads(data)
    return pickle.loads(data)


@pytest.fixture
async def setup():
    """Yields (control server, model, clock) with a connected device and a running acquisition pipeline."""
    clock = FakeClock()
    model = DAQ6510Model(clock=clock, scan_duration=0.1)
    daq = ModelledDAQ6510(model)
    await daq.connect()

    server = ControlServerUnderTest(daq, make_config())
    server.controller.poll_interval = 0.01
    server._loop = asyncio.get_running_loop()
    acquisition_task = asyncio.create_task(server.process_acquisition_data())

    yield server, model, clock

    await server.controller.stop_scan()
    server.interrupted.set()
    await acquisition_task
    server.disconnect_device_command_socket()
    server.disconnect_service_command_socket()
    server.disconnect_monitoring_socket()


async def command(server, name: str, **kwargs) -> dict:
    return decode(await server.controller.process_command({"command": name, **kwargs}))


async def wait_for(condition, timeout: float = 2.0):
    async def _wait():
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_wait(), timeout)


@pytest.mark.asyncio
async def test_start_scan_configures_the_instrument(setup):
    server, model, _ = setup

    response = await command(server, "start-scan")

    assert response["success"], response
    assert response["message"]["started"] is True
    assert server.controller.is_scan_running()

    assert 'SENS:FUNC "TEMPERATURE", (@101:103)' in model.commands
    assert "SENS:TEMPERATURE:RTD:FOUR PT100, (@101:103)" in model.commands
    assert model.scan_channels == CHANNELS
    assert model.scan_count == 0  # repeat until aborted
    assert model.scan_state == "RUNNING"


@pytest.mark.asyncio
async def test_scans_are_passed_to_latest_and_sinks(setup):
    server, _, clock = setup

    await command(server, "start-scan")
    clock.t = 3.5  # 4 scans completed

    await wait_for(lambda: len(server.metrics) == 4)

    status = (await command(server, "scan-status"))["message"]
    assert status["scans_received"] == 4
    assert status["next_index"] == 4 * len(CHANNELS) + 1

    latest = (await command(server, "get-latest"))["message"]
    assert sorted(latest) == CHANNELS
    assert latest["101"]["unit"] == "Celsius"

    hk = server.metrics[-1]
    assert sorted(hk) == ["TEST_T101", "TEST_T102", "TEST_T103", "timestamp"]
    assert latest["101"]["value"] == hk["TEST_T101"]

    timestamps = [m["timestamp"] for m in server.metrics]
    assert timestamps == sorted(set(timestamps))  # no duplicates, in order


@pytest.mark.asyncio
async def test_only_complete_scans_are_fetched(setup):
    server, model, clock = setup
    controller = server.controller

    await command(server, "start-scan")
    await controller.stop_scan()  # we poll manually in this test
    model.process("INIT")  # but keep the instrument scanning

    clock.t = 1.5  # 2 complete scans
    model.process("TRAC:ACT?")  # let the model add the readings to the buffer
    # Remove one reading, the buffer now ends with an incomplete scan
    model.buffers["defbuffer1"].readings.pop()

    assert await controller.poll_buffer() == 1
    assert controller.next_index == len(CHANNELS) + 1


@pytest.mark.asyncio
async def test_commands_during_scan(setup):
    server, _, _ = setup

    await command(server, "start-scan")

    for blocked in ("start-scan", "set-time", "send-command"):
        response = await command(server, blocked)
        assert not response["success"]
        assert response["message"]["error"] == "device-busy"

    response = await command(server, "get-idn")
    assert response["success"]
    assert "DAQ6510" in response["message"]

    assert (await command(server, "get-errors"))["message"] == []
    assert (await command(server, "get-time"))["success"]
    assert (await command(server, "get-buffer-count"))["success"]

    # unknown commands are still reported as unknown, not as busy
    assert "Unknown command" in (await command(server, "no-such-command"))["message"]


@pytest.mark.asyncio
async def test_stop_scan_aborts_the_instrument(setup):
    server, model, _ = setup

    await command(server, "start-scan")
    response = await command(server, "stop-scan")

    assert response["message"]["stopped"] is True
    assert not server.controller.is_scan_running()
    assert model.scan_state == "ABORTED"

    assert (await command(server, "stop-scan"))["message"]["stopped"] is False

    # after the scan, configuration commands are accepted again
    assert (await command(server, "set-time"))["success"]


@pytest.mark.asyncio
async def test_reset_during_scan(setup):
    server, model, _ = setup

    await command(server, "start-scan")
    response = await command(server, "reset")

    assert response["success"]
    assert not server.controller.is_scan_running()
    assert model.scan_channels == []  # *RST cleared the scan list


@pytest.mark.asyncio
async def test_send_command(setup):
    server, model, _ = setup

    response = await command(server, "send-command", command_string="*IDN?", response=True)
    assert "DAQ6510" in response["message"]

    response = await command(server, "send-command", command_string="ROUT:SCAN:INT 3")
    assert response["success"]
    assert model.scan_interval == 3.0

    assert not (await command(server, "send-command"))["success"]


@pytest.mark.asyncio
async def test_buffer_rollover(setup):
    server, model, clock = setup
    controller = server.controller
    server.config = make_config(buffer_capacity=30)  # rollover at 27 readings = 9 scans

    await command(server, "start-scan")
    await controller.stop_scan()  # we poll manually in this test
    model.process("INIT")  # but keep the instrument scanning

    clock.t = 9.5  # 10 scans
    assert await controller.poll_buffer() == 10

    assert controller.rollovers == 1
    assert controller.next_index == 1
    assert model.scan_state == "RUNNING"
    assert len(model.buffers["defbuffer1"].readings) == 0

    clock.t = 11.0  # the restarted scan started at 9.5
    assert await controller.poll_buffer() == 2

    await wait_for(lambda: len(server.metrics) == 12)
    timestamps = [m["timestamp"] for m in server.metrics]
    assert timestamps == sorted(set(timestamps))


@pytest.mark.asyncio
async def test_buffer_cleared_behind_our_back(setup):
    server, model, clock = setup
    controller = server.controller

    await command(server, "start-scan")
    await controller.stop_scan()
    model.process("INIT")

    clock.t = 2.5
    assert await controller.poll_buffer() == 3

    model.process('TRAC:CLE "defbuffer1"')
    model._scans_done = 0
    model._scan_start = clock.t
    clock.t = 4.0

    assert await controller.poll_buffer() == 2
    assert controller.next_index == 2 * len(CHANNELS) + 1


@pytest.mark.asyncio
async def test_timeout_reconnects_without_data_loss(setup):
    server, _, clock = setup
    controller = server.controller
    daq = controller.daq

    await command(server, "start-scan")
    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)

    daq.fail_next = DeviceTimeoutError("DAQ6510", "Communication timed out")
    clock.t = 5.5
    await wait_for(lambda: controller.scans_received == 6)

    assert "DeviceTimeoutError" in controller.last_error
    assert daq.is_connection_open  # reconnected by the scan loop
    assert controller.is_scan_running()


@pytest.mark.asyncio
async def test_start_scan_fails_on_device_errors(setup):
    server, model, _ = setup
    server.config = make_config(sensors=[SensorConfig("TEMPERATURE", "(@1x)", [("TRANSDUCER", "FRTD")])])

    response = await command(server, "start-scan")

    assert not response["success"]
    assert response["message"]["error"] == "start-scan-failed"
    assert "-224" in response["message"]["detail"]
    assert not server.controller.is_scan_running()
    assert model.scan_state == "IDLE"


@pytest.mark.asyncio
async def test_device_not_connected(setup):
    server, _, _ = setup
    await server.controller.daq.disconnect()

    response = await command(server, "get-idn")
    assert response["message"]["error"] == "device-not-connected"

    response = await command(server, "start-scan")
    assert response["message"]["error"] == "start-scan-failed"


@pytest.mark.asyncio
async def test_auto_scan_on_connect(setup):
    server, _, _ = setup
    await server.controller.daq.disconnect()
    server.auto_scan = True

    task = asyncio.create_task(server.maintain_connection())
    try:
        await wait_for(lambda: server.controller.is_scan_running())
    finally:
        server.interrupted.set()
        await task

    assert server.controller.daq.is_connection_open
    assert server.auto_scan is False


@pytest.mark.asyncio
async def test_storage_registration_follows_the_scan_channels(setup, monkeypatch):
    server, _, _ = setup
    calls = []

    monkeypatch.setattr(server, "is_storage_manager_active", lambda: True)
    monkeypatch.setattr(
        "egse.storage.register_to_storage_manager",
        lambda origin, persistence_class, prep: calls.append(("register", prep["column_names"])),
    )
    monkeypatch.setattr("egse.storage.unregister_from_storage_manager", lambda origin: calls.append(("unregister",)))

    await command(server, "start-scan")
    await command(server, "stop-scan")
    await command(server, "start-scan")  # same channels, no new registration
    await command(server, "stop-scan")

    server.config = make_config(channel_list="(@101:102)", sensors=[])
    await command(server, "start-scan")

    assert calls == [
        ("register", ["timestamp", "TEST_T101", "TEST_T102", "TEST_T103"]),
        ("unregister",),
        ("register", ["timestamp", "TEST_T101", "TEST_T102"]),
    ]

    await server.controller.stop_scan()
    server.unregister_from_storage_manager()
    server.unregister_from_storage_manager()  # idempotent
    assert calls[-1] == ("unregister",)
    assert len(calls) == 4


# ----- data sinks -----------------------------------------------------------------------------------------------------


class FakeMetricsSender:
    """Replaces the AsyncMetricsHubSender, records the points that are sent."""

    instances: list["FakeMetricsSender"] = []

    def __init__(self):
        self.points = []
        self.result = True
        self.connected = False
        FakeMetricsSender.instances.append(self)

    def connect(self):
        self.connected = True

    async def send(self, point) -> bool:
        if isinstance(self.result, Exception):
            raise self.result
        self.points.append(point.as_dict())
        return self.result

    def close(self):
        self.connected = False


@pytest.fixture
def metrics_sender(monkeypatch):
    FakeMetricsSender.instances = []
    monkeypatch.setattr(daq6510_acs, "AsyncMetricsHubSender", FakeMetricsSender)
    return FakeMetricsSender


@pytest.mark.asyncio
async def test_metrics_data_point(setup, metrics_sender):
    server, _, _ = setup
    hk = {"timestamp": "2025-01-02T03:04:05.250000+00:00", "TEST_T101": 20.5, "TEST_T102": 21.0}

    # call the real implementation, the control server under test replaces it
    assert await DAQ6510ControlServer._send_metrics(server, hk) is True
    assert await DAQ6510ControlServer._send_metrics(server, hk) is True

    assert len(metrics_sender.instances) == 1  # the sender is created once and reused
    sender = metrics_sender.instances[0]
    assert sender.connected

    point = sender.points[0]
    assert point["measurement"] == "daq6510"
    assert point["tags"] == {"site_id": daq6510_acs.SITE_ID, "origin": "DAQ6510"}
    assert point["fields"] == {"test_t101": 20.5, "test_t102": 21.0}
    assert point["time"] == datetime.datetime(2025, 1, 2, 3, 4, 5, 250000, tzinfo=datetime.timezone.utc).timestamp()


@pytest.mark.asyncio
async def test_metrics_failures_are_not_raised(setup, metrics_sender):
    server, _, _ = setup
    hk = {"timestamp": "2025-01-02T03:04:05+00:00", "TEST_T101": 20.5}

    assert await DAQ6510ControlServer._send_metrics(server, hk) is True
    sender = metrics_sender.instances[0]

    sender.result = False  # hub unreachable or send buffer full
    assert await DAQ6510ControlServer._send_metrics(server, hk) is False

    sender.result = RuntimeError("socket closed")
    assert await DAQ6510ControlServer._send_metrics(server, hk) is False


@pytest.mark.asyncio
async def test_scans_are_stored(setup, monkeypatch):
    server, _, clock = setup
    stored = []

    monkeypatch.setattr("egse.storage.store_housekeeping_information", lambda origin, hk: stored.append((origin, hk)))

    await command(server, "start-scan")
    server.storage_registered = True  # registration itself is tested in test_storage_registration_...
    clock.t = 1.5

    await wait_for(lambda: server.stored_count == 2)

    assert [origin for origin, _ in stored] == ["DAQ6510", "DAQ6510"]
    assert sorted(stored[0][1]) == ["TEST_T101", "TEST_T102", "TEST_T103", "timestamp"]
    assert stored[1][1] == server.metrics[1]


@pytest.mark.asyncio
async def test_sink_failures_do_not_stop_the_acquisition(setup, monkeypatch):
    server, _, clock = setup

    def store(origin, hk):
        raise ConnectionError("Storage Manager is gone")

    async def send_metrics(hk):
        return False

    monkeypatch.setattr("egse.storage.store_housekeeping_information", store)
    monkeypatch.setattr(server, "_send_metrics", send_metrics)

    await command(server, "start-scan")
    server.storage_registered = True
    clock.t = 2.5

    await wait_for(lambda: server.metrics_failed_count == 3)

    assert server.stored_count == 0
    assert server.metrics_count == 0
    assert server.controller.scans_received == 3
    assert sorted((await command(server, "get-latest"))["message"]) == CHANNELS


# ----- setup loading --------------------------------------------------------------------------------------------------

SETUP_YAML = """\
Setup:
    gse:
        DAQ6510:
            channels: (@101:104)
            sensors:
                PT100:
                    temperature:
                        TRANSDUCER: FRTD
                        RTD:
                            FOUR: PT100
                        channels: (@101:104)
            route:
                scan:
                    INTERVAL: 2
"""


@pytest.mark.asyncio
async def test_load_scan_config_from_setup_file(setup, tmp_path):
    server, _, _ = setup
    setup_file = tmp_path / "setup.yaml"
    setup_file.write_text(SETUP_YAML)
    server.setup_file = setup_file

    config = await DAQ6510ControlServer.load_scan_config(server)

    assert config.channel_names == ["101", "102", "103", "104"]
    assert config.interval == 2.0
    assert config.buffer_capacity == daq6510_acs.BUFFER_CAPACITY
    assert config.sensors[0].settings == [("TRANSDUCER", "FRTD"), ("RTD:FOUR", "PT100")]


@pytest.mark.asyncio
async def test_load_scan_config_without_setup(setup, monkeypatch):
    server, _, _ = setup
    monkeypatch.setattr("egse.setup.load_setup", lambda: None)

    with pytest.raises(ValueError, match="No Setup available"):
        await DAQ6510ControlServer.load_scan_config(server)


def test_hk_names_from_the_telemetry_dictionary(setup, monkeypatch, tmp_path):
    server, _, _ = setup
    setup_file = tmp_path / "setup.yaml"
    setup_file.write_text(SETUP_YAML)
    server.setup_file = setup_file
    config = make_config()

    # The Setup has no telemetry dictionary, fall back to the channel names
    assert DAQ6510ControlServer._read_hk_names(server, config) == {
        "101": "DAQ6510_101",
        "102": "DAQ6510_102",
        "103": "DAQ6510_103",
    }

    monkeypatch.setattr(
        "egse.hk.read_conversion_dict", lambda *args, **kwargs: {"101": "GLAB_T_IN", "103": "GLAB_T_OUT"}
    )
    assert DAQ6510ControlServer._read_hk_names(server, config) == {
        "101": "GLAB_T_IN",
        "102": "DAQ6510_102",
        "103": "GLAB_T_OUT",
    }


# ----- error paths ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_time(setup):
    server, model, _ = setup

    response = await command(server, "set-time", time="not a time")
    assert response["message"]["error"] == "invalid-argument"

    response = await command(server, "set-time", time="2025-01-02T03:04:05")
    assert response["success"]
    assert model.process("SYST:TIME? 1") == "Thu Jan 02 03:04:05 2025"


@pytest.mark.asyncio
async def test_device_error_is_reported(setup):
    server, _, _ = setup
    server.controller.daq.fail_next = DeviceError("DAQ6510", "Something went wrong")

    response = await command(server, "get-idn")

    assert not response["success"]
    assert response["message"]["error"] == "device-error"
    assert "Something went wrong" in response["message"]["detail"]

    assert (await command(server, "get-idn"))["success"]  # the next command works again


@pytest.mark.asyncio
async def test_start_scan_while_running_does_nothing(setup):
    server, model, _ = setup
    controller = server.controller

    await command(server, "start-scan")
    n_commands = len(model.commands)

    assert await controller.start_scan() is False
    assert len(model.commands) == n_commands


@pytest.mark.asyncio
async def test_stop_scan_when_abort_fails(setup, monkeypatch):
    server, _, _ = setup
    controller = server.controller

    async def abort():
        raise DeviceError("DAQ6510", "Communication failed")

    await command(server, "start-scan")
    monkeypatch.setattr(controller.daq, "abort", abort)

    assert await controller.stop_scan() is True
    assert not controller.is_scan_running()


@pytest.mark.asyncio
async def test_drop_connection_when_disconnect_fails(setup, monkeypatch):
    server, _, _ = setup
    controller = server.controller

    async def disconnect():
        raise DeviceError("DAQ6510", "Socket already closed")

    monkeypatch.setattr(controller.daq, "disconnect", disconnect)

    await controller._drop_connection()  # logs a warning, doesn't raise


# ----- connection loss and power cycles -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_lost_reconnects_without_data_loss(setup):
    server, model, clock = setup
    controller = server.controller
    daq = controller.daq

    await command(server, "start-scan")
    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)

    daq.break_connection()
    clock.t = 4.5
    await wait_for(lambda: controller.scans_received == 5)

    assert "Broken pipe" in controller.last_error
    assert daq.is_connection_open
    assert controller.is_scan_running()
    assert controller.restarts == 0  # the instrument kept scanning, no restart needed

    timestamps = [m["timestamp"] for m in server.metrics]
    assert timestamps == sorted(set(timestamps))


@pytest.mark.asyncio
async def test_scan_is_restarted_after_a_power_cycle(setup):
    server, model, clock = setup
    controller = server.controller

    await command(server, "start-scan")
    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)

    # A power cycle: the instrument loses its configuration and the buffer, and the connection is lost
    model.reset()
    controller.daq.break_connection()

    await wait_for(lambda: controller.restarts == 1)
    assert model.scan_state == "RUNNING"
    assert model.scan_channels == CHANNELS
    assert model.scan_count == 0
    assert ("101", "RTD:FOUR") in model.sense  # the sensors are configured again

    clock.t = 4.0  # the restarted scan started at 1.5
    await wait_for(lambda: controller.scans_received == 5)

    status = (await command(server, "scan-status"))["message"]
    assert status["running"] is True
    assert status["restarts"] == 1


@pytest.mark.asyncio
async def test_aborted_scan_is_restarted(setup):
    server, model, clock = setup
    controller = server.controller
    controller.clock = clock

    await command(server, "start-scan")
    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)

    # The scan is aborted by another client or from the front panel, the connection stays up
    model.process("ABOR")
    assert model.scan_state == "ABORTED"

    clock.t = 1.5 + controller.stall_timeout() - 0.1  # not stalled yet
    await asyncio.sleep(0.05)
    assert controller.restarts == 0

    clock.t = 1.5 + controller.stall_timeout() + 0.1
    await wait_for(lambda: controller.restarts == 1)
    assert model.scan_state == "RUNNING"
    assert controller.daq.is_connection_open

    clock.t += 2.5  # the restarted scan delivers new scans
    await wait_for(lambda: controller.scans_received == 5)
    assert controller.get_scan_health() == "ok"


@pytest.mark.asyncio
async def test_slow_scan_is_not_restarted(setup, monkeypatch):
    server, model, clock = setup
    controller = server.controller
    controller.clock = clock

    await command(server, "start-scan")
    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)

    checks = []
    get_scan_state = controller.daq.get_scan_state

    async def counting_get_scan_state():
        checks.append(clock.t)
        return await get_scan_state()

    monkeypatch.setattr(controller.daq, "get_scan_state", counting_get_scan_state)

    # No new scans while the instrument is still scanning, e.g. a scan takes longer than expected
    monkeypatch.setattr(model, "_update_scan", lambda: None)

    clock.t = 1.5 + controller.stall_timeout() + 0.1
    await wait_for(lambda: len(checks) == 1)
    await asyncio.sleep(0.05)

    assert len(checks) == 1  # checked once, not on every poll
    assert controller.restarts == 0
    assert controller.is_scan_running()


@pytest.mark.asyncio
async def test_scan_stops_when_the_restart_fails(setup, monkeypatch):
    server, model, clock = setup
    controller = server.controller

    await command(server, "start-scan")
    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)

    async def configure_scan(config):
        await controller.daq.write('SENS:FUNC "TEMP", (@1x)')  # the instrument reports an error

    model.reset()
    monkeypatch.setattr(controller.daq, "configure_scan", configure_scan)
    controller.daq.break_connection()

    await wait_for(lambda: not controller.is_scan_running())

    assert controller.last_error.startswith("ScanRestartError")
    assert "-224" in controller.last_error
    assert (await command(server, "scan-status"))["message"]["running"] is False

    # the scan can be started again once the cause is fixed
    monkeypatch.undo()
    assert (await command(server, "start-scan"))["message"]["started"] is True


@pytest.mark.asyncio
async def test_incomplete_buffer_read_is_fetched_again(setup, monkeypatch):
    server, model, clock = setup
    controller = server.controller

    await command(server, "start-scan")
    await controller.stop_scan()  # we poll manually in this test
    model.process("INIT")

    clock.t = 2.5  # 3 scans
    read_buffer = controller.daq.read_buffer

    async def empty_response(start, end, buffer_name):
        return []  # e.g. the device closed the connection

    monkeypatch.setattr(controller.daq, "read_buffer", empty_response)
    with pytest.raises(DeviceConnectionError, match="Expected 9 readings"):
        await controller.poll_buffer()
    assert controller.next_index == 1

    monkeypatch.setattr(controller.daq, "read_buffer", read_buffer)
    assert await controller.poll_buffer() == 3
    assert controller.next_index == 3 * len(CHANNELS) + 1


# ----- error record and condition -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_condition_clears_but_the_record_stays(setup, monkeypatch):
    server, _, clock = setup
    controller = server.controller

    await command(server, "start-scan")
    status = (await command(server, "scan-status"))["message"]
    assert status["health"] == "ok"
    assert status["error_count"] == 0
    assert status["last_error"] is None
    assert status["last_error_at"] is None

    # errors that repeat: the scan is degraded
    get_buffer_end = controller.daq.get_buffer_end

    async def failing_get_buffer_end(buffer_name):
        raise DeviceError("DAQ6510", "Something went wrong")

    monkeypatch.setattr(controller.daq, "get_buffer_end", failing_get_buffer_end)
    await wait_for(lambda: controller.consecutive_errors >= 2)
    assert (await command(server, "scan-status"))["message"]["health"] == "degraded"

    # the problem is gone: the condition clears by itself, the record of the error stays
    monkeypatch.setattr(controller.daq, "get_buffer_end", get_buffer_end)
    await wait_for(lambda: controller.consecutive_errors == 0, timeout=5.0)

    status = (await command(server, "scan-status"))["message"]
    assert status["health"] == "ok"
    assert status["error_count"] >= 2
    assert "Something went wrong" in status["last_error"]
    assert status["last_error_at"] is not None

    # clearing the errors is allowed during the scan
    response = await command(server, "clear-errors")
    assert response["success"]
    assert response["message"]["last_error"] is None
    assert response["message"]["last_error_at"] is None
    assert response["message"]["error_count"] == 0
    assert controller.is_scan_running()

    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)
    assert controller.last_error is None


@pytest.mark.asyncio
async def test_clear_errors_does_not_hide_a_persisting_problem(setup, monkeypatch):
    server, _, _ = setup
    controller = server.controller

    async def failing_get_buffer_end(buffer_name):
        raise DeviceError("DAQ6510", "Still broken")

    await command(server, "start-scan")
    monkeypatch.setattr(controller.daq, "get_buffer_end", failing_get_buffer_end)
    await wait_for(lambda: controller.consecutive_errors >= 1)

    status = (await command(server, "clear-errors"))["message"]
    assert status["health"] == "degraded"  # the condition is not cleared
    assert status["last_error"] is None

    await wait_for(lambda: controller.last_error is not None, timeout=5.0)  # recorded again on the next failure
    assert "Still broken" in controller.last_error


@pytest.mark.asyncio
async def test_failed_scan_health(setup, monkeypatch):
    server, model, clock = setup
    controller = server.controller

    await command(server, "start-scan")
    clock.t = 1.5
    await wait_for(lambda: controller.scans_received == 2)

    async def configure_scan(config):
        await controller.daq.write('SENS:FUNC "TEMP", (@1x)')

    model.reset()
    monkeypatch.setattr(controller.daq, "configure_scan", configure_scan)
    controller.daq.break_connection()
    await wait_for(lambda: not controller.is_scan_running())

    status = (await command(server, "scan-status"))["message"]
    assert status["health"] == "failed"
    assert status["running"] is False

    # clearing the errors doesn't change the condition, starting a new scan does
    assert (await command(server, "clear-errors"))["message"]["health"] == "failed"

    monkeypatch.undo()
    status = (await command(server, "start-scan"))["message"]["status"]
    assert status["health"] == "ok"
    assert status["last_error"] is None


@pytest.mark.asyncio
async def test_failed_auto_scan_is_reported(setup):
    server, _, _ = setup
    server.config = make_config(sensors=[SensorConfig("TEMPERATURE", "(@1x)", [("TRANSDUCER", "FRTD")])])
    await server.controller.daq.disconnect()
    server.auto_scan = True

    task = asyncio.create_task(server.maintain_connection())
    try:
        await wait_for(lambda: server.controller.scan_failed)
    finally:
        server.interrupted.set()
        await task

    status = server.controller.get_scan_status()
    assert status["health"] == "failed"
    assert "-224" in status["last_error"]


# ----- command line ---------------------------------------------------------------------------------------------------


@pytest.fixture
def cli(setup, monkeypatch):
    """Routes the device commands of the command line through the control server under test."""
    server, model, clock = setup

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send_device_command(self, request, timeout=None):
            return decode(await server.controller.process_command(request))

    monkeypatch.setattr(daq6510_acs, "DAQ6510Client", Client)
    return server, model, clock


@pytest.mark.asyncio
async def test_cli_prints_the_result(cli, capsys):
    server, model, _ = cli

    await daq6510_acs._run_device_command("get-idn")
    assert "DAQ6510" in capsys.readouterr().out

    await daq6510_acs._run_device_command("set-time", time="2025-01-02T03:04:05")
    assert capsys.readouterr().out.strip() == "OK"  # a successful command without a result
    assert model.process("SYST:TIME? 1") == "Thu Jan 02 03:04:05 2025"

    await daq6510_acs._run_device_command("send-command", command_string="ROUT:SCAN:STAT?", response=True)
    assert capsys.readouterr().out.startswith("IDLE")


@pytest.mark.asyncio
async def test_cli_reports_a_failure(cli, capsys):
    server, _, _ = cli

    await command(server, "start-scan")

    with pytest.raises(typer.Exit) as exc_info:
        await daq6510_acs._run_device_command("set-time")
    assert exc_info.value.exit_code == 1
    out = capsys.readouterr().out
    assert "'set-time' failed" in out
    assert "device-busy" in out


@pytest.mark.asyncio
async def test_cli_reports_an_unreachable_control_server(monkeypatch, capsys):
    class Client:
        async def __aenter__(self):
            raise ConnectionError("no service_type (DAQ6510) found")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(daq6510_acs, "DAQ6510Client", Client)

    with pytest.raises(typer.Exit) as exc_info:
        await daq6510_acs._run_device_command("get-idn")
    assert exc_info.value.exit_code == 1
    assert "Could not send 'get-idn'" in capsys.readouterr().out
