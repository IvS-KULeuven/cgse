"""Collects the status of all services: the data behind the overview and detail screens.

The collector polls the service registry for the registered services. For each control server it subscribes to the
monitoring port, which tells whether the server is alive and gives the live process information, and it requests
the status report, with the device connection, when the server appears, every `REPORT_INTERVAL` seconds, and when the
user refreshes. The custom servers (registry,
notification hub, metrics hub, logger) have no monitoring port and are asked for their status on every poll.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

from cgse_tui.data import monitor
from cgse_tui.data import report
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.data.services import CORE_CGSE_OBJECTS
from cgse_tui.data.services import REGISTRY_SERVICE_TYPE
from cgse_tui.data.services import core_services
from cgse_tui.data.services import custom_kind
from cgse_tui.logs import quiet

logger = logging.getLogger("cgse_tui.collector")

MIN_STALE_AFTER = 5.0
"""Minimum number of seconds without information before a service is shown as stale."""

STALE_INTERVALS = 3
"""Number of missed monitoring messages or polls after which a service is shown as stale."""

REPORT_INTERVAL = 10.0
"""Seconds between two status reports of a control server. The device connection is only in the status report, the
monitoring messages have the process information."""

REGISTRY_GONE_AFTER = 30.0
"""Seconds without an answer from the registry after which it is shown as inactive and its registrations are dropped.

