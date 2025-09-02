"""
Notification Hub services for event-based messaging.

Provides asynchronous and synchronous publisher/subscriber classes for
sending and receiving events between core services via ZeroMQ.
"""

import asyncio
import json
import logging
from asyncio import CancelledError
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

import zmq
import zmq.asyncio

from . import DEFAULT_COLLECTOR_PORT
from . import DEFAULT_PUBLISHER_PORT
from .event import NotificationEvent

NOTIFY_HUB_COLLECTOR = f"tcp://localhost:{DEFAULT_COLLECTOR_PORT}"
NOTIFY_HUB_PUBLISHER = f"tcp://localhost:{DEFAULT_PUBLISHER_PORT}"


class AsyncEventPublisher:
    """Publishes events asynchronously to the notification hub.

    Args:
        hub_address (str): Endpoint of the notification hub. [default=NOTIFY_HUB_COLLECTOR]
    """

    def __init__(self, hub_address: str = NOTIFY_HUB_COLLECTOR):
        self.hub_address = hub_address
        self.context = zmq.asyncio.Context()
        self.publisher = None
        self._connected = False
        self.logger = logging.getLogger("egse.event-pub")

    async def connect(self):
        """Connect to the notification hub"""
        if not self._connected:
            self.publisher = self.context.socket(zmq.PUSH)
            self.publisher.connect(self.hub_address)
            await asyncio.sleep(0.1)  # Allow connection to establish
            self._connected = True
            self.logger.info(f"Connected to hub at {self.hub_address}")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    async def publish(self, event: NotificationEvent):
        """Publish an event"""

        await self.publisher.send(json.dumps(event.as_dict()).encode())
        self.logger.debug(f"Published: {event.event_type}")

    def disconnect(self):
        """Clean shutdown"""
        self._connected = False
        if self.publisher:
            # Keep the linger parameter, otherwise the event will not be sent when
            # you use a context manager to just send one event.
            self.publisher.close(linger=100)
        self.context.term()


class AsyncEventSubscriber:
    """Subscribes to events from the notification hub asynchronously.

    Args:
        subscriptions (List[str]): List of event types to subscribe to.
        hub_address (str): Endpoint of the notification hub. [default=NOTIFY_HUB_PUBLISHER]
    """

    def __init__(self, subscriptions: List[str], hub_address: str = NOTIFY_HUB_PUBLISHER):
        self.subscriptions = subscriptions
        self.hub_address = hub_address
        self.context = zmq.asyncio.Context()
        self.subscriber = None
        self.handlers: Dict[str, Callable] = {}
        self.running = False
        self.logger = logging.getLogger("egse.event-sub")

    async def connect(self):
        """Connect to the notification hub."""
        self.subscriber = self.context.socket(zmq.SUB)
        self.subscriber.connect(self.hub_address)

        # Subscribe to specific event types
        for event_type in self.subscriptions:
            self.subscriber.setsockopt(zmq.SUBSCRIBE, event_type.encode())
            self.logger.info(f"Subscribed to: {event_type}")

    def register_handler(self, event_type: str, handler: Callable):
        """Register a handler for an event type."""
        self.handlers[event_type] = handler

    async def start_listening(self):
        """Start listening for events"""

        self.running = True
        self.logger.info("Started listening for events")

        while self.running:
            try:
                if await self.subscriber.poll(timeout=1000):
                    topic, message_bytes = await self.subscriber.recv_multipart()

                    event_type = topic.decode()
                    event_data = json.loads(message_bytes.decode())

                    await self._handle_event(event_type, event_data)

                await asyncio.sleep(0.001)

            except Exception as exc:
                self.logger.error(f"Error receiving event: {exc}")
                await asyncio.sleep(1)
            except CancelledError:
                break

    async def _handle_event(self, event_type: str, event_data: Dict):
        """Handle received event"""
        handler = self.handlers.get(event_type)

        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_data)
                else:
                    await asyncio.get_event_loop().run_in_executor(None, handler, event_data)
            except Exception as exc:
                self.logger.error(f"Error handling {event_type}: {exc}")
        else:
            self.logger.warning(f"No handler registered for {event_type}")

    def disconnect(self):
        """Stop listening"""
        self.running = False
        if self.subscriber is not None:
            self.subscriber.close(linger=0)
        self.context.term()


