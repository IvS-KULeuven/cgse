"""Template DAQ Control Server Implementation.

This module serves as a comprehensive template for implementing asynchronous DAQ (Data Acquisition)
control servers in the CGSE framework. It demonstrates best practices for integrating hardware DAQ
devices with the asynchronous command-based control architecture.

**Key Architectural Components:**

1. `TempController` — A `DeviceCommandRouter` subclass that handles device-specific commands
   (start-scan, stop-scan, scan-status, etc.). It implements a command guard pattern that blocks
   certain commands while a scan is running to prevent conflicts with ongoing DAQ operations.

2. `TempControlServer` — An `AcquisitionAsyncControlServer` subclass that manages the lifecycle
   of DAQ operations, including the background scan loop that reads data and forwards it to
   metric sinks (database, InfluxDB, etc.).

3. `TempServiceRouter` — A `ServiceCommandRouter` for handling service-level commands like
   health checks and component info.

**Core Patterns and Best Practices:**

- **Command Handlers:** Implement commands in the router, keeping them fast and non-blocking.
  Delegate long-running work (e.g., scanning) to background tasks in the control server.

- **Command Guard:** Use `ALLOWED_DURING_SCAN` to define which commands are safe to execute while
  a scan is active. The framework will reject other commands with a "device-busy" error.

- **Scan Loop:** The background task `_run_scan_loop()` continuously acquires data, processes it,
  and sends it to metric sinks. This separation ensures UI/API responsiveness.

- **Status and Health:** Keep status and health commands fast and always available to enable
  real-time monitoring and diagnostics even during active scans.

- **Metrics Integration:** Implement the `_send_metric()` method to push acquired data to your
  metrics hub (e.g., InfluxDB, QuestDB). This allows centralized data aggregation and analysis.

**Adaptation Checklist:**

1. Replace `BufferedFakeDaq` with your actual DAQ driver class.
2. Customize `ALLOWED_DURING_SCAN` commands based on your hardware constraints.
3. Implement `_send_metric()` with your real metrics hub client.
4. Keep long-running scan work in `_run_scan_loop()` (background task), not in command handlers.
5. Keep status/health commands fast and always available.
6. Add focused tests for: start/stop/status behavior and acquisition-to-sink flow.

**Example Usage:**

To create a new DAQ control server from this template:

1. Copy this module and rename it (e.g., `async_mydaq.py`).
2. Replace `TempController` with `MyDaqController`.
3. Replace `BufferedFakeDaq` with your DAQ driver.
4. Update command handlers and `_run_scan_loop()` for your hardware specifics.
5. Customize metrics integration in `_send_metric()`.
6. Add tests specific to your DAQ device and expected behaviors.

See the accompanying developer checklist in the docstring below for quick reference.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import sys
import time
from pathlib import Path
from typing import Any

import typer
from egse.log import logger
from egse.metrics import DataPoint
from egse.settings import get_site_id
from egse.system import TyperAsyncCommand
from egse.zmq_ser import zmq_json_response
from rich.console import Console

from egse.async_control import AcquisitionAsyncControlServer
from egse.async_control import DeviceCommandRouter
from egse.async_control import ServiceCommandRouter
from egse.async_control import TypedAsyncControlClient
from egse.logger import remote_logging
from egse.metricshub.client import AsyncMetricsHubSender

SITE_ID = get_site_id()


class TempController(DeviceCommandRouter):
    """
    Device command router with scan-time command guard policy.

    Certain commands are blocked while a scan is running to avoid conflicts with the DAQ operations.

    The commands that are allowed during a scan are defined in the ALLOWED_DURING_SCAN set. All other commands will
    be rejected with a "device-busy" error if a scan is currently running.

    Current allowed-during-scan commands are:
    - scan-status: Get the current status of the scan and DAQ.
    - stop-scan: Stop the DAQ scan.
    - get-latest: Retrieve the latest sample reading received from the DAQ.

    The full list of commands implemented in this router includes:
    - start-scan: Start a buffered DAQ scan with optional duration and chunking parameters.
    - stop-scan: Stop the DAQ scan.
    - scan-status: Get the current status of the scan and DAQ.
    - set-sensors: Configure the list of sensor IDs to read from.
    - set-interval: Set the sample interval for the DAQ.
    - get-latest: Retrieve the latest sample reading received from the DAQ.

    """

    ALLOWED_DURING_SCAN = {"scan-status", "stop-scan", "get-latest"}

    def __init__(self, control_server: "TempControlServer"):
        super().__init__(control_server)
        self._cs = control_server

    def register_handlers(self):
        self.add_handler("start-scan", self._start_scan)
        self.add_handler("stop-scan", self._stop_scan)
        self.add_handler("scan-status", self._scan_status)
        self.add_handler("set-sensors", self._set_sensors)
        self.add_handler("set-interval", self._set_interval)
        self.add_handler("set-setpoint", self._set_setpoint)
        self.add_handler("get-latest", self._get_latest)

    def _deny_if_not_allowed_during_scan(self, command_name: str) -> list | None:
        """Check if the given command is allowed while a scan is running. If not allowed,
        return a JSON response indicating the device is busy. If allowed, return None."""

        if self._cs.is_scan_running() and command_name not in self.ALLOWED_DURING_SCAN:
            return zmq_json_response(
                {
                    "success": False,
                    "message": {
                        "error": "device-busy",
                        "state": "scanning",
                        "detail": f"Command '{command_name}' is blocked while scan is running.",
                        "allowed during scan": sorted(self.ALLOWED_DURING_SCAN),
                    },
                }
            )
        return None

    async def _start_scan(self, cmd: dict[str, Any]) -> list:
        """Start a buffered DAQ scan with optional parameters.
        The command will be rejected if a scan is already running to avoid conflicts.

        Allowed parameters:

        - duration_s: Optional duration in seconds for the scan. If not provided or 0, the scan will run until stopped.
        - chunk_size: Number of samples to read per buffer read operation. Default is 16.
        - poll_interval_s: Optional sleep interval in seconds between buffer reads to reduce CPU usage.
            Default is 0.2s. Set to 0 for no sleeping.

        """

        blocked = self._deny_if_not_allowed_during_scan("start-scan")
        if blocked:
            return blocked

        duration_s = float(cmd.get("duration_s", 0.0))
        chunk_size = int(cmd.get("chunk_size", 16))
        poll_interval_s = float(cmd.get("poll_interval_s", 0.2))

        started = await self._cs.start_scan(
            duration_s=duration_s,
            chunk_size=chunk_size,
            poll_interval_s=poll_interval_s,
        )

        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "running": self._cs.is_scan_running(),
                    "started": started,
                    "status": self._cs.get_scan_status(),
                },
            }
        )

    async def _stop_scan(self, cmd: dict[str, Any]) -> list:
        """Stop the DAQ scan if it is running. Returns the updated scan status."""
        stopped = await self._cs.stop_scan()
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "stopped": stopped,
                    "status": self._cs.get_scan_status(),
                },
            }
        )

    async def _scan_status(self, cmd: dict[str, Any]) -> list:
        return zmq_json_response({"success": True, "message": self._cs.get_scan_status()})

    async def _set_sensors(self, cmd: dict[str, Any]) -> list:
        blocked = self._deny_if_not_allowed_during_scan("set-sensors")
        if blocked:
            return blocked

        sensor_ids = [str(x) for x in cmd.get("sensor_ids", [])]
        if not sensor_ids:
            return zmq_json_response({"success": False, "message": {"error": "sensor_ids may not be empty"}})

        self._cs.daq.set_sensor_ids(sensor_ids)
        return zmq_json_response({"success": True, "message": {"sensor_ids": sensor_ids}})

    async def _set_setpoint(self, cmd: dict[str, Any]) -> list:
        # Example of a command that would be blocked during a scan to prevent unsafe reconfiguration.
        blocked = self._deny_if_not_allowed_during_scan("set-setpoint")
        if blocked:
            return blocked

        setpoint_c = float(cmd.get("setpoint_c", 25.0))
        self._cs.daq.set_setpoint(setpoint_c)

        return zmq_json_response({"success": True, "message": {"setpoint_c": setpoint_c}})

    async def _set_interval(self, cmd: dict[str, Any]) -> list:
        blocked = self._deny_if_not_allowed_during_scan("set-interval")
        if blocked:
            return blocked

        interval_s = float(cmd.get("interval_s", 1.0))
        if interval_s <= 0:
            return zmq_json_response({"success": False, "message": {"error": "interval_s must be > 0"}})

        self._cs.daq.set_sample_interval(interval_s)
        return zmq_json_response({"success": True, "message": {"interval_s": interval_s}})

    async def _get_latest(self, cmd: dict[str, Any]) -> list:
        return zmq_json_response({"success": True, "message": {"latest": self._cs.latest_sample}})


class TempServices(ServiceCommandRouter):
    def __init__(self, control_server: "TempControlServer"):
        super().__init__(control_server)
        self._cs = control_server

    def register_handlers(self):
        self.add_handler("health", self._health)

    async def _health(self, cmd: dict[str, Any]) -> list:
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "status": "ok",
                    "scan": self._cs.get_scan_status(),
                    "written_csv": self._cs.csv_count,
                    "sent_metrics": self._cs.metrics_count,
                    "failed_metrics": self._cs.metrics_failed_count,
                },
            }
        )


class TempControlServer(AcquisitionAsyncControlServer):
    """Temperature control server example for buffered DAQ scans.

    This class demonstrates a minimal but practical pattern for DAQs that do not
    provide callback-based streaming and instead expose scan start/stop plus
    buffered reads.

    Runtime model:
    1. Device commands (`start-scan`, `stop-scan`, `scan-status`, etc.) are
        handled by `TempController`.
    2. `start_scan` starts DAQ acquisition and spawns `_run_scan_loop` as an
        asyncio background task.
    3. `_run_scan_loop` periodically pulls chunks from the DAQ buffer and pushes
        each sample into the acquisition pipeline via `on_acquisition_data`.
    4. `AcquisitionAsyncControlServer` queues these records and dispatches them
        to `handle_acquisition`, where sink logic is implemented.

    Data sinks implemented here:
    - CSV append in `_append_csv_row`.
    - Metrics forwarding hook in `_send_metric` (stub to replace with real
       metrics hub client).

    Responsiveness and safety:
    - Long-running scan work is done in a background task, so command handling
       stays responsive.
    - DAQ blocking operations are offloaded with `asyncio.to_thread`.
    - `TempController` enforces a command whitelist while scanning to prevent
       unsafe runtime reconfiguration.
    """

    service_type = "temp-control-server"
    service_name = "temp_control_server"

    def __init__(self, service_name: str | None = None):
        self.csv_path = Path("temperature.csv")
        self.csv_count = 0
        self.metrics_count = 0
        self.metrics_failed_count = 0
        self.latest_sample: dict[str, Any] = {}
        self._metrics_sender: AsyncMetricsHubSender | None = None
        self._scan_task: asyncio.Task | None = None
        self._scan_stop_event = asyncio.Event()
        self.daq = BufferedFakeDaq(sensor_ids=["T1", "T2", "T3", "T4"], sample_interval_s=1.0)
        super().__init__()

        if service_name:
            self.service_name = service_name

        # Buffered scans can produce bursts; optional batching helps reduce overhead.
        # These variables are used in the acquisition pipeline to control batch behavior.
        self.acquisition_batch_enabled = True
        self.acquisition_batch_max_size = 200

    def create_device_command_router(self) -> DeviceCommandRouter:
        return TempController(self)

    def create_service_command_router(self) -> ServiceCommandRouter:
        return TempServices(self)

    def is_scan_running(self) -> bool:
        task = self._scan_task
        return task is not None and not task.done()

    def get_scan_status(self) -> dict[str, Any]:
        return {
            "running": self.is_scan_running(),
            "daq running": self.daq.is_running(),
            "sensor_ids": self.daq.sensor_ids,
            "interval_s": self.daq.sample_interval_s,
        }

    async def start_scan(self, *, duration_s: float, chunk_size: int, poll_interval_s: float) -> bool:
        """Start the buffered DAQ scan loop. Returns True if the scan was started, or False if a scan
        is already running. The scan is started in the background and runs until the specified duration
        elapses or stop_scan() is called.
        """

        if self.is_scan_running():
            return False

        self._scan_stop_event.clear()
        await asyncio.to_thread(self.daq.start_scan, duration_s)
        self._scan_task = asyncio.create_task(
            self._run_scan_loop(chunk_size=max(1, chunk_size), poll_interval_s=max(0.0, poll_interval_s)),
            name="temp-buffered-scan",
        )
        return True

    async def stop_scan(self) -> bool:
        """Stop the buffered DAQ scan loop. Returns True if a scan was stopped, or False if no scan was running."""
        was_running = self.is_scan_running() or self.daq.is_running()

        self._scan_stop_event.set()
        await asyncio.to_thread(self.daq.stop_scan)

        task = self._scan_task
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
            self._scan_task = None

        return was_running

    async def _run_scan_loop(self, *, chunk_size: int, poll_interval_s: float):
        try:
            while not self._scan_stop_event.is_set() and self.daq.is_running():
                chunk = await asyncio.to_thread(self.daq.read_buffer_chunk, chunk_size)
                for sample in chunk:
                    self.on_acquisition_data(sample, source="daq-buffer", metadata={"mode": "buffered-scan"})

                if poll_interval_s:
                    await asyncio.sleep(poll_interval_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.logger.error(f"Buffered scan loop failed: {exc}", exc_info=True)
        finally:
            await asyncio.to_thread(self.daq.stop_scan)

    async def handle_acquisition(
        self,
        data: Any,
        *,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ):
        # Assume DAQ gives: {"sensor_id": "...", "temperature_c": 23.4, "scan_index": ...}
        sensor_id = str(data.get("sensor_id", "unknown"))
        temp_c = float(data["temperature_c"])
        ts = timestamp or dt.datetime.now(dt.timezone.utc).isoformat()
        self.latest_sample[sensor_id] = {
            "timestamp": ts,
            "sensor_id": sensor_id,
            "temperature_c": temp_c,
            "source": source,
            "scan_index": data.get("scan_index"),
        }

        # 1) Store to CSV (offload file I/O to thread)
        await asyncio.to_thread(self._append_csv_row, [ts, sensor_id, temp_c, source or "daq"])
        self.csv_count += 1

        # 2) Send to metrics hub (replace with your real client call)
        sent = await self._send_metric("temperature_c", temp_c, tags={"sensor": sensor_id, "source": source or "daq"})
        if sent:
            self.metrics_count += 1
        else:
            self.metrics_failed_count += 1

    def _append_csv_row(self, row: list[Any]):
        new_file = not self.csv_path.exists()
        with self.csv_path.open("a", newline="") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(["timestamp", "sensor_id", "temperature_c", "source"])
            writer.writerow(row)

    async def _send_metric(self, name: str, value: float, tags: dict[str, str]) -> bool:
        # Best-effort metrics propagation: never block acquisition on sink failures.
        if self._metrics_sender is None:
            self._metrics_sender = AsyncMetricsHubSender()
            self._metrics_sender.connect()

        try:
            point = (
                DataPoint.measurement(self.service_name)
                .tag("site_id", SITE_ID)
                .tag("origin", self.service_type)
                .field(name, value)
                .time(dt.datetime.now(dt.timezone.utc))
            )

            for key, tag_value in tags.items():
                if tag_value is not None:
                    point.tag(str(key), str(tag_value))

            return await self._metrics_sender.send(point)
        except Exception as exc:
            self.logger.warning(f"Failed to send metric '{name}' to Metrics Hub: {exc!r}")
            return False

    def stop(self):
        if self.is_scan_running() and self._loop is not None and self._loop.is_running():
            self._loop.create_task(self.stop_scan())
        elif self.daq.is_running():
            self.daq.stop_scan()

        if self._metrics_sender is not None:
            self._metrics_sender.close()
            self._metrics_sender = None

        super().stop()


class BufferedFakeDaq:
    """Placeholder buffered DAQ API used by TempControlServer.

    This fake driver models common DAQ behavior where acquisition is controlled by:
    - `start_scan(duration_s)`
    - repeated `read_buffer_chunk(max_points)` calls
    - `stop_scan()`

    It intentionally has no callback-based streaming API. The control server pulls
    data chunks in its own background loop and forwards samples through the
    acquisition pipeline.

    Replace this class with your real DAQ driver, while keeping the same high-level
    contract expected by TempControlServer:
    - `is_running()` should report whether a scan is active.
    - `start_scan()` should arm/start hardware acquisition.
    - `read_buffer_chunk()` may block on hardware I/O and should return a list of
        sample dictionaries.
    - `stop_scan()` should stop acquisition safely and should be idempotent.

    Sample shape expected by the server pipeline:
    {
        "scan_index": int,
        "sensor_id": str,
        "temperature_c": float,
    }
    """

    def __init__(self, sensor_ids: list[str], sample_interval_s: float):
        self.sensor_ids = sensor_ids
        self.sample_interval_s = sample_interval_s
        self.setpoint = 25.0
        self._running = False
        self._scan_index = 0
        self._scan_end_monotonic: float | None = None

    def set_sensor_ids(self, sensor_ids: list[str]):
        self.sensor_ids = sensor_ids

    def set_sample_interval(self, sample_interval_s: float):
        self.sample_interval_s = sample_interval_s

    def set_setpoint(self, setpoint_c: float):
        self.setpoint = setpoint_c

    def is_running(self) -> bool:
        if not self._running:
            return False

        if self._scan_end_monotonic is not None and time.monotonic() >= self._scan_end_monotonic:
            self._running = False
            return False

        return True

    def start_scan(self, duration_s: float = 0.0):
        self._running = True
        self._scan_index = 0
        if duration_s and duration_s > 0:
            self._scan_end_monotonic = time.monotonic() + duration_s
        else:
            self._scan_end_monotonic = None

    def stop_scan(self):
        self._running = False

    def read_buffer_chunk(self, max_points: int) -> list[dict[str, Any]]:
        # Simulate blocking hardware I/O call.
        time.sleep(min(self.sample_interval_s, 0.2))

        if not self.is_running():
            return []

        chunk: list[dict[str, Any]] = []
        for _ in range(max_points):
            for sensor_id in self.sensor_ids:
                self._scan_index += 1
                chunk.append(
                    {
                        "scan_index": self._scan_index,
                        "sensor_id": sensor_id,
                        "temperature_c": self.setpoint + (self._scan_index % 10) * 0.1,
                    }
                )
            # Keep the example bounded per loop even when many sensors are configured.
            if len(chunk) >= max_points:
                break

        return chunk


class TempAsyncControlClient(TypedAsyncControlClient):
    """Typed client wrapper for TempControlServer commands."""

    service_type = TempControlServer.service_type

    async def start_scan(
        self,
        *,
        duration_s: float = 0.0,
        chunk_size: int = 16,
        poll_interval_s: float = 0.2,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        response = await self.send_device_command(
            {
                "command": "start-scan",
                "duration_s": duration_s,
                "chunk_size": chunk_size,
                "poll_interval_s": poll_interval_s,
            },
            timeout=timeout,
        )
        return self._success_message_as_dict(response, "start-scan")

    async def stop_scan(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command({"command": "stop-scan"}, timeout=timeout)
        return self._success_message_as_dict(response, "stop-scan")

    async def scan_status(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command({"command": "scan-status"}, timeout=timeout)
        return self._success_message_as_dict(response, "scan-status")

    async def set_sensors(self, sensor_ids: list[str], timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command(
            {"command": "set-sensors", "sensor_ids": sensor_ids},
            timeout=timeout,
        )
        return self._success_message_as_dict(response, "set-sensors")

    async def set_interval(self, interval_s: float, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command(
            {"command": "set-interval", "interval_s": interval_s},
            timeout=timeout,
        )
        return self._success_message_as_dict(response, "set-interval")

    async def set_setpoint(self, setpoint_c: float, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command(
            {"command": "set-setpoint", "setpoint_c": setpoint_c},
            timeout=timeout,
        )
        return self._success_message_as_dict(response, "set-setpoint")

    async def get_latest(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_device_command({"command": "get-latest"}, timeout=timeout)
        return self._success_message_as_dict(response, "get-latest")

    async def health(self, timeout: float | None = None) -> dict[str, Any] | None:
        response = await self.send_service_command("health", timeout=timeout)
        return self._success_message_as_dict(response, "health")


app = typer.Typer()


@app.command(cls=TyperAsyncCommand)
async def start_cs(
    service_name: str | None = typer.Option(
        None,
        "--service-name",
        help="Optional runtime service name override for this server instance.",
    ),
):
    """Start the async temperature control server."""

    with remote_logging():
        try:
            control_server = TempControlServer(service_name=service_name)
            await control_server.start()
        except KeyboardInterrupt:
            print("Shutdown requested...exiting")
        except SystemExit as exit_code:
            print(f"System Exit with code {exit_code}.")
            sys.exit(-1)
        except Exception:  # noqa
            import traceback

            traceback.print_exc(file=sys.stdout)


@app.command(cls=TyperAsyncCommand)
async def stop_cs():
    """Send terminate command to the async temperature control server."""
    console = Console()
    try:
        async with TempAsyncControlClient() as client:
            logger.info("Sending stop_server() to async temp control server.")
            if await client.stop_server() is None:
                console.print("Stop command failed or timed out.", style="red")
    except Exception as exc:
        console.print(f"Error occurred while sending stop command: {exc}", style="red")


@app.command(cls=TyperAsyncCommand)
async def status():
    """Get status of the async temperature control server."""
    console = Console()
    try:
        async with TempAsyncControlClient() as client:
            info = await client.info()
            health = await client.health()
            scan = await client.scan_status()
            console.print({"info": info, "health": health, "scan": scan})
    except Exception as exc:
        console.print(f"Error occurred while fetching status: {exc}", style="red")


@app.command(cls=TyperAsyncCommand)
async def get_latest():
    """Get the latest temperature readings from the async temperature control server."""
    console = Console()
    try:
        async with TempAsyncControlClient() as client:
            latest = await client.get_latest()
            console.print({"latest": latest})
    except Exception as exc:
        console.print(f"Error occurred while fetching latest readings: {exc}", style="red")


@app.command(cls=TyperAsyncCommand)
async def set_setpoint(setpoint_c: float):
    """Set the temperature setpoint for the async temperature control server."""
    console = Console()
    try:
        async with TempAsyncControlClient() as client:
            response = await client.set_setpoint(setpoint_c=setpoint_c)
            console.print(response)
    except Exception as exc:
        console.print(f"Error occurred while setting setpoint: {exc}", style="red")


@app.command(cls=TyperAsyncCommand)
async def start_scan(
    duration_s: float = 0.0,
    chunk_size: int = 16,
    poll_interval_s: float = 0.2,
):
    """Start buffered DAQ scan with optional duration and chunking options."""
    console = Console()
    try:
        async with TempAsyncControlClient() as client:
            response = await client.start_scan(
                duration_s=duration_s,
                chunk_size=chunk_size,
                poll_interval_s=poll_interval_s,
            )
            console.print(response)
    except Exception as exc:
        console.print(f"Error occurred while starting scan: {exc}", style="red")


@app.command(cls=TyperAsyncCommand)
async def stop_scan():
    """Stop buffered DAQ scan."""
    console = Console()
    try:
        async with TempAsyncControlClient() as client:
            response = await client.stop_scan()
            console.print(response)
    except Exception as exc:
        console.print(f"Error occurred while stopping scan: {exc}", style="red")


if __name__ == "__main__":
    app()
