"""Async Metrics Hub — core service for receiving and persisting telemetry/HK data.

Clients send `DataPoint` objects serialized as JSON to the
PULL socket.  The hub batches the incoming points and flushes them to the
configured storage backend (InfluxDB, DuckDB, `...`) via the plugin system in
`egse.plugins.metrics`.

Backend selection is driven by the environment variable `CGSE_METRICS_BACKEND`
(default: `"influxdb"`).  Backend-specific configuration is picked up from the
environment inside the respective plugin (e.g. `CGSE_INFLUX_*` for InfluxDB).
DuckDB additionally requires `CGSE_DUCKDB_PATH`.
"""

import asyncio
import json
import logging
import multiprocessing
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from typing import Callable

import typer
import zmq
import zmq.asyncio
from egse.env import bool_env
from egse.env import float_env
from egse.env import int_env
from egse.env import str_env
from egse.log import logger
from egse.metrics import TimeSeriesRepository
from egse.metrics import get_metrics_repo
from egse.settings import Settings
from egse.system import TyperAsyncCommand
from egse.system import get_host_ip
from egse.zmq_ser import get_port_number

from egse.logger import remote_logging
from egse.metricshub import DEFAULT_COLLECTOR_PORT
from egse.metricshub import DEFAULT_REQUESTS_PORT
from egse.metricshub import PROCESS_NAME
from egse.metricshub import SERVICE_TYPE
from egse.metricshub import STATS_INTERVAL
from egse.metricshub.client import AsyncMetricsHubClient
from egse.registry import MessageType
from egse.registry.client import REQUEST_TIMEOUT
from egse.registry.client import AsyncRegistryClient

REQUEST_POLL_TIMEOUT = 1.0
"""Time to wait while listening for requests [seconds]."""

app = typer.Typer(name=PROCESS_NAME)

settings = Settings.load("Metrics Hub")

# Note: if you need these helpers also in other services, consider moving them to the package `cgse-common`,
#       module `egse.settings` instead of importing from this server module.


def _env_or_settings_str(env_name: str, setting_name: str, default: str) -> str:
    return str_env(env_name, str(settings.get(setting_name, default)))


def _env_or_settings_int(env_name: str, setting_name: str, default: int) -> int:
    return int_env(env_name, int(settings.get(setting_name, default)))


def _env_or_settings_float(env_name: str, setting_name: str, default: float) -> float:
    return float_env(env_name, float(settings.get(setting_name, default)))


def _env_or_settings_bool(env_name: str, setting_name: str, default: bool) -> bool:
    return bool_env(env_name, bool(settings.get(setting_name, default)))