class ServiceMessaging:
    """Convenience wrapper for publishing and subscribing to events.

    Args:
        service_name (str): Name of the service.
        subscriptions (List[str], optional): Event types to subscribe to.
    """

    def __init__(self, service_name: str, subscriptions: List[str] | None = None):
        self.service_name = service_name
        self.publisher = AsyncEventPublisher()
        self.subscriber = AsyncEventSubscriber(subscriptions or []) if subscriptions else None

    async def publish_event(self, event_type: str, data: Dict[Any, Any], correlation_id: Optional[str] = None):
        """Publish an event"""
        event = NotificationEvent(
            event_type=event_type,
            source_service=self.service_name,
            data=data,
            correlation_id=correlation_id,
        )
        await self.publisher.publish(event)

    def register_handler(self, event_type: str, handler: Callable):
        """Register event handler"""
        if self.subscriber:
            self.subscriber.register_handler(event_type, handler)

    async def start_listening(self):
        """Start listening for events"""
        if self.subscriber:
            await self.subscriber.start_listening()

    def disconnect(self):
        """Clean shutdown"""
        self.publisher.disconnect()
        if self.subscriber:
            self.subscriber.disconnect()


class EventPublisher:
    """Publishes events synchronously to the notification hub.

    Args:
        hub_address (str): Endpoint of the notification hub. [default=NOTIFY_HUB_COLLECTOR]
    """

    def __init__(self, hub_address: str = NOTIFY_HUB_COLLECTOR):
        self.hub_address = hub_address
        self.context = zmq.Context().instance()
        self.publisher = None
        self._connected = False
        self.logger = logging.getLogger("egse.event-pub")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        """Connect to the notification hub"""
        if not self._connected:
            self.publisher = self.context.socket(zmq.PUSH)
            self.publisher.connect(self.hub_address)
            # time.sleep(0.1)  # Allow connection to establish
            self._connected = True
            self.logger.info(f"Connected to hub at {self.hub_address}")

    def publish(self, event: NotificationEvent):
        """Publish an event"""
        self.publisher.send(json.dumps(event.as_dict()).encode())
        self.logger.debug(f"Published: {event.event_type} with correlation_id={event.correlation_id}")

    def disconnect(self):
        """Clean shutdown"""
        if self._connected:
            # Keep the linger parameter, otherwise the event will not be sent when
            # you use the context manager to just send one event.
            self.publisher.close(linger=100)
            self._connected = False


class EventSubscriber:
    """Subscribes to events from the notification hub. Use this class in a synchronous context.

    Args:
        subscriptions (List[str]): List of event types to subscribe to.
        hub_address (str): Endpoint of the notification hub. [default = NOTIFY_HUB_COLLECTOR]
    """

    def __init__(self, subscriptions: List[str], hub_address: str = NOTIFY_HUB_PUBLISHER):
        self.subscriptions = subscriptions
        self.hub_address = hub_address
        self.context = zmq.Context().instance()
        self.subscriber = None
        self.handlers: Dict[str, Callable] = {}
        self.logger = logging.getLogger("egse.event-sub")

    def connect(self):
        """Connect to the notification hub"""
        self.subscriber = self.context.socket(zmq.SUB)
        self.subscriber.connect(self.hub_address)

        # Subscribe to specific event types
        for event_type in self.subscriptions:
            self.subscriber.setsockopt(zmq.SUBSCRIBE, event_type.encode())
            self.logger.info(f"Subscribed to: {event_type or 'all'}")

    def register_handler(self, event_type: str, handler: Callable):
        """Register a handler for an event type"""
        self.handlers[event_type] = handler

    @property
    def socket(self):
        return self.subscriber

    def poll(self, timeout=1000):
        return self.subscriber.poll(timeout=timeout)

    def handle_event(self, return_event_data: bool = False) -> dict:
        topic, message_bytes = self.subscriber.recv_multipart()

        event_type = topic.decode()
        event_data = json.loads(message_bytes.decode())

        if return_event_data:
            return event_data
        else:
            self._handle_event(event_type, event_data)
            return {}

    def _handle_event(self, event_type: str, event_data: Dict):
        """Handle received event"""
        handler = self.handlers.get(event_type)

        if handler:
            try:
                handler(event_data)
            except Exception as exc:
                self.logger.error(f"Error handling {event_type} by {handler.__name__}: {exc}", exc_info=True)
        else:
            self.logger.warning(f"No handler registered for {event_type}")

    def disconnect(self):
        """Stop listening"""
        if self.subscriber:
            self.subscriber.close(linger=0)
