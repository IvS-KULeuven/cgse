from enum import Enum

from egse.log import logging
from egse.settings import Settings

logger = logging.getLogger("egse.registry")


settings = Settings.load("Service Registry")

# The ports that are assigned to REQ-REP and PUB-SUB protocols of the registry services. These can be overridden in
# the local settings file with a fallback value specified below. Do not assign zero ('0') to these ports, as this
# will cause the registry server to bind to a random free port, which will break the communication between the
# registry server and its clients. Clients will then not be able to contact the registry server for service discovery.

DEFAULT_RS_REQ_PORT = settings.get("REQUESTER_PORT", 4242)  # Handle requests
DEFAULT_RS_PUB_PORT = settings.get("PUBLISHER_PORT", 4243)  # Publish events
DEFAULT_RS_HB_PORT = settings.get("HEARTBEAT_PORT", 4244)  # Heartbeats

DEFAULT_RS_DB_PATH = "service_registry.db"


class MessageType(Enum):
    """Message types using the envelope frame in the ROUTER-DEALER protocol."""

    REQUEST_WITH_REPLY = b"REQ"  # Client expects a reply
    REQUEST_NO_REPLY = b"REQ_NO_REPLY"  # No reply expected by the client
    RESPONSE = b"RESPONSE"  # Response to a request
    NOTIFICATION = b"NOTIF"  # Server-initiated notification
    HEARTBEAT = b"HB"  # Heartbeat/health check


def is_service_registry_active(timeout: float = 0.5):
    """Check if the service registry is running and active.

    This function will send a 'health_check' request to the service registry and
    waits for the answer.

    If no reply was received after the given timeout [default=0.5s] the request
    will time out and return False.
    """

    from egse.registry.client import RegistryClient  # prevent circular import

    with RegistryClient(timeout=timeout) as client:
        if not client.health_check():
            return False
        else:
            return True


async def async_is_service_registry_active(timeout: float = 0.5) -> bool:
    """Asynchronously check if the service registry is running and active.

    This function sends a `health` request to the service registry and awaits
    the answer.

    If no reply is received within the given timeout (default: 0.5s), the
    request times out and False is returned.
    """

    from egse.registry.client import AsyncRegistryClient  # prevent circular import

    with AsyncRegistryClient(timeout=timeout) as client:
        if not await client.health_check():
            return False
        else:
            return True
