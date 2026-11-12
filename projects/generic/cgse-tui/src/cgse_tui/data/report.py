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


def _command_status(hostname: str, port: int, timeout: float) -> Any:
    """Sends the pickled string command "status" to a command server (e.g. the logger) and returns its answer."""
    return _command_request(hostname, port, "status", timeout)


def _command_request(hostname: str, port: int, command: str, timeout: float) -> Any:
    """Sends a pickled string command to a command server (e.g. the logger) and returns its answer, None when it
    didn't answer in time."""
    import pickle

    import zmq

    socket = zmq.Context.instance().socket(zmq.REQ)
    socket.setsockopt(zmq.LINGER, 0)
    try:
        socket.connect(f"tcp://{hostname}:{port}")
        socket.send(pickle.dumps(command))
        if not socket.poll(int(timeout * 1000)):
            return None
        return pickle.loads(socket.recv())
    finally:
        socket.close(linger=0)


async def request_custom_status(service: ServiceInfo, timeout: float = 2.0) -> dict[str, Any] | None:
    """Returns the status of the registry, a hub or a command server (e.g. the logger), None when it didn't answer."""
    from cgse_tui.data.services import custom_kind

    kind = custom_kind(service)
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
        elif kind == "command" and service.host and service.port:
            status = await asyncio.wait_for(
                asyncio.to_thread(_command_status, service.host, service.port, timeout), timeout=5 * timeout
            )
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


async def request_log_tail(
    service: ServiceInfo, after: int, maximum: int, timeout: float = 2.0
) -> dict[str, Any] | None:
    """Returns the log records the logger received after sequence number `after`, at most `maximum`, the most recent.

    The answer has `last_seq` and `records`; None when the logger didn't answer, and an answer without `records` when
    the logger is an older version without the `tail` command.
    """
    if not (service.host and service.port):
        return None
    try:
        answer = await asyncio.wait_for(
            asyncio.to_thread(_command_request, service.host, service.port, f"tail {after} {maximum}", timeout),
            timeout=5 * timeout,
        )
    except Exception as exc:
        logger.warning(f"No log records from {service.service_type}: {type(exc).__name__}: {exc}")
        return None
    return answer if isinstance(answer, dict) else None


async def request_log_history(
    service: ServiceInfo, since: float, until: float, maximum: int, cursor: str | None = None, timeout: float = 10.0
) -> dict[str, Any] | None:
    """Returns the log records the logger reads from its log files, created between the timestamps `since` and
    `until`, at most `maximum`; the answer of the previous request has the `cursor` to continue with.

    The answer has `status`, and `records` and `cursor` (None when the window is complete) or `error`; None when the
    logger didn't answer, and an answer without `status` ACK when the logger is an older version without the
    `history` command. See `egse.logger.history`.
    """
    if not (service.host and service.port):
        return None
    command = f"history {since} {until} {maximum}" + (f" {cursor}" if cursor else "")
    try:
        answer = await asyncio.wait_for(
            asyncio.to_thread(_command_request, service.host, service.port, command, timeout),
            timeout=2 * timeout,
        )
    except Exception as exc:
        logger.warning(f"No log history from {service.service_type}: {type(exc).__name__}: {exc}")
        return None
    return answer if isinstance(answer, dict) else None


async def request_log_files(service: ServiceInfo, timeout: float = 2.0) -> dict[str, Any] | None:
    """Returns the files of the log folder of a log-files service: `status`, and `folder` and `files` (`name`, `size`,
    `mtime`, the most recently changed first) or `error`; None when the service didn't answer. See `egse.logfiles`."""
    return await _log_files_request(service, "files", timeout)


async def request_log_file_page(
    service: ServiceInfo,
    name: str,
    offset: int | None = None,
    before: int | None = None,
    maximum: int | None = None,
    timeout: float = 5.0,
) -> dict[str, Any] | None:
    """Returns a page of a file of the log folder of a log-files service: from `offset`, the page that ends at
    `before`, or the last page when both are None. The answer has `status`, and `text`, `offset`, `end`, `size` and
    `truncated`, or `error`; None when the service didn't answer. See `egse.logfiles.reader.read_file()`."""
    import shlex

    size = "" if maximum is None else f" {maximum}"
    if before is not None:
        command = f"before {shlex.quote(name)} {before}{size}"
    else:
        command = f"read {shlex.quote(name)} {'-' if offset is None else offset}{size}"
    return await _log_files_request(service, command, timeout)


async def _log_files_request(service: ServiceInfo, command: str, timeout: float) -> dict[str, Any] | None:
    if not (service.host and service.port):
        return None
    try:
        answer = await asyncio.wait_for(
            asyncio.to_thread(_command_request, service.host, service.port, command, timeout),
            timeout=2 * timeout,
        )
    except Exception as exc:
        logger.warning(f"No answer from {service.service_type}: {type(exc).__name__}: {exc}")
        return None
    return answer if isinstance(answer, dict) else None
