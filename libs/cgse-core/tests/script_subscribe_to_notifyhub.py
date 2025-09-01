from egse.log import logger
from egse.notifyhub.services import EventSubscriber

subscriber = EventSubscriber([""])
subscriber.connect()


def handle_simple_event(event_data: dict):
    logger.info(f"----> {event_data=}")


def handle_single_event(event_data: dict):
    logger.info(f"----> {event_data=}")


subscriber.register_handler("simple-event", handle_simple_event)
subscriber.register_handler("single-event", handle_single_event)

while True:
    try:
        if subscriber.poll():
            logger.info("Event spotted...")
            event_data = subscriber.handle_event(return_event_data=True)
            logger.info(f"{event_data=}")
    except KeyboardInterrupt:
        logger.info("Caught KeyboardInterrupt, terminating...")
        break

subscriber.disconnect()
