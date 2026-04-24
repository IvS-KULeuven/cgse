# The Notification Hub

## Overview

The Notification Hub is the centralized event bus for core services and control servers.
Services publish events to the hub, and subscribers consume these events through a
single PUB-SUB distribution channel.

Core responsibilities:

- decoupled event fan-out
- unified subscription endpoint
- basic health/control interface

## Socket Endpoints

The Notification Hub exposes three ZeroMQ sockets:

| Purpose            |    Pattern     | Your Socket | Endpoint             |
|--------------------|:--------------:|:-----------:|----------------------|
| Event Publishing   |   PUSH-PULL    |    PUSH     | tcp://localhost:6125 |
| Event Subscription |    PUB-SUB     |     SUB     | tcp://localhost:6126 |
| Health Checks      | ROUTER-DEALER  |   DEALER    | tcp://localhost:6127 |

!!! note
    These default port values are defined in `cgse_core/settings.yaml` and can be overridden in the local settings.
    Ports can be static or dynamically allocated by the OS when configured as `0`. Clients discover
    the active endpoints through the Registry, especially when ports are configured as `0`.

## Event Model

```python
from egse.notifyhub.event import NotificationEvent

event = NotificationEvent(
    event_type="new_setup",
    source_service="cm_cs",
    data={"setup_id": "0001234"},
)
```
A `NotificationEvent` also has a `timestamp` and a `correlation_id`
associated. These fields are automatically filled on creation of the event
and must not be provided. An event can be converted into a plain dictionary
with the `.as_dict()` method.

```
>>> print(event.as_dict())
{
  'event_type': 'new_setup',
  'source_service': 'cm_cs',
  'data': {'setup_id': '0001234'},
  'timestamp': 1756709627.25942,
  'correlation_id': '23b44f16-34f9-498a-85f7-5c57658ea363'
}
```

## Client Access

Any core service, control server, or script can publish events to the Notification Hub using `EventPublisher`.
For convenience, `EventPublisher` supports usage as a context manager, making it easy to send single events.

=== "Synchronous"

    ```python
    from egse.notifyhub.services import EventPublisher

    with EventPublisher() as publisher:
        publisher.publish(event)
    ```

=== "Asynchronous"

    ```python
    from egse.notifyhub.services import AsyncEventPublisher

    async with AsyncEventPublisher() as publisher:
        await publisher.publish(event)
    ```

### Subscribing To Events

Listen to events from the notification hub with the EventSubscriber class.
The usage for this class is quite different for synchronous and asynchronous
contexts.

=== "Synchronous"

    In a synchronous context, you will need to add code to poll the socket
    and handle the event inside your own event loop. The subscriber socket
    can be retrieved with the `subscriber.socket` property, you can then add
    the socket to a Poller object.

    ```python
    from egse.notifyhub.services import EventSubscriber

    def load_setup(event_data: dict):
        ...

    subscriber = EventSubscriber(["new_setup"])
    subscriber.register_handler("new_setup", load_setup)
    subscriber.connect()

    while True:

        ...

        if subscriber.poll():
            subscriber.handle_event()

    subscriber.disconnect()
    ```

=== "Asynchronous"

    ```python
    from egse.notifyhub.services import AsyncEventSubscriber

    async def load_setup(event_data: dict):
        ...

    subscriber = AsyncEventSubscriber(["new_setup"])
    subscriber.register_handler("new_setup", load_setup)
    await subscriber.connect()

    event_listener = asyncio.create_task(subscriber.start_listening())

    ...

    subscriber.disconnect()
    await event_listener  # add a wait_for with a timeout if needed
    ```

## Control Actions

The Notify Hub server exposes these control actions over the request socket:

- `health`: check if the hub is alive
- `info`: get ports and runtime statistics
- `terminate`: request a graceful shutdown

You can query this through the client API (`server_status`) or with CLI status.

## Status And Health

The Notification Hub provides a health check interface to monitor status and availability.
This allows services and scripts to verify connectivity and basic hub functionality.
To perform a health check, use the `NotificationHubClient` class. The client
connects to the hub's ROUTER-DEALER socket and sends a health check request.
If the hub is available, it responds `True`. In case of an error or when the
hub is not available, `False` is returned.

=== "Synchronous"

    ```python
    from egse.notifyhub.client import NotificationHubClient

    with NotificationHubClient() as client:
        if not client.health_check():
            ... # notification hub not available
    ```

=== "Asynchronous"

    ```python
    from egse.notifyhub.client import AsyncNotificationHubClient

    with AsyncNotificationHubClient() as client:
        if not await client.health_check():
            ... # notification hub not available
    ```

The health check has a default timeout of 5 seconds. If this is too long for
your needs, provide a `request_timeout` argument as a float in seconds to
the `NotificationHubClient` call.

## Running The Service

Use the server module CLI directly:

=== "Using `uv` (preferred)"

    ```bash
    uv run cgse nh start
    uv run cgse nh stop
    uv run cgse nh status
    ```

=== "Direct (for debugging)"

    ```bash
    python -m egse.notifyhub.server start
    python -m egse.notifyhub.server status
    python -m egse.notifyhub.server stop
    ```
## Configuration

Notification Hub settings are loaded from `Notify Hub` in `cgse_core/settings.yaml`.
Main keys include:

- `EVENT_PUB_PORT`
- `EVENT_SUB_PORT`
- `HEARTBEAT_PORT`
- `STATS_INTERVAL`

## Integration Notes

- Configuration Manager publishes setup-change events (for example `new_setup`).
- Storage Manager and other services can subscribe without direct coupling between services.



## Monitoring And Troubleshooting

Every `STATS_INTERVAL` seconds (default: 30s), the hub reports basic statistics to the log.

TODO: this should also go on the PUB channel as a StatsEvent.
