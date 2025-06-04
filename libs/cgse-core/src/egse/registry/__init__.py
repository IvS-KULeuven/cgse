import logging

# Default ports that are assigned to REQ-REP and PUB-SUB protocols of the registry services
DEFAULT_RS_REQ_PORT = 4242  # Handle requests
DEFAULT_RS_PUB_PORT = 4243  # Publish events
DEFAULT_RS_HB_PORT = 4244  # Heartbeats

logger = logging.getLogger("egse.registry")