def _get_backend_config() -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Resolve backend name/config and return a safe public info dict.

    The backend is selected via ``CGSE_METRICS_BACKEND`` (default ``"influxdb"``).
    """
    backend = _env_or_settings_str("CGSE_METRICS_BACKEND", "BACKEND", "influxdb").strip().lower()

    match backend:
        case "influxdb":
            host = str_env("CGSE_INFLUX_HOST", "http://localhost:8181")
            database = str_env("CGSE_INFLUX_DATABASE", str_env("PROJECT", "cgse"))
            config = {
                "host": host,
                "database": database,
                "token": str_env("INFLUXDB3_AUTH_TOKEN", ""),
            }
            public_info = {
                "name": backend,
                "host": host,
                "database": database,
            }
        case "duckdb":
            db_path = str_env("CGSE_DUCKDB_PATH", "metrics.duckdb")
            config = {
                "db_path": db_path,
            }
            public_info = {
                "name": backend,
                "db_path": db_path,
            }
        case _:
            raise ValueError(f"Unknown CGSE_METRICS_BACKEND '{backend}'. Supported: 'influxdb', 'duckdb'.")

    return backend, config, public_info


def _load_repository() -> tuple[TimeSeriesRepository, dict[str, Any]]:
    """Build a `TimeSeriesRepository` and safe backend metadata."""
    backend, config, public_info = _get_backend_config()
    return get_metrics_repo(backend, config), public_info


class AsyncMetricsHub:
    """Async metrics hub that collects DataPoint messages and batches them to a
    time-series backend via the plugin system.

    Sockets
    -------
    collector_socket (PULL)
        Receives serialized `DataPoint` JSON from services.
    requests_socket (ROUTER)
        Handles control requests: health, info, terminate.
    """

    def __init__(self, repository: TimeSeriesRepository | None = None):
        self.server_id = PROCESS_NAME

        self.context: zmq.asyncio.Context = zmq.asyncio.Context()

        # Receive DataPoint dicts from services (PULL for implicit load balancing)
        self.collector_socket: zmq.asyncio.Socket = self.context.socket(zmq.PULL)

        # Health check / control (ROUTER - can handle multiple concurrent clients)
        self.requests_socket: zmq.asyncio.Socket = self.context.socket(zmq.ROUTER)

        # Service registry
        self.registry_client = AsyncRegistryClient(timeout=REQUEST_TIMEOUT)

        self.service_id = None
        self.service_name = PROCESS_NAME
        self.service_type = SERVICE_TYPE
        self.is_service_registered: bool = False

        # Storage backend — loaded from env when not injected (e.g. in tests)
        self._repository_injected = repository is not None
        self.repository: TimeSeriesRepository | None = repository  # may be None until start()
        self.backend_info: dict[str, Any] = (
            {
                "name": "injected",
                "repository_class": type(repository).__name__,
                "injected": True,
            }
            if repository is not None
            else {"name": "unknown", "injected": False}
        )

        # Batching configuration (from env, then settings, with sensible defaults)
        self.batch_size: int = _env_or_settings_int("CGSE_METRICS_BATCH_SIZE", "BATCH_SIZE", 1_000)
        self.max_batch_size: int = _env_or_settings_int("CGSE_METRICS_MAX_BATCH_SIZE", "MAX_BATCH_SIZE", 5_000)
        self.flush_interval: float = _env_or_settings_float("CGSE_METRICS_FLUSH_INTERVAL", "FLUSH_INTERVAL", 2.0)
        self.flush_concurrency: int = _env_or_settings_int("CGSE_METRICS_FLUSH_CONCURRENCY", "FLUSH_CONCURRENCY", 8)
        self.debug_counters_enabled: bool = _env_or_settings_bool(
            "CGSE_METRICS_DEBUG_COUNTERS", "DEBUG_COUNTERS", False
        )
        self.queue_maxsize: int = _env_or_settings_int("CGSE_METRICS_QUEUE_MAXSIZE", "QUEUE_MAXSIZE", 10_000)
        self.collector_rcvhwm: int = _env_or_settings_int("CGSE_METRICS_COLLECTOR_RCVHWM", "COLLECTOR_RCVHWM", 10_000)
        self.collector_yield_every: int = _env_or_settings_int(
            "CGSE_METRICS_COLLECTOR_YIELD_EVERY", "COLLECTOR_YIELD_EVERY", 250
        )
        self.batch_drain_limit: int = _env_or_settings_int("CGSE_METRICS_BATCH_DRAIN_LIMIT", "BATCH_DRAIN_LIMIT", 1_000)
        self.info_ping_timeout: float = _env_or_settings_float(
            "CGSE_METRICS_INFO_PING_TIMEOUT", "INFO_PING_TIMEOUT", 0.5
        )
        self.backlog_high_watermark: float = _env_or_settings_float(
            "CGSE_METRICS_BACKLOG_HIGH_WATERMARK", "BACKLOG_HIGH_WATERMARK", 0.20
        )

        # Internal queue: raw dicts as received from ZMQ
        self.data_queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_maxsize)

        self.stats = {
            "received": 0,
            "written": 0,
            "dropped": 0,
            "errors": 0,
            "write_batches": 0,
            "last_batch_size": 0,
            "last_write_s": 0.0,
            "avg_write_s": 0.0,
            "filtered_none_fields": 0,
            "filtered_none_tags": 0,
            "dropped_all_none_fields": 0,
            "start_time": time.time(),
        }

        self._last_queue_full_log_ts = 0.0
        self._flush_semaphore: asyncio.Semaphore | None = None  # initialized in start()
        self._pending_flushes: set[asyncio.Task] = set()
        self._write_executor: ThreadPoolExecutor | None = None

        self.running = False
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

        self._logger = logging.getLogger("egse.metricshub")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the metrics hub.

        Binds the ZMQ sockets, connects to the storage backend, creates the
        asyncio tasks, registers with the service registry, and then waits for a
        shutdown signal.
        """
        multiprocessing.current_process().name = PROCESS_NAME

        self.running = True
        self._logger.info("Starting Async Metrics Hub...")

        self.collector_socket.bind(f"tcp://*:{DEFAULT_COLLECTOR_PORT}")
        self.requests_socket.bind(f"tcp://*:{DEFAULT_REQUESTS_PORT}")

        # High-water mark so the OS doesn't buffer unboundedly
        self.collector_socket.setsockopt(zmq.RCVHWM, self.collector_rcvhwm)

        if not self._repository_injected:
            self.repository, self.backend_info = _load_repository()

        self.repository.connect()  # type: ignore[union-attr]

        if not self.repository.ping():  # type: ignore[union-attr]
            raise RuntimeError(
                "Metrics Hub backend is unreachable — refusing to start. "
                "Check your backend configuration (CGSE_METRICS_BACKEND and related env vars)."
            )

        self._logger.info("Connected to storage backend.")

        self._write_executor = ThreadPoolExecutor(
            max_workers=self.flush_concurrency,
            thread_name_prefix="metricshub-write",
        )
        self._flush_semaphore = asyncio.Semaphore(self.flush_concurrency)

        self._tasks = [
            asyncio.create_task(self._collector()),
            asyncio.create_task(self._batch_processor()),
            asyncio.create_task(self._stats_reporter()),
            asyncio.create_task(self._handle_requests()),
        ]

        await self.registry_client.connect()

        await self.register_service()

        await self._shutdown_event.wait()

        await self.deregister_service()

        await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown: flush remaining points, cancel tasks, close sockets."""
        self.running = False
        self._logger.info("Async Metrics Hub shutdown initiated...")

        if self._tasks:
            done, pending = await asyncio.wait(self._tasks, timeout=2.0)
            for task in pending:
                task.cancel()

        await self._flush_remaining()

        if self._write_executor is not None:
            self._write_executor.shutdown(wait=True)
            self._write_executor = None

        self.repository.close()  # type: ignore[union-attr]

        self.collector_socket.close()
        self.requests_socket.close()

        await self.registry_client.disconnect()

        self._logger.info("Async Metrics Hub shutdown complete.")

        self.context.term()

    async def register_service(self):
        self._logger.info("Registering Metrics Hub with service registry...")

        requests_port = get_port_number(self.requests_socket)
        collector_port = get_port_number(self.collector_socket)

        self.service_id = await self.registry_client.register(
            name=self.service_name,
            host=get_host_ip() or "127.0.0.1",
            port=requests_port,
            service_type=self.service_type,
            metadata={"collector_port": collector_port},
        )

        if not self.service_id:
            self._logger.error("Failed to register with the service registry.")
            self.is_service_registered = False
        else:
            await self.registry_client.start_heartbeat()
            self.is_service_registered = True

    async def deregister_service(self):
        self._logger.info("De-registering Metrics Hub from service registry...")
        if self.service_id:
            await self.registry_client.stop_heartbeat()
            await self.registry_client.deregister()

    # ------------------------------------------------------------------
    # Core async tasks
    # ------------------------------------------------------------------

    async def _collector(self):
        """Receive serialized DataPoint JSON from ZMQ PULL socket and queue it."""
        self._logger.info("Collector task started.")
        points_since_yield = 0

        while self.running:
            try:
                message_bytes = await self.collector_socket.recv()
            except asyncio.CancelledError:
                self._logger.warning("Collector task cancelled.")
                self.running = False
                break
            except Exception as exc:
                self._logger.error(f"Collector error: {exc}", exc_info=True)
                await asyncio.sleep(0.1)
                continue

            try:
                payload = json.loads(message_bytes.decode())
            except json.JSONDecodeError as exc:
                self._logger.warning(f"Received invalid JSON, discarding: {exc}")
                self.stats["dropped"] += 1
                continue

            point_dict, error = _normalize_payload(payload)
            if point_dict is None:
                if self.debug_counters_enabled and error == "all field values are None":
                    self.stats["dropped_all_none_fields"] += 1
                self._logger.warning(f"Received malformed payload, discarding: {error}")
                self.stats["dropped"] += 1
                continue

            if self.debug_counters_enabled and isinstance(payload, dict):
                fields = payload.get("fields")
                if isinstance(fields, dict):
                    self.stats["filtered_none_fields"] += sum(1 for value in fields.values() if value is None)

                tags = payload.get("tags")
                if isinstance(tags, dict):
                    self.stats["filtered_none_tags"] += sum(1 for value in tags.values() if value is None)

            try:
                self.data_queue.put_nowait(point_dict)
                self.stats["received"] += 1
            except asyncio.QueueFull:
                now = time.monotonic()
                if now - self._last_queue_full_log_ts > 1.0:
                    self._logger.warning("Queue full - dropping points.")
                    self._last_queue_full_log_ts = now
                self.stats["dropped"] += 1

            # Yield to the event loop every N points to keep the request handler responsive under sustained load.
            points_since_yield += 1
            if points_since_yield >= self.collector_yield_every:
                points_since_yield = 0
                await asyncio.sleep(0)

    async def _batch_processor(self):
        """Drain the queue and flush to the storage backend in batches."""
        self._logger.info("Batch processor task started.")

        batch: list[dict] = []
        last_flush = time.monotonic()

        while self.running:
            try:
                target_batch_size = self.batch_size
                qsize = self.data_queue.qsize()
                if self.queue_maxsize > 0 and (qsize / self.queue_maxsize) >= self.backlog_high_watermark:
                    target_batch_size = max(self.batch_size, self.max_batch_size)
                effective_drain_limit = max(self.batch_drain_limit, target_batch_size)

                remaining = self.flush_interval - (time.monotonic() - last_flush)
                timeout = max(0.05, remaining)

                # Always await here — this is the guaranteed yield point that keeps
                # the event loop (and the request handler) responsive under sustained load.
                try:
                    point_dict = await asyncio.wait_for(self.data_queue.get(), timeout=timeout)
                    batch.append(point_dict)
                except asyncio.TimeoutError:
                    pass  # check flush conditions below

                # Drain any additional queued points without yielding, capped so we
                # do not spin long enough to starve other tasks.
                drained = 0
                while len(batch) < target_batch_size and drained < effective_drain_limit:
                    try:
                        batch.append(self.data_queue.get_nowait())
                        drained += 1
                    except asyncio.QueueEmpty:
                        break

                should_flush = len(batch) >= target_batch_size or (
                    batch and (time.monotonic() - last_flush) >= self.flush_interval
                )

                if should_flush:
                    # Acquire a slot before handing off.  This yields to the event
                    # loop (request handler stays responsive) and provides backpressure
                    # when InfluxDB can't absorb writes as fast as they arrive.
                    await self._flush_semaphore.acquire()  # type: ignore[union-attr]
                    task = asyncio.create_task(self._run_flush(batch))
                    self._pending_flushes.add(task)
                    task.add_done_callback(self._pending_flushes.discard)
                    batch = []  # rebind — old list is now owned by the flush task
                    last_flush = time.monotonic()

            except asyncio.CancelledError:
                self._logger.warning("Batch processor task cancelled.")
                break
            except Exception as exc:
                self._logger.error(f"Batch processor error: {exc}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _run_flush(self, batch: list[dict]):
        """Semaphore-owning flush wrapper used by concurrent tasks.

        The semaphore slot was acquired by _batch_processor; this method always
        releases it on completion so the slot is never leaked.
        """
        try:
            await self._flush_batch(batch)
        finally:
            self._flush_semaphore.release()  # type: ignore[union-attr]

    async def _flush_batch(self, batch: list[dict]):
        """Write a batch of point dicts to the storage backend.

        The write call is dispatched to a thread-pool executor so that blocking
        backend clients (e.g. influxdb_client_3, duckdb) do not stall the event
        loop.
        """
        if not batch:
            return

        start = time.monotonic()
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._write_executor, lambda: self.repository.write(batch))  # type: ignore[union-attr]

            elapsed = time.monotonic() - start
            rate = len(batch) / elapsed if elapsed > 0 else float("inf")
            self.stats["written"] += len(batch)
            self.stats["write_batches"] += 1
            self.stats["last_batch_size"] = len(batch)
            self.stats["last_write_s"] = elapsed
            write_batches = self.stats["write_batches"]
            self.stats["avg_write_s"] += (elapsed - self.stats["avg_write_s"]) / write_batches
            self._logger.debug(f"Flushed {len(batch)} points ({rate:.0f} pts/s).")

        except Exception as exc:
            self._logger.error(f"Failed to write batch of {len(batch)} points: {exc}", exc_info=True)
            self.stats["errors"] += len(batch)

    async def _flush_remaining(self):
        """Wait for in-flight flushes, then drain the queue and write what's left."""
        if self._pending_flushes:
            self._logger.info(f"Waiting for {len(self._pending_flushes)} in-flight flush task(s)...")
            await asyncio.gather(*list(self._pending_flushes), return_exceptions=True)

        remaining: list[dict] = []
        while not self.data_queue.empty():
            try:
                remaining.append(self.data_queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if remaining:
            self._logger.info(f"Flushing {len(remaining)} remaining points on shutdown.")
            await self._flush_batch(remaining)

    async def _stats_reporter(self):
        """Periodically log batch statistics."""
        while self.running:
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=STATS_INTERVAL)
                break  # shutdown was requested
            except asyncio.TimeoutError:
                uptime = max(1e-6, time.monotonic() - self.stats["start_time"])
                recv_rate = self.stats["received"] / uptime
                write_rate = self.stats["written"] / uptime
                self._logger.info(
                    f"Stats: received={self.stats['received']}, "
                    f"written={self.stats['written']}, "
                    f"dropped={self.stats['dropped']}, "
                    f"errors={self.stats['errors']}, "
                    f"queue={self.data_queue.qsize()}/{self.queue_maxsize}, "
                    f"recv_rate={recv_rate:.0f}/s, "
                    f"write_rate={write_rate:.0f}/s, "
                    f"pending_flushes={len(self._pending_flushes)}, "
                    f"last_batch={self.stats['last_batch_size']}, "
                    f"last_write={self.stats['last_write_s'] * 1000:.1f}ms, "
                    f"avg_write={self.stats['avg_write_s'] * 1000:.1f}ms"
                )
            except asyncio.CancelledError:
                self._logger.warning("Stats reporter task cancelled.")
                self.running = False

    # ------------------------------------------------------------------
    # Request handling (ROUTER socket)
    # ------------------------------------------------------------------

    async def _handle_requests(self):
        """Process control requests on the ROUTER socket."""
        self._logger.info("Request handler task started.")

        while self.running:
            try:
                try:
                    message_parts = await asyncio.wait_for(
                        self.requests_socket.recv_multipart(), timeout=REQUEST_POLL_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    continue

                if len(message_parts) >= 3:
                    client_id = message_parts[0]
                    message_type = MessageType(message_parts[1])
                    message_data = message_parts[2]

                    response = await self._process_request(message_data)
                    await self._send_response(client_id, message_type, response)

            except zmq.ZMQError as exc:
                self._logger.error(f"ZMQ error in request handler: {exc}", exc_info=True)
            except asyncio.CancelledError:
                self._logger.warning("Request handler task cancelled.")
                self.running = False
            except Exception as exc:
                self._logger.error(f"Unexpected error in request handler: {exc}", exc_info=True)

    async def _process_request(self, msg_data: bytes) -> dict[str, Any]:
        try:
            request = json.loads(msg_data.decode())
        except json.JSONDecodeError as exc:
            self._logger.error(f"Invalid JSON in request: {exc}")
            return {"success": False, "error": "Invalid JSON format"}

        action = request.get("action")
        if not action:
            return {"success": False, "error": "Missing required field: action"}

        handlers: dict[str, Callable] = {
            "health": self._handle_health,
            "info": self._handle_info,
            "terminate": self._handle_terminate,
        }

        handler = handlers.get(action)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action}"}

        return await handler(request)

    async def _send_response(self, client_id: bytes, msg_type: MessageType, response: dict[str, Any]):
        if msg_type == MessageType.REQUEST_WITH_REPLY:
            await self.requests_socket.send_multipart(
                [client_id, MessageType.RESPONSE.value, json.dumps(response).encode()]
            )

    async def _handle_health(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "status": "ok", "timestamp": int(time.time())}

    async def _backend_reachable(self) -> bool:
        """Return backend connectivity state, shielding request handling from ping errors."""
        if self.repository is None:
            return False

        try:
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.repository.ping),
                timeout=self.info_ping_timeout,
            )
        except asyncio.TimeoutError:
            self._logger.warning(f"Backend ping timed out after {self.info_ping_timeout:.2f}s while serving info.")
            return False
        except Exception as exc:
            self._logger.warning(f"Backend ping failed while serving info: {exc}")
            return False

    async def _handle_info(self, request: dict[str, Any]) -> dict[str, Any]:
        backend_info = self.backend_info.copy()
        if self.repository is not None:
            backend_info["repository_class"] = type(self.repository).__name__
        backend_info["reachable"] = await self._backend_reachable()
        statistics = self.stats.copy()
        statistics["queue"] = self.data_queue.qsize()
        statistics["queue_maxsize"] = self.queue_maxsize
        statistics["debug_counters_enabled"] = self.debug_counters_enabled
        statistics["pending_flushes"] = len(self._pending_flushes)

        return {
            "success": True,
            "status": "ok",
            "collector_port": get_port_number(self.collector_socket),
            "requests_port": get_port_number(self.requests_socket),
            "backend": backend_info,
            "batch_size": self.batch_size,
            "max_batch_size": self.max_batch_size,
            "flush_interval": self.flush_interval,
            "flush_concurrency": self.flush_concurrency,
            "backlog_high_watermark": self.backlog_high_watermark,
            "statistics": statistics,
            "timestamp": int(time.time()),
        }

    async def _handle_terminate(self, request: dict[str, Any]) -> dict[str, Any]:
        self._logger.info("Termination requested via control socket.")
        await self.stop()
        return {"success": True, "status": "terminating", "timestamp": int(time.time())}

    async def stop(self):
        """Signal the hub to shut down."""
        self._shutdown_event.set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_payload(payload: Any) -> tuple[dict | None, str | None]:
    """Validate and normalize a DataPoint-style payload.

    The expected input shape is compatible with `DataPoint.as_dict()`:

    - `measurement`: non-empty `str`
    - `fields`: `dict` with non-empty string keys
    - `tags`: optional `dict` with non-empty string keys
    - `time` (or `timestamp`): optional `str` | `int` | `float`

    Normalization and filtering rules:

    - `None` field values are removed.
    - `None` tag values are removed.
    - If all field values are removed, the payload is rejected.
    - `timestamp` is accepted as an alias for `time`.
    - Only key/type validation is performed; value domain constraints are left
      to downstream storage backends.

    Args:
        payload: Raw decoded JSON payload received by the collector.

    Returns:
        `(point_dict, None)` on success, where `point_dict` has keys
        `measurement`, `fields`, `tags` and optional `time`.

        `(None, error_message)` on validation failure.
    """
    if not isinstance(payload, dict):
        return None, "payload is not a dict"

    measurement = payload.get("measurement")
    fields = payload.get("fields")
    tags = payload.get("tags", {})
    timestamp = payload.get("time", payload.get("timestamp"))

    if not isinstance(measurement, str) or not measurement.strip():
        return None, "missing/invalid 'measurement'"
    if not isinstance(fields, dict) or len(fields) == 0:
        return None, "missing/invalid 'fields'"
    if not isinstance(tags, dict):
        return None, "invalid 'tags'"

    # keep field values compatible with downstream backends
    cleaned_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not key:
            return None, "field keys must be non-empty strings"
        if value is not None:
            cleaned_fields[key] = value

    if not cleaned_fields:
        return None, "all field values are None"

    cleaned_tags: dict[str, Any] = {}
    for key, value in tags.items():
        if not isinstance(key, str) or not key:
            return None, "tag keys must be non-empty strings"
        if value is not None:
            cleaned_tags[key] = value

    if timestamp is not None and not isinstance(timestamp, (str, int, float)):
        return None, "invalid timestamp/time"

    point = {
        "measurement": measurement,
        "fields": cleaned_fields,
        "tags": cleaned_tags,
    }
    if timestamp is not None:
        point["time"] = timestamp
    return point, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.command(cls=TyperAsyncCommand)
