import asyncio
import json
import time

import pytest

from egse.device import DeviceConnectionError
from egse.device import DeviceTimeoutError
from egse.tempcontrol.keithley.daq6510_adev import DAQ6510

SCPI_PORT = 5025
HOSTNAME = "192.168.68.77"  # hostname at home with DHCP


@pytest.mark.sayncio
async def is_daq6510_available():
    try:
        daq = DAQ6510(HOSTNAME, SCPI_PORT)
        await daq.connect()
    except DeviceTimeoutError:
        return False

    return True


@pytest.mark.asyncio
async def test_constructor():
    daq = DAQ6510(HOSTNAME, SCPI_PORT)
    await daq.connect()

    response = await daq.query("*IDN?\n")

    assert response == "KEITHLEY INSTRUMENTS,MODEL DAQ6510,04569510,1.7.12b"

    await daq.disconnect()


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
    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        assert await daq.is_connected()

    assert not await daq.is_connected()


@pytest.mark.asyncio
async def test_incorrect_construction():
    daq = DAQ6510(HOSTNAME)
    daq.hostname = "unknown"  # set this explicitly because the local_settings might define the HOSTNAME
    with pytest.raises(DeviceConnectionError, match="DAQ6510: Address resolution error for unknown"):
        await daq.connect()

    daq = DAQ6510(HOSTNAME)
    daq.hostname = None
    with pytest.raises(ValueError, match="DAQ6510: Hostname is not initialized"):
        await daq.connect()

    daq = DAQ6510(HOSTNAME)
    daq.port = None

    with pytest.raises(ValueError, match="DAQ6510: Port number is not initialized"):
        await daq.connect()

    daq = DAQ6510(HOSTNAME, 3000)  # pass an incorrect port number

    with pytest.raises(DeviceConnectionError, match="DAQ6510: Connection refused"):
        await daq.connect()


@pytest.mark.asyncio
async def test_write_read():
    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        await daq.write(':SYST:COMM:LAN:CONF "AUTO"')
        await daq.write(":SYST:COMM:LAN:CONF?")

        response = (await daq.read()).decode()

        assert response.startswith("auto")


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
            ch1, tst1, val1, ch2, tst2, val2 = response.split(",")
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


@pytest.mark.asyncio
async def test_daq6510_mon():
    from egse.tempcontrol.keithley.daq6510_mon import DAQMonitorClient

    client = DAQMonitorClient(server_address="localhost", port=5556)

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
        client.close()
