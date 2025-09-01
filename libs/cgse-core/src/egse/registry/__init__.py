import logging
from enum import Enum

# Default ports that are assigned to REQ-REP and PUB-SUB protocols of the registry services
DEFAULT_RS_REQ_PORT = 4242  # Handle requests
DEFAULT_RS_PUB_PORT = 4243  # Publish events
DEFAULT_RS_HB_PORT = 4244  # Heartbeats

DEFAULT_RS_DB_PATH = "service_registry.db"


class MessageType(Enum):
    """Message types using the envelope frame in the ROUTER-DEALER protocol."""

    REQUEST_WITH_REPLY = b"REQ"  # Client expects a reply
    REQUEST_NO_REPLY = b"REQ_NO_REPLY"  # No reply expected by the client
    RESPONSE = b"RESPONSE"  # Response to a request
    NOTIFICATION = b"NOTIF"  # Server-initiated notification
    HEARTBEAT = b"HB"  # Heartbeat/health check


logger = logging.getLogger("egse.registry")


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
