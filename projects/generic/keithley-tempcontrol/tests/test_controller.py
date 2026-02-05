from egse.log import logger
from egse.scpi import create_channel_list
from egse.tempcontrol.keithley.daq6510 import DEFAULT_BUFFER_1, DAQ6510Controller


def test_daq6510_controller():
    """
    Test the Controller for the DAQ6510 device.
    1. Connect to the device.
    2. Reset the device.
    3. Retrieve and print device information.
    4. Get and print buffer capacity and count.
    5. Configure sensors for temperature measurements on specified channels.
       - Channel 101: FRTD with PT100 in Celsius.
       - Channel 102: RTD with PT100 in Celsius.
    6. Setup measurements for the configured channels.
    7. Perform measurements and print the results.
    8. Finally, disconnect from the device.
    """
    daq = DAQ6510Controller()

    try:
        daq.connect()
        daq.reset()

        info = daq.info()
        assert isinstance(info, str)
        logger.info(f"Device info: {info}")

        buffer_capacity = daq.get_buffer_capacity()
        logger.info(f"buffer {DEFAULT_BUFFER_1} can still hold {buffer_capacity} readings")

        buffer_count = daq.get_buffer_count()
        logger.info(f"buffer {DEFAULT_BUFFER_1} holds {buffer_count} readings")

        for sense, channels in [
            ({"TEMPERATURE": [("TRANSDUCER", "FRTD"), ("RTD:FOUR", "PT100"), ("UNIT", "CELSIUS")]}, "(@101)"),
            ({"TEMPERATURE": [("TRANSDUCER", "RTD"), ("RTD:TWO", "PT100"), ("UNIT", "CELSIUS")]}, "(@102)"),
        ]:
            daq.configure_sensors(channels, sense=sense)

        channels = create_channel_list((101, 102))
        logger.info(f"Channels: {channels}")

        daq.setup_measurements(channel_list=channels)

        meas_response = daq.perform_measurement(channel_list=channels, count=5, interval=1)

        logger.info(f"Measurement response: {meas_response}")

        buffer_count = daq.get_buffer_count()
        logger.info(f"buffer {DEFAULT_BUFFER_1} holds {buffer_count} readings")
    finally:
        daq.disconnect()


if __name__ == "__main__":
    test_daq6510_controller()
