# The Notification Hub

## Overview

The Notification Hub serves as a centralized event distribution system for the core services and control servers. 
Instead of having services directly subscribe to each other, all services publish their events to the hub, which 
then redistributes them to interested subscribers via ZeroMQ PUB-SUB sockets.

## Benefits

- **Decoupling**: Services don't need to know about each other directly
- **Scalability**: Easy to add new subscribers without modifying existing services
- **Reliability**: Single point of event distribution with consistent delivery
- **Simplicity**: One subscription endpoint for all system events

# Socket Endpoints

The Notification Hub exposes three ZeroMQ sockets:

| Purpose            |    Pattern     |  Your Socket  | Endpoint                    |
|--------------------|:--------------:|:-------------:|-----------------------------|
| Event Publishing   |   PUSH-PULL    |     PUSH      | tcp://notification-hub:4245 |
| Event Subscription |    PUB-SUB     |      SUB      | tcp://notification-hub:4246 |
| Health Checks      | ROUTER-DEALER  |    DEALER     | tcp://notification-hub:4247 |

Note: port numbers can be changed in the local settings YAML file.

## Events

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

## Publishing Events

Any core service, control server, or script can publish events to the notification hub using the EventPublisher class. For convenience, EventPublisher supports usage as a context manager, making it easy to send single events.

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


## Subscribing to Events

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

## Health Checks

The Notification Hub provides a health check interface to monitor the status and availability of the hub. This allows services and scripts to verify connectivity and basic hub functionality.
To perform a health check, use the NotificationHubClient class. The client 
connects to the hub's ROUTER-DEALER socket and sends a health check request. 
If the hub is available, it responds True. In case of an error or when the 
hub is not available, False is returned.

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


## Monitoring

Every 30s, the hub provides basic connection and event statistics to the log.

TODO: this should also go on the PUB channel as a StatsEvent.
