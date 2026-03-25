import asyncio
import json

import pytest
import zmq

from egse.metrics import DataPoint
from egse.metricshub.client import AsyncMetricsHubClient
from egse.metricshub.client import AsyncMetricsHubSender
from egse.metricshub.client import MetricsHubClient
from egse.metricshub.client import MetricsHubSender
from egse.metricshub.server import AsyncMetricsHub
from egse.metricshub.server import _normalize_payload
from egse.registry import MessageType


class RecordingRepository:
    def __init__(self):
        self.connected = False
        self.closed = False
        self.writes: list[list[dict]] = []

    def connect(self) -> None:
        self.connected = True

    def ping(self) -> bool:
        return True

    def write(self, points):
        if isinstance(points, list):
            self.writes.append(points.copy())
        else:
            self.writes.append([points])

    def query(self, query_str: str, mode: str):
        raise NotImplementedError()

    def get_table_names(self) -> list[str]:
        return []

    def get_column_names(self, table_name: str) -> list[str]:
        return []

    def get_values_last_hours(self, table_name: str, column_name: str, hours: int, mode: str):
        return []

    def get_values_in_range(self, table_name: str, column_name: str, start_time: str, end_time: str, mode: str):
        return []

    def close(self) -> None:
        self.closed = True


class DummySyncSocket:
    def __init__(self, poll_result=True, message_parts=None):
        self.poll_result = poll_result
        self.message_parts = message_parts or [
            MessageType.RESPONSE.value,
            json.dumps({"success": True, "status": "ok"}).encode(),
        ]
        self.sent: list[list[bytes]] = []

    def send_multipart(self, message):
        self.sent.append(message)

    def poll(self, timeout):
        return self.poll_result

    def recv_multipart(self):
        return self.message_parts


class DummySyncPushSocket:
    def __init__(self, should_raise_again: bool = False):
        self.should_raise_again = should_raise_again
        self.sent_payloads: list[bytes] = []

    def send(self, payload: bytes, flags: int = 0):
        if self.should_raise_again:
            raise zmq.Again()
        self.sent_payloads.append(payload)


def test_normalize_payload_accepts_valid_datapoint():
    payload = {
        "measurement": "camera_tm",
        "tags": {"device_id": "cam_01", "mode": "idle"},
        "fields": {"temperature": 23.4, "pressure": 1013.2},
        "time": "2026-03-23T12:34:56Z",
    }

    point, error = _normalize_payload(payload)

    assert error is None
    assert point == payload


@pytest.mark.parametrize(
    ("payload", "error_fragment"),
    [
        ({}, "missing/invalid 'measurement'"),
        ({"measurement": "camera_tm", "fields": {}}, "missing/invalid 'fields'"),
        ({"measurement": "camera_tm", "fields": {"temperature": 1.0}, "tags": []}, "invalid 'tags'"),
        ({"measurement": "camera_tm", "fields": {"": 1.0}}, "field keys must be non-empty strings"),
        ({"measurement": "camera_tm", "fields": {"temperature": None}}, "field values cannot be None"),
        (
            {"measurement": "camera_tm", "fields": {"temperature": 1.0}, "tags": {"": "cam_01"}},
            "tag keys must be non-empty strings",
        ),
        (
            {"measurement": "camera_tm", "fields": {"temperature": 1.0}, "tags": {"device_id": None}},
            "tag values cannot be None",
        ),
        ({"measurement": "camera_tm", "fields": {"temperature": 1.0}, "time": {}}, "invalid timestamp/time"),
    ],
)
def test_normalize_payload_rejects_invalid_datapoint(payload, error_fragment):
    point, error = _normalize_payload(payload)

    assert point is None
    assert error_fragment in error


def test_normalize_payload_rejects_non_dict_payload():
    point, error = _normalize_payload(["not", "a", "dict"])

    assert point is None
    assert error == "payload is not a dict"


@pytest.mark.asyncio
async def test_flush_batch_writes_points_to_repository():
    repository = RecordingRepository()
    hub = AsyncMetricsHub(repository=repository)

    batch = [
        {
            "measurement": "camera_tm",
            "tags": {"device_id": "cam_01"},
            "fields": {"temperature": 23.4},
            "time": "2026-03-23T12:34:56Z",
        },
        {
            "measurement": "camera_tm",
            "tags": {"device_id": "cam_01"},
            "fields": {"pressure": 1013.2},
            "time": "2026-03-23T12:34:57Z",
        },
    ]

    await hub._flush_batch(batch)

    assert hub.stats["written"] == 2
    assert hub.stats["errors"] == 0
    assert repository.writes == [batch]


@pytest.mark.asyncio
async def test_flush_remaining_drains_queue_and_writes_points():
    repository = RecordingRepository()
    hub = AsyncMetricsHub(repository=repository)

    queued_point = {
        "measurement": "hexapod_tm",
        "tags": {"device_id": "hex_01"},
        "fields": {"x": 1.25},
        "time": "2026-03-23T12:34:56Z",
    }

    await hub.data_queue.put(queued_point)

    await hub._flush_remaining()

    assert hub.data_queue.empty()
    assert hub.stats["written"] == 1
    assert repository.writes == [[queued_point]]


