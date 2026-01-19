import json
import logging
import time

from egse.tempcontrol.keithley.daq6510_mon import DAQMonitorClient
from egse.tempcontrol.keithley.daq6510_mon import DAQ_MON_CMD_PORT

logger = logging.getLogger("egse.daq6510-client")


def daq6510_mon():
    with DAQMonitorClient(server_address="localhost", port=DAQ_MON_CMD_PORT) as client:
        # Get current status
        status = client.get_status()
        logger.info(f"Service status: {json.dumps(status, indent=4)}")

        # Set polling interval to 1s
        response = client.set_interval(1.0)
        logger.info(f"Set interval response: {response}")

        # Start polling with custom settings
        response = client.start_polling(channels=["101", "102"], interval=1.0)
        logger.info(f"Start polling response: {response}")

        # Wait for a while
        logger.info("Sleeping for 5.0s...")
        time.sleep(5.0)

        # doing some measurements in between ...
        response = client.get_reading(["101"])
        logger.info(f"Reading: {response = }")
        response = client.get_reading(["102"])
        logger.info(f"Reading: {response = }")

        # Wait for another 5.0s
        logger.info("Sleeping for 5.0s...")
        time.sleep(5.0)

        # another measurement during polling...
        response = client.get_reading(["101", "102"])
        logger.info(f"Reading: {response = }")

        # and get the last reading from the polling loop
        response = client.get_last_reading()
        logger.info(f"Reading: {response = }")

        # Wait for another 1.0s
        logger.info("Sleeping for 1.0s...")
        time.sleep(1.0)

        # Change polling interval
        response = client.set_interval(3.0)
        logger.info(f"Set interval response: {response}")

        # Wait for a while
        logger.info("Sleeping for 10.0s...")
        time.sleep(10.0)

        # Stop polling
        response = client.stop_polling()
        logger.info(f"Stop polling response: {response}")


if __name__ == "__main__":
    daq6510_mon()
