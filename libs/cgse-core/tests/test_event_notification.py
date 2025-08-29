"""
Testing the Notification Hub.

What is expected to happen:

  - 10 events of type 'simple-event' are published where the 'count' is incremented from [0-9] and the 'quit' is False
  - subscription to event type 'simple-event'
  - handle is registered for the even type 'simple-event'
  - when the 'count' reaches 5, listening should be interrupted and stopped
  - four more events are published with count = [6-9]
  - a last event is published with count = 9 and 'quit' = True

You can use the script 'script_subscribe_to_notifyhub.py' to follow the events.

"""

import threading
import time
import pytest
from egse.log import logger
from egse.notifyhub import is_notify_hub_active
from egse.notifyhub.event import NotificationEvent
from egse.notifyhub.services import EventPublisher
from egse.notifyhub.services import EventSubscriber


pytestmark = pytest.mark.skipif(
    not is_notify_hub_active(), reason="The notification hub shall be running for this test."
)


def test_simple_event():
    publisher = EventPublisher()
    publisher.connect()

    is_running = True

    def handle_simple_event(event_data: dict):
        # The asserts will not fail the test, but they will appear in the output
        # of the test as ERROR when they fail.
        nonlocal is_running
        assert event_data["data"]["message"] == "a unit test for event notification"
        if "quit" in event_data["data"]:
            logger.info(f"{event_data=}")
            if event_data["data"]["count"] >= 5:
                is_running = False

    def _start_listening():
        logger.info("Starting to listen...")
        subscriber = EventSubscriber(["simple-event"])
        subscriber.connect()
        subscriber.register_handler("simple-event", handle_simple_event)

        while is_running:
            if subscriber.poll():
                subscriber.handle_event()

        subscriber.disconnect()

    thread = threading.Thread(target=_start_listening)
    thread.start()

    for idx in range(10):
        publisher.publish(
            NotificationEvent(
                event_type="simple-event",
                source_service="test-simple-event",
                data={"message": "a unit test for event notification", "count": idx, "quit": False},
            )
        )
        time.sleep(0.01)

    publisher.publish(
        NotificationEvent(
            event_type="simple-event",
            source_service="test-simple-event",
            data={"message": "a unit test for event notification", "count": 10, "quit": True},
        )
    )

    time.sleep(0.1)

    publisher.disconnect()