def test_sync_metrics_hub_client_health_check_success():
    client = MetricsHubClient(req_endpoint="tcp://localhost:9999")
    client.req_socket = DummySyncSocket(  # type: ignore[assignment]
        poll_result=True,
        message_parts=[
            MessageType.RESPONSE.value,
            json.dumps({"success": True, "status": "ok"}).encode(),
        ],
    )

    assert client.health_check() is True


def test_sync_metrics_hub_client_server_status_timeout():
    client = MetricsHubClient(req_endpoint="tcp://localhost:9999", request_timeout=0.01)
    client.req_socket = DummySyncSocket(poll_result=False)  # type: ignore[assignment]

    response = client.server_status()

    assert response["success"] is False
    assert response["error"] == "Request timed out"


def test_sync_metrics_hub_client_terminate_no_reply():
    client = MetricsHubClient(req_endpoint="tcp://localhost:9999")
    socket = DummySyncSocket()
    client.req_socket = socket  # type: ignore[assignment]

    assert client.terminate_metrics_hub() is True
    assert socket.sent, "Terminate request should be sent to the socket"
    assert socket.sent[0][0] == MessageType.REQUEST_NO_REPLY.value


@pytest.mark.asyncio
async def test_sender_to_hub_data_path_over_zmq():
    repository = RecordingRepository()
    hub = AsyncMetricsHub(repository=repository)

    # Use a random local port to avoid clashes with any running services.
    endpoint = f"tcp://127.0.0.1:{hub.collector_socket.bind_to_random_port('tcp://127.0.0.1')}"

    hub.batch_size = 1
    hub.flush_interval = 0.05
    hub.running = True

    collector_task = asyncio.create_task(hub._collector())
    batch_task = asyncio.create_task(hub._batch_processor())

    sender = AsyncMetricsHubSender(hub_endpoint=endpoint)
    sender.connect()

    point = DataPoint.measurement("camera_tm").tag("device_id", "cam_01").field("temperature", 23.4)

    try:
        payload = json.dumps(point.as_dict()).encode()
        # Bound send wait time so the test never hangs when the peer is unavailable.
        sender.socket.setsockopt(zmq.SNDTIMEO, 200)  # type: ignore[union-attr]

        sent = False
        for _ in range(20):
            try:
                await sender.socket.send(payload)  # type: ignore[union-attr]
                sent = True
                break
            except zmq.Again:
                await asyncio.sleep(0.02)

        assert sent is True

        # Wait until the batch processor flushes the point.
        for _ in range(50):
            if repository.writes:
                break
            await asyncio.sleep(0.02)

        assert repository.writes, "Expected at least one write from sender->hub pipeline."

        flushed = repository.writes[0][0]
        assert flushed["measurement"] == "camera_tm"
        assert flushed["tags"]["device_id"] == "cam_01"
        assert flushed["fields"]["temperature"] == 23.4
    finally:
        sender.close()

        hub.running = False
        collector_task.cancel()
        batch_task.cancel()

        await asyncio.gather(collector_task, batch_task, return_exceptions=True)

        hub.collector_socket.close(linger=0)
        hub.requests_socket.close(linger=0)
        hub.context.term()


def test_sync_sender_send_success_with_datapoint():
    sender = MetricsHubSender(hub_endpoint="tcp://localhost:9999")
    sender.socket = DummySyncPushSocket()  # type: ignore[assignment]

    point = DataPoint.measurement("camera_tm").tag("device_id", "cam_01").field("temperature", 23.4)
    assert sender.send(point) is True
    assert sender.socket.sent_payloads, "Expected payload to be sent"  # type: ignore[union-attr]


def test_sync_sender_send_returns_false_when_queue_full():
    sender = MetricsHubSender(hub_endpoint="tcp://localhost:9999")
    sender.socket = DummySyncPushSocket(should_raise_again=True)  # type: ignore[assignment]

    point = DataPoint.measurement("camera_tm").field("temperature", 23.4)
    assert sender.send(point) is False


@pytest.mark.asyncio
async def test_control_requests_health_info_terminate_in_process():
    repository = RecordingRepository()
    hub = AsyncMetricsHub(repository=repository)

    requests_port = hub.requests_socket.bind_to_random_port("tcp://127.0.0.1")
    req_endpoint = f"tcp://127.0.0.1:{requests_port}"

    hub.running = True
    request_task = asyncio.create_task(hub._handle_requests())

    try:
        await asyncio.sleep(0.05)

        with AsyncMetricsHubClient(req_endpoint=req_endpoint, request_timeout=1.0) as client:
            assert await client.health_check() is True

            info = await client.server_status()
            assert info["success"] is True
            assert info["status"] == "ok"
            assert info["requests_port"] == requests_port
            assert info["backend"]["name"] == "injected"
            assert info["backend"]["repository_class"] == "RecordingRepository"
            assert info["backend"]["reachable"] is True
            assert info["statistics"]["queue"] == 0

            terminated = await client.terminate_metrics_hub()
            assert terminated is True

        assert hub._shutdown_event.is_set()
    finally:
        hub.running = False
        request_task.cancel()
        await asyncio.gather(request_task, return_exceptions=True)

        hub.collector_socket.close(linger=0)
        hub.requests_socket.close(linger=0)
        hub.context.term()