async def start():
    """Start the Metrics Hub service."""
    with remote_logging():
        hub = AsyncMetricsHub()
        await hub.start()


@app.command(cls=TyperAsyncCommand)
async def stop():
    """Stop a running Metrics Hub service."""
    with AsyncMetricsHubClient() as client:
        await client.terminate_metrics_hub()


@app.command(cls=TyperAsyncCommand)
async def status():
    """Show the current status of the Metrics Hub service."""
    with AsyncMetricsHubClient() as client:
        response = await client.server_status()

    if response.get("success"):
        stats = response.get("statistics", {})
        backend = response.get("backend", {})

        backend_name = backend.get("name", "unknown")
        backend_reachable = backend.get("reachable", "?")
        repository_class = backend.get("repository_class", "?")

        backend_details_parts: list[str] = []
        if "host" in backend:
            backend_details_parts.append(f"host={backend['host']}")
        if "database" in backend:
            backend_details_parts.append(f"database={backend['database']}")
        if "db_path" in backend:
            backend_details_parts.append(f"db_path={backend['db_path']}")
        backend_details = ", ".join(backend_details_parts) if backend_details_parts else "n/a"

        status_report = textwrap.dedent(
            f"""\
            Metrics Hub:
                Status:          {response["status"]}
                Collector port:  {response["collector_port"]}
                Requests port:   {response["requests_port"]}
                Backend:         {backend_name}
                  Reachable:     {backend_reachable}
                  Repository:    {repository_class}
                  Details:       {backend_details}
                Batch size:      {response["batch_size"]}
                Max batch size:  {response.get("max_batch_size", response["batch_size"])}
                Flush interval:  {response["flush_interval"]} s
                Flush concur.:   {response.get("flush_concurrency", "?")}
                Backlog HWM:     {response.get("backlog_high_watermark", "?")}
                Statistics:
                    Received:    {stats.get("received", 0)}
                    Written:     {stats.get("written", 0)}
                    Dropped:     {stats.get("dropped", 0)}
                    Errors:      {stats.get("errors", 0)}
                    Queue size:  {stats.get("queue", "?")} / {stats.get("queue_maxsize", "?")}
                    Pending flushes: {stats.get("pending_flushes", 0)}
                    Last batch:  {stats.get("last_batch_size", 0)}
                    Last write:  {stats.get("last_write_s", 0.0) * 1000:.1f} ms
                    Avg write:   {stats.get("avg_write_s", 0.0) * 1000:.1f} ms
                    None fields: {stats.get("filtered_none_fields", 0)}
                    None tags:   {stats.get("filtered_none_tags", 0)}
                    All-None:    {stats.get("dropped_all_none_fields", 0)}
                    Debug counters:  {stats.get("debug_counters_enabled", True)}
            """
        )
    else:
        status_report = "Metrics Hub: not active"

    # print(response)
    print(status_report)


if __name__ == "__main__":
    try:
        rc = app()
    except zmq.ZMQError as exc:
        if "Address already in use" in str(exc):
            logger.error(f"The Metrics Hub is already running: {exc}")
        else:
            logger.error("Couldn't start the Metrics Hub.", exc_info=True)
        rc = -1
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received for MetricsHub, terminating...")
        rc = -1

    sys.exit(rc)
