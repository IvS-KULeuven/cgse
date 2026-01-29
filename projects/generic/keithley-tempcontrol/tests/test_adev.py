import asyncio
import json
import time

import pytest

from egse.device import DeviceConnectionError
from egse.device import DeviceTimeoutError
from egse.env import bool_env
from egse.log import logger
from egse.settings import Settings
from egse.tempcontrol.keithley.daq6510_adev import DAQ6510
from egse.tempcontrol.keithley.daq6510_mon import DAQMonitorClient

settings = Settings.load("Keithley DAQ6510")

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")

SCPI_PORT = settings.get("PORT", 5025)
HOSTNAME = settings.get("HOSTNAME", "localhost")


@pytest.mark.asyncio
async def is_daq6510_available():
    try:
        daq = DAQ6510(HOSTNAME, SCPI_PORT)
        await daq.connect()
    except DeviceTimeoutError:
        return False

    return True


def is_daq6510_monitor_active():
    if VERBOSE_DEBUG:
        logger.debug("Checking if monitor is active...")

    client = DAQMonitorClient(timeout=0.5)

    try:
        client.connect()
        status = client.get_status()
        if status["status"] == "ok":
            return True
        else:
            return False
    finally:
        client.disconnect()
        if VERBOSE_DEBUG:
            logger.debug("Finished with checking for an active monitor.")


@pytest.mark.asyncio
async def test_constructor():
    daq = DAQ6510(HOSTNAME, SCPI_PORT)
    await daq.connect()

    response = await daq.query("*IDN?\n")

    idn = response.decode().strip()
    manufacturer, model, _, firmware = idn.split(",")

    assert manufacturer == "KEITHLEY INSTRUMENTS"
    assert "DAQ6510" in model
    assert (firmware == "1.7.12b") or (firmware == "0.1.0")

    await daq.disconnect()


@pytest.mark.asyncio
async def test_action_response():
    # This test is for the simulator only

    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        manufacturer, model, serial_number, firmware_version = await daq.get_idn_parts()
        assert manufacturer == "KEITHLEY INSTRUMENTS"
        assert "DAQ6510" in model
        if serial_number == "SIMULATOR":
            response = await daq.query("*ACTION-RESPONSE?\n")
            logger.info(f"*ACTION-RESPONSE: {response=}")
            await daq.write("*ACTION-NO-RESPONSE\n")


@pytest.mark.asyncio
async def test_connection(caplog):
    daq = DAQ6510(HOSTNAME, SCPI_PORT)

    assert not await daq.is_connected()

    await daq.connect()

    assert await daq.is_connected()

    await daq.disconnect()

    assert not await daq.is_connected()

    await daq.disconnect()  # This should do nothing

    await daq.connect()

    caplog.clear()

    await daq.connect()  # calling this when the connection is open issues a warning

    assert "Trying to connect to an already connected device" in caplog.text

    await daq.disconnect()

    assert not await daq.is_connected()

    await daq.reconnect()
    assert await daq.is_connected()

    await daq.reconnect()
    assert await daq.is_connected()

    await daq.disconnect()


@pytest.mark.asyncio
async def test_context_manager():
    logger.debug("Entering the actual test!")

    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        assert await daq.is_connected()

        response = await daq.query("*IDN?\n")

        idn = response.decode().strip()
        manufacturer, model, _, firmware = idn.split(",")

        assert manufacturer == "KEITHLEY INSTRUMENTS"
        assert "DAQ6510" in model
        assert (firmware == "1.7.12b") or (firmware == "0.1.0")

    assert not await daq.is_connected()


@pytest.mark.asyncio
async def test_incorrect_construction():
    daq = DAQ6510(HOSTNAME)
    daq.hostname = "unknown"  # set this explicitly because the local_settings might define the HOSTNAME
    with pytest.raises(DeviceConnectionError, match="DAQ6510: Address resolution error for unknown"):
        await daq.connect()

    if VERBOSE_DEBUG:
        logger.debug(f"1 <{'-' * 200}")

    daq = DAQ6510(HOSTNAME)
    daq.hostname = None
    with pytest.raises(ValueError, match="DAQ6510: Hostname is not initialized"):
        await daq.connect()

    if VERBOSE_DEBUG:
        logger.debug(f"2 <{'-' * 200}")

    daq = DAQ6510(HOSTNAME)
    daq.port = None

    with pytest.raises(ValueError, match="DAQ6510: Port number is not initialized"):
        await daq.connect()

    if VERBOSE_DEBUG:
        logger.debug(f"3 <{'-' * 200}")

    daq = DAQ6510(HOSTNAME, 3456)  # pass an incorrect port number, check with `lsof -i -n -P |grep 3456`

    with pytest.raises(DeviceConnectionError, match="refused|failed"):
        await daq.connect()

    if VERBOSE_DEBUG:
        logger.debug(f"4 <{'-' * 200}")


