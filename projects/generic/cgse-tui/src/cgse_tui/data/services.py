"""The services the TUI knows about before they register: the service registry and the core services."""

from __future__ import annotations

from egse.logger import SERVICE_TYPE as LOGGER_SERVICE_TYPE
from egse.metricshub import SERVICE_TYPE as METRICS_HUB_SERVICE_TYPE
from egse.notifyhub import SERVICE_TYPE as NOTIFY_HUB_SERVICE_TYPE
from egse.plugin import entry_points

REGISTRY_SERVICE_TYPE = "SERVICE_REGISTRY"
"""The registry doesn't register itself, the TUI uses this service type for its row."""

CUSTOM_KINDS = ("registry", "notifyhub", "metricshub", "command")
"""The `server_kind` of the services that are not control servers. They have no monitoring port, they are asked for
their status on every poll. `command` servers (e.g. the logger) answer the pickled string command "status"."""

CUSTOM_SERVICE_TYPES = {
    REGISTRY_SERVICE_TYPE: "registry",
    NOTIFY_HUB_SERVICE_TYPE: "notifyhub",
    METRICS_HUB_SERVICE_TYPE: "metricshub",
    LOGGER_SERVICE_TYPE: "command",
}
"""The kind of the core services that are not control servers, for registrations without `server_kind`."""


def custom_kind(service) -> str | None:
    """Returns the kind of a service that is not a control server, None for a control server.

    The `server_kind` of the registration decides; for registrations without it (older versions) the service type.
    """
    if service.server_kind in CUSTOM_KINDS:
        return service.server_kind
    return CUSTOM_SERVICE_TYPES.get(service.service_type)


def core_services() -> dict[str, str]:
    """Returns the core services as a mapping of service type to name, including the service registry.

    The core services are registered in the entry point group `cgse.process_management.core_services` as
    `name = service type`, e.g. `"Storage Manager" = "SM_CS"`.
    """
    services = {REGISTRY_SERVICE_TYPE: "Service Registry"}
    for ep in entry_points("cgse.process_management.core_services"):
        services[ep.value] = ep.name
    return services
