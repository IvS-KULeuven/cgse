__all__ = [
    "DEFAULT_COLLECTOR_PORT",
    "DEFAULT_REQUESTS_PORT",
    "STATS_INTERVAL",
    "is_metrics_hub_active",
    "async_is_metrics_hub_active",
]

from egse.settings import Settings

settings = Settings.load("Metrics Hub")

PROCESS_NAME = settings.get("PROCESS_NAME", "mh_cs")
SERVICE_ID = settings.get("SERVICE_ID", "mh_cs_1")
SERVICE_TYPE = settings.get("SERVICE_TYPE", "MH_CS")

DEFAULT_COLLECTOR_PORT = settings.get("COLLECTOR_PORT", 0)
DEFAULT_REQUESTS_PORT = settings.get("REQUESTS_PORT", 0)

STATS_INTERVAL = settings.get("STATS_INTERVAL", 30)
"""How often the metrics hub logs batch statistics [seconds]. Defaults to 30s."""


async def async_is_metrics_hub_active(timeout: float = 0.5) -> bool:
    """Check if the metrics hub is running.

    Sends a health request to the hub and waits for the reply. Returns True
    when the hub responds with a healthy status within the given timeout.
    """
    from egse.metricshub.client import AsyncMetricsHubClient  # prevent circular import

    with AsyncMetricsHubClient(request_timeout=timeout) as client:
        return await client.health_check()


def is_metrics_hub_active(timeout: float = 0.5) -> bool:
    """Synchronous wrapper around :func:`async_is_metrics_hub_active`."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("Use async_is_metrics_hub_active() from an async context.")
        return loop.run_until_complete(async_is_metrics_hub_active(timeout))
    except Exception:
        return False