@pytest.mark.asyncio
async def test_initialize():
    init_commands = [
        ('TRAC:MAKE "test1", 1000', False),  # create a new buffer
        # settings for channel 1 and 2 of slot 1
        ('SENS:FUNC "TEMP", (@101:102)', False),  # set the function to temperature
        ("SENS:TEMP:TRAN FRTD, (@101)", False),  # set the transducer to 4-wire RTD
        ("SENS:TEMP:RTD:FOUR PT100, (@101)", False),  # set the type of the 4-wire RTD
        ("SENS:TEMP:TRAN RTD, (@102)", False),  # set the transducer to 2-wire RTD
        ("SENS:TEMP:RTD:TWO PT100, (@102)", False),  # set the type of the 2-wire RTD
        ('ROUT:SCAN:BUFF "test1"', False),
        ("ROUT:SCAN:CRE (@101:102)", False),
        ("ROUT:CHAN:OPEN (@101:102)", False),
        ("ROUT:STAT? (@101:102)", True),
        ("ROUT:SCAN:STAR:STIM NONE", False),
        # ("ROUT:SCAN:ADD:SING (@101, 102)", False),  # not sure what this does, not really needed
        ("ROUT:SCAN:COUN:SCAN 1", False),  # not sure if this is needed in this setting
        # ("ROUT:SCAN:INT 1", False),
    ]

    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        await daq.initialize(reset_device=True)

    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        await daq.initialize(commands=init_commands, reset_device=False)
        response = (await daq.query("ROUT:SCAN:BUFF?")).decode().strip()
        assert response == "test1"

    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        await daq.initialize(reset_device=True)


@pytest.mark.asyncio
async def test_timeout_on_device():
    # This is something that can not be tested since both the `query/trans()` and `write()` command
    # append the required separator to the command string if it is missing.
    ...


@pytest.mark.asyncio
async def test_check_lan_configuration():
    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        # DON'T change the LAN configuration, because you might not be able to reconnect.
        # await daq.write(':SYST:COMM:LAN:CONF "AUTO"')
        # await asyncio.sleep(0.1)

        await daq.write(":SYST:COMM:LAN:CONF?")

        response = (await daq.read()).decode().strip()

        logger.info(f"{response=}")

        mode, ip, subnet, gateway = response.split(",")
        assert mode in ("auto", "manual")
        assert ip == HOSTNAME


