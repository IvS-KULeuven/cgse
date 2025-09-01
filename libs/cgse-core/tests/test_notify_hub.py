import asyncio
import contextlib
import sys
import threading
import time

import pytest

from egse.log import logger
from egse.notifyhub import async_is_notify_hub_active
from egse.notifyhub import is_notify_hub_active
from egse.notifyhub.event import NotificationEvent
from egse.notifyhub.server import AsyncNotificationHub
from egse.notifyhub.services import AsyncEventPublisher
from egse.notifyhub.services import AsyncEventSubscriber
from egse.notifyhub.services import EventPublisher
from egse.notifyhub.services import EventSubscriber
from egse.process import SubProcess
from egse.registry import is_service_registry_active
from egse.system import Timer
from egse.system import type_name
from egse.system import waiting_for


pytestmark = pytest.mark.skipif(
    is_notify_hub_active(), reason="The notification hub shall NOT be running for this test."
)


@contextlib.asynccontextmanager
async def async_notify_hub():
    """Asynchronous context manager that starts a notification hub as an asyncio Task."""

    if await async_is_notify_hub_active():
        pytest.xfail("The notification hub shall not be running for this test.")

    server = AsyncNotificationHub()
    server_task = asyncio.create_task(server.start())

    with Timer(name="Notify Hub startup timer"):
        await asyncio.wait_for(async_is_notify_hub_active(), timeout=5.0)

    try:
        yield
    except Exception as exc:
        logger.error(f"Caught {type_name(exc)}: {exc}", exc_info=True)

    await server.stop()

    await asyncio.gather(server_task, return_exceptions=True)

    if not server_task.done():
        server_task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await server_task


@contextlib.contextmanager
def notify_hub():
    """Context manager that starts a notification hub as a sub-process."""

    if is_notify_hub_active():
        pytest.xfail("The notification hub shall not be running for this test.")

    proc = SubProcess("Notification Hub", [sys.executable, "-m", "egse.notifyhub.server"], ["start"])
    proc.execute()

    with Timer(name="Notify Hub startup timer"):
        waiting_for(is_notify_hub_active, timeout=5.0)

    yield proc

    proc.quit()

    with Timer(name="Notify Hub shutdown timer"):
        waiting_for(lambda: not is_notify_hub_active(), timeout=5.0)


def single_event_handler(event_data: dict):
    logger.info(f"{event_data=}")
    assert event_data["event_type"] == "single-event"
    assert event_data["source_service"] == "test_notify_hub"
    assert event_data["data"]["data"] == "Simple string for a single event"


@pytest.mark.skipif(not is_service_registry_active(), reason="This test needs the service registry running")
@pytest.mark.asyncio
async def test_server_running_async():
    # This test starts the notification hub and let it running for 30s
    # In these 30s it should:
    #
    # - register as a service to the service registry
    # - send at least three heartbeats to the registry server
    # - de-register from the service registry

    async with async_notify_hub():
        logger.warning("Please note this test takes 30s, check the log afterwards for expected server actions.")
        await asyncio.sleep(30.0)


def test_single_event():
    with notify_hub():
        publisher = EventPublisher()
        publisher.connect()

        event = NotificationEvent(
            event_type="single-event",
            source_service="test_notify_hub",
            data={"data": "Simple string for a single event"},
        )

        def poll_next_event():
            subscriber = EventSubscriber(["single-event"])
            subscriber.connect()
            subscriber.register_handler("single-event", single_event_handler)
            event_received = False
            while not event_received:
                if subscriber.poll():
                    subscriber.handle_event()
                    event_received = True
                    continue

                logger.info("no event received yet...")
                time.sleep(1.0)

            subscriber.disconnect()

        thread = threading.Thread(target=poll_next_event)
        thread.start()

        time.sleep(0.1)  # give the thread time to start

        logger.info(f"Publishing event {event.event_type}")
        publisher.publish(event)

        time.sleep(1.0)

        publisher.disconnect()


@pytest.mark.asyncio
async def test_single_event_async():
    async with async_notify_hub():
        publisher = AsyncEventPublisher()
        await publisher.connect()

        subscriber = AsyncEventSubscriber(["single-event"])
        await subscriber.connect()

        subscriber.register_handler("single-event", single_event_handler)

        event_listener = asyncio.create_task(subscriber.start_listening())

        await asyncio.sleep(0.1)

        event = NotificationEvent(
            event_type="single-event",
            source_service="test_notify_hub",
            data={"data": "Simple string for a single event"},
        )
        await publisher.publish(event)

        await asyncio.sleep(0.2)

        subscriber.disconnect()

        await event_listener

        publisher.disconnect()