A registered service without fresh information is shown as stale: alive according to the registry, but not answering.
When the registry itself doesn't answer, the registrations can't be checked. After this time the services are no
longer considered registered: core services are shown as inactive, other services are removed from the overview.
"""


class Collector:
    """Keeps a `ServiceInfo` per service type, up to date with the registry, monitoring messages and requests.

    The external calls can be replaced, so the collector can be tested without running services.

    Args:
        registry: an object with the `health_check()` and `list_services()` coroutines of `AsyncRegistryClient`,
            used for every poll. When None, a new `AsyncRegistryClient` is used for every poll: the client doesn't
            match replies to requests, so after a timeout (e.g. while the registry is restarted) a reused client
            would read the replies to earlier requests.
        registry_endpoint: the request endpoint of the registry, the default from the settings when None.
        poll_interval: seconds between two polls of the registry and the custom servers.
        report_interval: seconds between two status reports of a control server.
        request_timeout: timeout in seconds for a single request.
        known_services: service type to name of the services that are shown also when not registered,
            by default the service registry and the core services.
        subscribe: coroutine function that follows a monitoring endpoint, see `monitor.subscribe()`.
        request_report: coroutine function that returns the status report of a control server.
        request_custom_status: coroutine function that returns the status of a custom server.
        clock: returns the current time in seconds.
    """

    def __init__(
        self,
        *,
        registry: Any = None,
        registry_endpoint: str | None = None,
        poll_interval: float = 2.0,
        report_interval: float = REPORT_INTERVAL,
        request_timeout: float = 2.0,
        known_services: dict[str, str] | None = None,
        subscribe: Callable[..., Awaitable[None]] = monitor.subscribe,
        request_report: Callable[..., Awaitable[dict | None]] = report.request_status_report,
        request_custom_status: Callable[..., Awaitable[dict | None]] = report.request_custom_status,
        clock: Callable[[], float] = time.time,
    ):
        self.registry = registry
        self.registry_endpoint = registry_endpoint
        self.poll_interval = poll_interval
        self.report_interval = report_interval
        self.request_timeout = request_timeout
        self.known_services = core_services() if known_services is None else known_services
        self._subscribe = subscribe
        self._request_report = request_report
        self._request_custom_status = request_custom_status
        self._clock = clock

        self.services: dict[str, ServiceInfo] = {
            service_type: ServiceInfo(
                name=name,
                service_type=service_type,
                state=ServiceState.INACTIVE,
                cgse_object=CORE_CGSE_OBJECTS.get(service_type),
            )
            for service_type, name in self.known_services.items()
        }
        if REGISTRY_SERVICE_TYPE in self.services:
            self.services[REGISTRY_SERVICE_TYPE].stale_after = self._custom_stale_after()
        if REGISTRY_SERVICE_TYPE in self.services:
            self.services[REGISTRY_SERVICE_TYPE].host = "localhost"  # the default registry endpoint
        if registry_endpoint and REGISTRY_SERVICE_TYPE in self.services:
            # The status request of the registry row goes to the same registry, e.g. "tcp://localhost:6100".
            host, _, port = registry_endpoint.rpartition("://")[2].rpartition(":")
            self.services[REGISTRY_SERVICE_TYPE].host = host
            self.services[REGISTRY_SERVICE_TYPE].port = int(port)
        self._monitors: dict[str, asyncio.Task] = {}
        self._requests: dict[str, asyncio.Task] = {}
        self._report_requested_at: dict[str, float] = {}
        self._last_states: dict[str, ServiceState] = {}
        self._registry_answered_at: float | None = None
        self.registry_answering = False
        """True when the registry answered the health check of the last poll."""

    def _custom_stale_after(self) -> float:
        """Stale time of the servers that are polled: three polls plus one request timeout.

        One lost request doesn't make the server stale. Requests do get lost: the registry and the hubs wait for a
        request with `asyncio.wait_for(socket.recv_multipart(), timeout)`, which can lose a request that arrives just
        when the wait is cancelled, see the defect list in `docs/dev_guide/tui_status_inventory.md`.
        """
        return max(MIN_STALE_AFTER, STALE_INTERVALS * self.poll_interval + self.request_timeout)

    # ----- results ----------------------------------------------------------------------------------------------------

    def snapshot(self) -> list[ServiceInfo]:
        """Returns all services sorted by name, with their state brought up to date.

        A change of state is logged, e.g. "Notification Hub: ok → stale". The messages of the client libraries
        during the requests of the collector are not shown, see `cgse_tui.logs.quiet()`.
        """
        now = self._clock()
        for service_type, service in self.services.items():
            service.state = self._state(service, now)
            previous = self._last_states.get(service_type)
            if previous is not None and previous is not service.state:
                level = logging.INFO if service.state is ServiceState.OK else logging.WARNING
                logger.log(level, f"{service.name}: {previous.value} → {service.state.value}")
            self._last_states[service_type] = service.state
        for service_type in self._last_states.keys() - self.services.keys():
            del self._last_states[service_type]
        return sorted(self.services.values(), key=lambda service: service.name.lower())

    def _state(self, service: ServiceInfo, now: float) -> ServiceState:
        if not service.registered and service.service_type != REGISTRY_SERVICE_TYPE:
            return ServiceState.INACTIVE
        if service.service_type == REGISTRY_SERVICE_TYPE:
            if service.last_update is None or now - service.last_update > REGISTRY_GONE_AFTER:
                return ServiceState.INACTIVE
        if service.last_update is None:
            if service.registered_at is not None and now - service.registered_at > service.stale_after:
                return ServiceState.STALE  # registered, but no answer and no monitoring message
            return ServiceState.UNKNOWN
        if now - service.last_update > service.stale_after:
            return ServiceState.STALE
        return ServiceState.OK

    # ----- running ----------------------------------------------------------------------------------------------------

    async def run(self) -> None:
        """Polls until cancelled."""
        try:
            while True:
                await self.poll()
                await asyncio.sleep(self.poll_interval)
        finally:
            await self.stop()

    async def stop(self) -> None:
        tasks = [*self._monitors.values(), *self._requests.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._monitors.clear()
        self._requests.clear()

    async def poll(self, reports: bool = False) -> None:
        """Updates the services from the registry, and asks the custom servers for their status.

        The control servers are asked for their status report every `report_interval` seconds, or now when `reports`
        is True (a refresh by the user).
        """
        with quiet():
            if self.registry is not None:
                await self._poll_registry(self.registry, reports)
            else:
                from egse.registry.client import AsyncRegistryClient

                async with AsyncRegistryClient(
                    registry_req_endpoint=self.registry_endpoint, timeout=self.request_timeout
                ) as registry:
                    await self._poll_registry(registry, reports)

    async def _poll_registry(self, registry: Any, reports: bool = False) -> None:
        self.registry_answering = await registry.health_check()
        if self.registry_answering:
            self._registry_answered_at = self._clock()
            self._update_registrations(await registry.list_services())
            self._start_request(REGISTRY_SERVICE_TYPE)
        elif self._registry_answered_at is not None and (
            self._clock() - self._registry_answered_at > REGISTRY_GONE_AFTER
        ):
            if any(service.registered for service in self.services.values()):
                logger.warning(
                    f"The service registry didn't answer for {REGISTRY_GONE_AFTER:.0f} s, "
                    "the services are no longer considered registered."
                )
                self._update_registrations([])
        now = self._clock()
        for service_type, service in self.services.items():
            if not service.registered:
                continue
            requested_at = self._report_requested_at.get(service_type, now)
            if custom_kind(service) or reports or now - requested_at >= self.report_interval:
                self._start_request(service_type)

    def is_running(self, service_type: str) -> bool:
        """True when the service is registered, for the registry: when it answered the last health check."""
        if service_type == REGISTRY_SERVICE_TYPE:
            return self.registry_answering
        service = self.services.get(service_type)
        return service is not None and service.registered

    async def wait_until(self, service_type: str, running: bool, timeout: float, interval: float = 1.0) -> bool:
        """Polls until the service is (not) running, see `is_running()`. Returns False after the timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            await self.poll()
            if self.is_running(service_type) is running:
                return True
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(interval)

    async def refresh_report(self, service_type: str) -> ServiceInfo | None:
        """Requests the status of the given service again and returns its updated information."""
        service = self.services.get(service_type)
        if service is None:
            return None
        task = self._start_request(service_type)
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        return service

    # ----- registrations ----------------------------------------------------------------------------------------------

    def _update_registrations(self, records: list[dict[str, Any]]) -> None:
        registered = set()

        for record in records:
            metadata = record.get("metadata") or {}
            service_type = metadata.get("type") or record.get("name")
            registered.add(service_type)

            service = self.services.get(service_type)
            if service is None:
                service = self.services[service_type] = ServiceInfo(name=record.get("name"), service_type=service_type)
            was_registered = service.registered
            if was_registered and (service.host, service.monitoring_port) != (
                record.get("host"),
                metadata.get("monitoring_port"),
            ):
                # The server was restarted between two polls and registered with new ports.
                if task := self._monitors.pop(service_type, None):
                    task.cancel()
                service.server_kind = None  # a restarted server may run another version
                was_registered = False

            service.registered = True
            service.service_id = record.get("id")
            service.metadata = metadata
            service.last_heartbeat = record.get("last_heartbeat")
            service.ttl = record.get("ttl")
            service.health = record.get("health")
            service.host = record.get("host")
            service.port = record.get("port")
            service.service_port = metadata.get("service_port")
            service.monitoring_port = metadata.get("monitoring_port")
            service.start_time = metadata.get("start_time")
            service.cgse_object = metadata.get("cgse_object") or CORE_CGSE_OBJECTS.get(service_type)
            # Older control servers register without `device_id`, their status report has it
            service.device_id = metadata.get("device_id") or service.device_id
            # Keep the kind that answered a status report when the server registered without `server_kind`.
            service.server_kind = metadata.get("server_kind") or service.server_kind
            if custom_kind(service):
                service.stale_after = self._custom_stale_after()
                # No monitoring port: the process information comes from the last heartbeat in the registry
                self._update_process(service, record.get("status") or {})

            if not was_registered:
                service.registered_at = self._clock()
                self._start_monitor(service)
                self._start_request(service_type)

        for service_type, service in list(self.services.items()):
            if service.registered and service_type not in registered:
                self._deregistered(service)

    @staticmethod
    def _update_process(service: ServiceInfo, process: dict[str, Any]) -> None:
        """Fills the process information from a status with the keys of `egse.process.process_status()`."""
        if process:
            service.pid = process.get("pid")
            service.uptime_s = process.get("uptime_s")
            service.cpu_percent = process.get("cpu_percent")
            service.cpu_user_s = process.get("cpu_user_s")
            service.cpu_system_s = process.get("cpu_system_s")
            service.rss = process.get("rss")
            service.uss = process.get("uss", service.uss)  # only in the status report

    def _deregistered(self, service: ServiceInfo) -> None:
        if service.service_type not in self.known_services:
            logger.info(f"{service.name} ({service.service_type}) is no longer registered.")
        if task := self._monitors.pop(service.service_type, None):
            task.cancel()
        self._report_requested_at.pop(service.service_type, None)
        if service.service_type in self.known_services:
            name = self.known_services[service.service_type]
            self.services[service.service_type] = ServiceInfo(
                name=name, service_type=service.service_type, cgse_object=CORE_CGSE_OBJECTS.get(service.service_type)
            )
        else:
            del self.services[service.service_type]

    # ----- monitoring -------------------------------------------------------------------------------------------------

    def _start_monitor(self, service: ServiceInfo) -> None:
        if not (service.host and service.monitoring_port) or service.service_type in self._monitors:
            return
        endpoint = f"tcp://{service.host}:{service.monitoring_port}"
        task = asyncio.create_task(self._monitor(service.service_type, endpoint), name=f"monitor-{endpoint}")
        self._monitors[service.service_type] = task

    async def _monitor(self, service_type: str, endpoint: str) -> None:
        try:
            await self._subscribe(endpoint, lambda status: self._on_monitoring(service_type, status))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Monitoring of {service_type} at {endpoint} stopped: {type(exc).__name__}: {exc}")

    def _on_monitoring(self, service_type: str, status: dict[str, Any]) -> None:
        service = self.services.get(service_type)
        if service is None:
            return
        fields = monitor.process_fields(status)
        service.pid = fields["pid"]
        service.uptime_s = fields["uptime_s"]
        service.cpu_percent = fields["cpu_percent"]
        service.cpu_user_s = fields["cpu_user_s"]
        service.cpu_system_s = fields["cpu_system_s"]
        service.rss = fields["rss"]
        service.uss = fields["uss"]
        if fields["interval_s"]:
            service.stale_after = max(MIN_STALE_AFTER, STALE_INTERVALS * fields["interval_s"])
        service.last_update = self._clock()

    # ----- requests ---------------------------------------------------------------------------------------------------

    def _start_request(self, service_type: str) -> asyncio.Task | None:
        if task := self._requests.get(service_type):
            return task  # still running
        service = self.services.get(service_type)
        if service is None:
            return None
        self._report_requested_at[service_type] = self._clock()
        task = asyncio.create_task(self._request(service), name=f"request-{service_type}")
        self._requests[service_type] = task
        task.add_done_callback(lambda _: self._requests.pop(service_type, None))
        return task

    async def _request(self, service: ServiceInfo) -> None:
        with quiet():
            await self._request_status(service)

    async def _request_status(self, service: ServiceInfo) -> None:
        if custom_kind(service):
            status = await self._request_custom_status(service, self.request_timeout)
            if status is not None:
                service.has_device = False  # the registry, hubs and command servers never control a device
                service.report = status
                service.last_update = self._clock()
                if custom_kind(service) == "registry":
                    # The registry doesn't register itself, its `info` reply has its own process information
                    self._update_process(service, status.get("process") or {})
                    service.start_time = status.get("start_time")
                    service.cgse_object = status.get("cgse_object") or service.cgse_object
            return

        status = await self._request_report(service, self.request_timeout)
        if status is None:
            return
        service.report = status

        if service.pid is None:
            self._update_process(service, status.get("process") or {})
        control_server = status.get("control_server")
        if isinstance(control_server, dict) and control_server.get("device_id"):
            service.device_id = control_server["device_id"]
        device = status.get("device")
        if isinstance(device, dict):
            service.has_device = True
            service.connected = device.get("connected")
            service.sim_mode = device.get("sim_mode")
        elif "device" in status:
            service.has_device = False  # the report says: no device
        if service.last_update is None:
            service.last_update = self._clock()
