"""
This module defines Listeners between control servers and is part of a notification system where changes in
one control-server are notified to all listeners of that control-server.

Since we have communication between control servers, a listener registers to a control server with its name/id
and a Proxy class that will be used to send the notification. A listener can also contain an `event_id` to restrict
events to handle. (Shall events be filtered on the server (only notify events that match the `event_id` or shall they
be filtered on the client (only handle those events that match the `event_id`) ?)

Any control server will support notification and listeners are added through the service proxy of the control server.

A control server that wants to be notified by an event needs to implement the
[EventInterface](listener.md#egse.listener.EventInterface) in the Proxy and in the Controller.

"""

import logging
from enum import IntEnum
from typing import Any
from typing import Dict
from typing import List
from typing import Type

from egse.decorators import dynamic_interface
from egse.system import Timer

LOGGER = logging.getLogger(__name__)


class EVENT_ID(IntEnum):  # noqa
    """An identifier for the type of event."""

    ALL = 0
    """Match all events."""
    SETUP = 1
    """An event for a new or updated Setup."""


class Event:
    """An event that is generated by a control server."""

    def __init__(self, event_id: int, context: Any):
        self.id = event_id
        self.context = context

    def __repr__(self):
        return f"Event({EVENT_ID(self.id).name}, {self.context})"

    @property
    def type(self) -> str:
        try:
            return self.context["event_type"]
        except KeyError:
            return "unknown: event_type not provided"


class EventInterface:
    """
    A dynamic interface for handling events.

    This interface defines a single method, 'handle_event', which is intended
    to be implemented by classes that want to handle specific types of events.

    Use this interface as a mixin for classes (Proxy/Controller) that implement this `handle_event` method.

    """

    @dynamic_interface
    def handle_event(self, event: Event):
        """Handles the specified event.

        Args:
            event (Event): An instance of the Event class representing the event to be handled.
        """
        ...


class Listeners:
    """
    A class for managing and notifying registered listeners.

    This class provides methods to add, remove, and notify listeners of events.
    """

    def __init__(self):
        """Initializes an instance of the Listeners class."""
        self._listeners: Dict[str, dict] = {}

    def __len__(self):
        """Returns the number of registered listeners."""
        return len(self._listeners)

    def add_listener(self, listener: dict):
        """
        Adds a new listener to the registered listeners.

        The listener argument dictionary is expected to have at least the following key:values pairs:

        * 'name': the name or identifier of the listener
        * 'proxy': a Proxy object that will be used for notifying the service

        Args:
            listener (dict): A dictionary with properties of the listener,
                including 'name' and 'proxy'.

        Raises:
            ValueError: If the listener already exists.
        """
        try:
            listener_name = listener["name"]
        except KeyError as exc:
            raise ValueError(f"Expected 'name' key in listener argument {listener}.") from exc

        if listener_name in self._listeners:
            raise ValueError(f"Process {listener_name} is already registered as a listener.")

        # For now we make these listeners have a Proxy class that will be used for notification. Later on
        # we might have other mechanisms for notification.

        from egse.proxy import Proxy

        proxy = listener.get("proxy")
        if proxy is not None:
            if not isinstance(proxy, type) or not issubclass(proxy, Proxy):
                raise ValueError(f"Expected 'proxy' in listener argument {proxy=} to be a Proxy sub-class.")

        self._listeners[listener_name] = listener

    def remove_listener(self, listener: dict):
        """
        Removes a listener from the registered listeners.

        Args:
           listener (dict): A dictionary representing the listener to be
               removed. It should contain a 'name' key.

        Raises:
           ValueError: If the 'name' key is not present in the listener
               argument or if the specified listener is not registered.
        """

        try:
            listener_name = listener["name"]
        except KeyError as exc:
            raise ValueError(f"Expected 'name' key in listener argument {listener}.") from exc

        try:
            del self._listeners[listener_name]
        except KeyError as exc:
            raise ValueError(f"Process {listener_name} cannot be removed, not registered.") from exc

    def notify_listeners(self, event: Event):
        """
        Notifies all registered listeners of a specific event.

        Args:
            event (Event): An instance of the Event class representing the
                event to be broadcasted.

        Note:
            The 'handle_event' method is called on each listener's proxy
            object to process the event.
        """

        LOGGER.debug(f"Notifying listeners {self.get_listener_names()}")

        for name, listener in self._listeners.items():
            self.notify_listener(name, listener, event)

    def notify_listener(self, name: str, listener: dict, event: Event):
        """
        Notifies a registered listener fro the given event.
        """
        proxy: Type[EventInterface] = listener["proxy"]

        # The Proxy uses a REQ-REP protocol and waits for an answer. That's why we have a Timer
        # in the context so we are able to monitor how long it takes to notify a listener.
        # The Timer can be removed when we are confident all `handle_event` functions are properly
        # implemented.
        with Timer(f"Notify listener {name}", log_level=logging.DEBUG), proxy() as pobj:
            rc = pobj.handle_event(event)

        LOGGER.debug(f"Listener {name} returned {rc=}")

    def get_listener_names(self) -> List[str]:
        """Returns a list with the names of the registered listeners."""
        return list(self._listeners.keys())
