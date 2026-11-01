"""Requests the status of a service: the status report of a control server, or the status of a custom server."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.monitor import process_fields

logger = logging.getLogger("cgse_tui.report")


def _sync_status_report(hostname: str, port: int, timeout: float) -> dict[str, Any] | None:
    from egse.services import ServiceProxy

    with ServiceProxy(hostname=hostname, port=port, timeout=timeout) as proxy:
        report = proxy.get_status_report()
        if report is None:
            # A server that was started before the status report existed doesn't offer the command.
            process_status = proxy.get_process_status()
            report = {"process": process_fields(process_status), "process_status": process_status}
        return report


async def request_status_report(service: ServiceInfo, timeout: float = 2.0) -> dict[str, Any] | None:
    """Returns the status report of a sync or async control server, or None when it couldn't be retrieved.

    A control server that registered without `server_kind` (started with an older version) is asked with the sync
    client first, then with the async client. The kind that answers is remembered in `service.server_kind`.
    """
    if service.server_kind in ("sync", "async"):
        kinds = [service.server_kind]
    elif service.service_port:
        kinds = ["sync", "async"]
    else:
        return None

    for kind in kinds:
        report = await _request_status_report(kind, service, timeout)
        if report is not None:
            service.server_kind = kind
            return report
    return None


async def _request_status_report(kind: str, service: ServiceInfo, timeout: float) -> dict[str, Any] | None:
    try:
        if kind == "sync" and service.host and service.service_port:
            return await asyncio.wait_for(
                asyncio.to_thread(_sync_status_report, service.host, service.service_port, timeout),
                timeout=5 * timeout,
            )
        if kind == "async":
            from egse.async_control import AsyncControlClient

            async with AsyncControlClient(service_type=service.service_type, timeout=timeout) as client:
                return await client.get_status_report()
    except Exception as exc:
        logger.warning(f"No status report from {service.service_type} ({kind}): {type(exc).__name__}: {exc}")
    return None


async def request_custom_status(service: ServiceInfo, timeout: float = 2.0) -> dict[str, Any] | None:
    """Returns the status of the registry, notification hub, metrics hub or logger, None when it didn't answer."""
    from cgse_tui.data.services import CUSTOM_SERVICE_TYPES

    kind = CUSTOM_SERVICE_TYPES.get(service.service_type)
    try:
        if kind == "registry":
            from egse.registry.client import AsyncRegistryClient

            endpoint = f"tcp://{service.host}:{service.port}" if service.host and service.port else None
            async with AsyncRegistryClient(registry_req_endpoint=endpoint, timeout=timeout) as client:
                status = await client.server_status()
        elif kind == "notifyhub":
            from egse.notifyhub.client import AsyncNotificationHubClient

            with AsyncNotificationHubClient(
                req_endpoint=f"tcp://{service.host}:{service.port}", request_timeout=timeout
            ) as client:
                status = await client.server_status()
        elif kind == "metricshub":
            from egse.metricshub.client import AsyncMetricsHubClient

            with AsyncMetricsHubClient(
                req_endpoint=f"tcp://{service.host}:{service.port}", request_timeout=timeout
            ) as client:
                status = await client.server_status()
        elif kind == "logger":
            from egse.logger import send_request

            status = await asyncio.wait_for(asyncio.to_thread(send_request, "status"), timeout=5 * timeout)
        else:
            return None
    except Exception as exc:
        logger.warning(f"No status from {service.service_type}: {type(exc).__name__}: {exc}")
        return None

    if not isinstance(status, dict):
        return None
    if status.get("success") is False or "error" in status or status.get("status") == "NACK":
        return None
    return status