@pytest.mark.asyncio
async def test_a_scan():
    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        # Initialize

        await daq.write("*RST")  # this also the user-defined buffer "test1"

        for cmd, response in [
            ('TRAC:MAKE "test1", 1000', False),  # create a new buffer
            # settings for channel 1 and 2 of slot 1
            ('SENS:FUNC "TEMP", (@101:102)', False),  # set the function to temperature
            ("SENS:TEMP:TRAN FRTD, (@101)", False),  # set the transducer to 4-wire RTD
            ("SENS:TEMP:RTD:FOUR PT100, (@101)", False),  # set the type of the 4-wire RTD
            ("SENS:TEMP:TRAN RTD, (@102)", False),  # set the transducer to 2-wire RTD
            ("SENS:TEMP:RTD:TWO PT100, (@102)", False),  # set the type of the 2-wire RTD
            ('ROUT:SCAN:BUFF "test1"', False),
            ("ROUT:SCAN:CRE (@101:102)", False),
            ("ROUT:CHAN:OPEN (@101:102)", False),
            ("ROUT:STAT? (@101:102)", True),
            ("ROUT:SCAN:STAR:STIM NONE", False),
            # ("ROUT:SCAN:ADD:SING (@101, 102)", False),  # not sure what this does, not really needed
            ("ROUT:SCAN:COUN:SCAN 1", False),  # not sure if this is needed in this setting
            # ("ROUT:SCAN:INT 1", False),
        ]:
            if response:
                print(f"Sending {cmd}... response=", end="")
                print(await daq.trans(cmd))
            else:
                print(f"Sending {cmd}...")
                await daq.write(cmd)

        # Read out the channels

        # daq.write('TRAC:CLE "test1"\n')

        for _ in range(10):
            await daq.write("INIT:IMM")
            await daq.write("*WAI")

            # Reading the data

            # When a trigger mode is running, these READ? commands can not be used.

            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")
            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")
            # time.sleep(1)
            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")
            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")

            # Read out the buffer

            response = await daq.trans('TRAC:DATA? 1, 2, "test1", CHAN, TST, READ')
            print(f"{response = }")
            ch1, tst1, val1, ch2, tst2, val2 = response.decode().split(",")
            print(f"Channel: {ch1} Time: {tst1} Value: {float(val1):.4f}\t", end="")
            print(f"Channel: {ch2} Time: {tst2} Value: {float(val2):.4f}")
            await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_another_scan():
    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        # Initialize

        n_readings = 50

        await daq.write("*RST")  # This also clears the default buffers

        for cmd, response in [
            ('SENS:FUNC "TEMP", (@101,102)', False),
            ("SENS:TEMP:UNIT CELS, (@101,102)", False),
            ("SENS:TEMP:TRAN FRTD, (@101)", False),  # set the transducer to 4-wire RTD
            ("SENS:TEMP:RTD:FOUR PT100, (@101)", False),  # set the type of the 4-wire RTD
            ("SENS:TEMP:TRAN RTD, (@102)", False),  # set the transducer to 2-wire RTD
            ("SENS:TEMP:RTD:TWO PT100, (@102)", False),  # set the type of the 2-wire RTD
            # Set the amount of time that the input signal is measured.
            ("SENS:TEMP:NPLC 0.1, (@101,102)", False),
            ('TRIG:LOAD "Empty"', False),
            ('TRIG:BLOC:BUFF:CLEAR 1, "defbuffer1"', False),
            ('TRIG:BLOC:MDIG 2, "defbuffer1"', False),
            (f"TRIG:BLOC:BRAN:COUN 3, {n_readings}, 2", False),
        ]:
            if response:
                print(f"Sending {cmd}... response=", end="")
                print(await daq.trans(cmd))
            else:
                print(f"Sending {cmd}...")
                await daq.write(cmd)

        # Read out the channels

        # What should this read_timeout be and how shall I set and reset this?
        daq.read_timeout = 10.0

        for _ in range(10):
            await daq.write("INIT:IMM")
            await daq.write("*WAI")

            # Reading the data

            response = await daq.trans(f'TRAC:DATA? 1, {n_readings}, "defbuffer1", CHAN, TST, READ')
            print(f"{response = }")
            # ch1, tst1, val1, ch2, tst2, val2 = response.split(",")
            # print(f"Channel: {ch1} Time: {tst1} Value: {float(val1):.4f}\t", end="")
            # print(f"Channel: {ch2} Time: {tst2} Value: {float(val2):.4f}")
            await asyncio.sleep(0.1)


@pytest.mark.skipif(
    not is_daq6510_monitor_active(), reason="The DAQ6510 Monitoring service needs to be running for this test."
)
@pytest.mark.asyncio
async def test_daq6510_mon():
    from egse.tempcontrol.keithley.daq6510_mon import DAQMonitorClient
    from egse.tempcontrol.keithley.daq6510_mon import DAQ_MON_CMD_PORT

    client = DAQMonitorClient(server_address="localhost", port=DAQ_MON_CMD_PORT)
    client.connect()

    try:
        # Get current status
        status = client.get_status()
        print(f"Service status: {json.dumps(status, indent=2)}")

        # Start polling with custom settings
        response = client.start_polling(channels=["101", "102"], interval=2.0)
        print(f"Start polling response: {response}")

        # Wait for a while
        time.sleep(5)

        # Change polling interval
        response = client.set_interval(3.0)
        print(f"Set interval response: {response}")

        # Wait for a while
        time.sleep(5)

        # Stop polling
        response = client.stop_polling()
        print(f"Stop polling response: {response}")

    finally:
        client.disconnect()


if __name__ == "__main__":
    from egse.log import logging

    # The statement logging.captureWarnings(True) redirects Python's warnings module output
    # (such as warnings.warn(...)) to the logging system, so warnings appear in your logs
    # instead of just printing to stderr. This is useful for unified logging and easier
    # debugging, especially in larger applications.
    logging.captureWarnings(True)

    try:
        # main_task = asyncio.run(test_action_response())
        main_task = asyncio.run(test_a_scan())
        # main_task = asyncio.run(test_constructor())
        # main_task = asyncio.run(test_context_manager())
        # main_task = asyncio.run(test_incorrect_construction())
        # main_task = asyncio.run(test_initialize())
        # main_task = asyncio.run(test_timeout_on_device())  # will do nothing, cannot be tested
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, terminating.")
