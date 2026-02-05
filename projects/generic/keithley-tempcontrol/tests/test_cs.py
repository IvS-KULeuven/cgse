from egse.log import logger
from egse.scpi import create_channel_list
from egse.tempcontrol.keithley.daq6510 import DEFAULT_BUFFER_1, DAQ6510Proxy
from egse.tempcontrol.keithley.daq6510_cs import is_daq6510_cs_active


def test_active():
    assert is_daq6510_cs_active() in (False, True)
    assert is_daq6510_cs_active(timeout=1.0) in (False, True)
    logger.info("DAQ6510 Control Server active: " + str(is_daq6510_cs_active()))


def test_proxy():
    with DAQ6510Proxy() as proxy:
        info = proxy.info()

        assert isinstance(info, str)

        idn = proxy.get_idn()
        assert isinstance(idn, str)

        assert info == idn

    logger.info("DAQ6510 Proxy test passed.")


def test_time():
    with DAQ6510Proxy() as proxy:
        dev_time_str = proxy.get_time()
        logger.info(f"Device time string: {dev_time_str}")
        logger.info("DAQ6510 Proxy time test passed.")


def test_measurement():
    """
    Test performing measurements with the DAQ6510 Proxy.
    1. Connect to the device using the proxy.
    2. Reset the device to ensure a clean state.
    3. Retrieve and log device information.
    4. Get and log buffer capacity and count.
    5. Configure sensors for temperature measurements on specified channels.
       - Channel 101: FRTD with PT100 in Celsius.
       - Channel 102: RTD with PT100 in Celsius.
    6. Setup measurements for the configured channels.
    7. Perform measurements and log the results.
    8. Finally, disconnect from the device.
    """
    count = 5
    interval = 1

    with DAQ6510Proxy() as daq:
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

        meas_response = daq.perform_measurement(channel_list=channels, count=count, interval=interval)

        assert len(meas_response) == 2 * count, f"Expected {2 * count} measurements, got {len(meas_response)}"

        logger.info(f"Measurement response: {meas_response}")

        buffer_count = daq.get_buffer_count()
        logger.info(f"buffer {DEFAULT_BUFFER_1} holds {buffer_count} readings")


if __name__ == "__main__":
    test_active()
    test_proxy()
    test_time()
    test_measurement()
