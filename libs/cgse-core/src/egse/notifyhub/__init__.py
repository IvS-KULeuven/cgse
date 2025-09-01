__all__ = [
    "DEFAULT_COLLECTOR_PORT",
    "DEFAULT_PUBLISHER_PORT",
    "DEFAULT_REQUESTS_PORT",
    "STATS_INTERVAL",
    "is_notify_hub_active",
    "async_is_notify_hub_active",
]

from egse.settings import Settings

settings = Settings.load("Notify Hub")

# Default ports that are assigned to PUSH-PULL, PUB-SUB, ROUTER-DEALER protocols of the notification hub.
# The actual ports are defined in the Settings.yaml, use local settings to change them.
DEFAULT_COLLECTOR_PORT = settings.get("COLLECTOR_PORT", 0)
DEFAULT_PUBLISHER_PORT = settings.get("PUBLISHER_PORT", 0)
DEFAULT_REQUESTS_PORT = settings.get("REQUESTS_PORT", 0)

STATS_INTERVAL = settings.get("STATS_INTERVAL", 30)
"""How often the notification hub sends statistics about active connections and processed events. Default to 30s."""


async def async_is_notify_hub_active(timeout: float = 0.5) -> bool:
    """Check if the notification hub is running and active.

    This function will send a 'health_check' request to the notification hub and
    waits for the answer. If the hub replies with `healthy` the function returns
    True, otherwise, False is returned.

    If no reply was received after the given timeout [default=0.5s] the request
    will time out and return False.

    Use this function in an asynchronous context.
    """

    from egse.notifyhub.client import AsyncNotificationHubClient  # prevent circular import

    with AsyncNotificationHubClient(request_timeout=timeout) as client:
        if not await client.health_check():
            return False
        else:
            return True


def is_notify_hub_active(timeout: float = 0.5):
    """Check if the notification hub is running and active.

    This function will send a 'health_check' request to the notification hub and
    waits for the answer. If the hub replies with `healthy` the function returns
    True, otherwise, False is returned.

    If no reply was received after the given timeout [default=0.5s] the request
    will time out and return False.
    """

    from egse.notifyhub.client import NotificationHubClient  # prevent circular import

    with NotificationHubClient(request_timeout=timeout) as client:
        if not client.health_check():
            return False
        else:
            return True
