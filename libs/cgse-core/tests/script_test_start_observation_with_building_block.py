import sys
import time

from egse.log import logging
from egse.observation import ObservationContext
from egse.observation import building_block
from egse.observation import end_observation
from egse.observation import execute
from egse.observation import start_observation

logger = logging.getLogger("egse.test.script.observation_with_building_block")


def execute_start_observation_and_building_block():
    obsid = start_observation("Test observation with building block")
    logger.info(f"Started observation with obsid={obsid}")

    time.sleep(1.0)
    result = example_building_block()
    logger.info(f"Result of building block: {result}")
    time.sleep(1.0)

    end_observation()
    logger.info("Ended observation")


def execute_building_block():
    result = execute(example_building_block)
    logger.info(f"Result of building block: {result}")


def check_observation_context():
    ObservationContext().start_observation({"description": "Check observation context"})
    assert ObservationContext().get_level() == 0, "Observation level should be 0 at the start of the observation"
    ObservationContext().end_observation()


@building_block
def example_building_block() -> int:
    logger.info("Executing example building block")
    time.sleep(2.0)
    logger.info("Finishing example building block")
    return 42


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    execute_start_observation_and_building_block()
    execute_building_block()
    check_observation_context()
