import logging
from enum import Enum

# Default ports that are assigned to REQ-REP and PUB-SUB protocols of the registry services
DEFAULT_RS_REQ_PORT = 4242  # Handle requests
DEFAULT_RS_PUB_PORT = 4243  # Publish events
DEFAULT_RS_HB_PORT = 4244  # Heartbeats

DEFAULT_RS_DB_PATH = 'service_registry.db'


class MessageType(Enum):
    """Message types using the envelope frame in the ROUTER-DEALER protocol."""
    REQUEST_WITH_REPLY = b"REQ"     # Client expects a reply
    REQUEST_NO_REPLY = b"NO-REQ"    # No reply expected by the client
    RESPONSE = b"REP"               # Response to a request
    NOTIFICATION = b"NOTIF"         # Server-initiated notification
    HEARTBEAT = b"HB"               # Heartbeat/health check


logger = logging.getLogger("egse.registry")
