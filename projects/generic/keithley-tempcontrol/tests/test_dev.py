import time

import pytest
from egse.device import DeviceConnectionError
from egse.device import DeviceTimeoutError
from egse.system import Timer
from egse.tempcontrol.keithley.daq6510_dev import DAQ6510EthernetInterface

SCPI_PORT = 5025
HOSTNAME = "192.168.68.77"  # hostname at home with DHCP


def is_daq6510_available():
    try:
        daq = DAQ6510EthernetInterface(HOSTNAME, SCPI_PORT)
        daq.connect()
    except DeviceTimeoutError:
        return False

    return True


def test_constructor():
    daq = DAQ6510EthernetInterface(HOSTNAME, SCPI_PORT)
    daq.connect()

    response = daq.trans("*IDN?\n")

    assert response == "KEITHLEY INSTRUMENTS,MODEL DAQ6510,04569510,1.7.12b"

    daq.disconnect()


def test_connection(caplog):
    daq = DAQ6510EthernetInterface(HOSTNAME, SCPI_PORT)

    assert not daq.is_connected()

    daq.connect()

    assert daq.is_connected()

    daq.disconnect()

    assert not daq.is_connected()

    daq.disconnect()  # This should do nothing

    daq.connect()

    caplog.clear()

    daq.connect()  # calling this when the connection is open issues a warning

    assert "trying to connect to an already connected socket" in caplog.text

    daq.disconnect()

    assert not daq.is_connected()

    daq.reconnect()
    assert daq.is_connected()

    daq.reconnect()
    assert daq.is_connected()

    daq.disconnect()


def test_context_manager():
    with DAQ6510EthernetInterface(HOSTNAME, SCPI_PORT) as daq:
        assert daq.is_connected()

    assert not daq.is_connected()


def test_incorrect_construction():
    daq = DAQ6510EthernetInterface()
    daq.hostname = "unknown"  # set this explicitly because the local_settings might define he HOSTNAME
    with pytest.raises(DeviceConnectionError, match="DAQ6510: Socket address info error for unknown"):
        daq.connect()

    daq = DAQ6510EthernetInterface()
    daq.hostname = None
    with pytest.raises(ValueError, match="hostname is not initialized"):
        daq.connect()

    daq = DAQ6510EthernetInterface(HOSTNAME)
    daq.port = None

    with pytest.raises(ValueError, match="port number is not initialized"):
        daq.connect()

    daq = DAQ6510EthernetInterface(HOSTNAME, 3000)  # pass an incorrect port number

    with pytest.raises(DeviceConnectionError, match="DAQ6510: Connection refused"):
        daq.connect()


def test_write_read():
    with DAQ6510EthernetInterface(HOSTNAME, SCPI_PORT) as daq:
        daq.write(':SYST:COMM:LAN:CONF "AUTO"')
        daq.write(":SYST:COMM:LAN:CONF?")

        response = daq.read().decode()

        assert response.startswith("auto")


def test_a_scan():
    with DAQ6510EthernetInterface() as daq:
        # Initialize

        daq.write("*RST")  # this also the user-defined buffer "test1"

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
                print(daq.trans(cmd))
            else:
                print(f"Sending {cmd}...")
                daq.write(cmd)

        # Read out the channels

        # daq.write('TRAC:CLE "test1"\n')

        for _ in range(10):
            daq.write("INIT:IMM")
            daq.write("*WAI")

            # Reading the data

            # When a trigger mode is running, these READ? commands can not be used.

            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")
            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")
            # time.sleep(1)
            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")
            # print(daq.trans('READ? "test1", CHAN, TST, READ\n', wait=False), end="")

            # Read out the buffer

            response = daq.trans('TRAC:DATA? 1, 2, "test1", CHAN, TST, READ')
            print(f"{response = }")
            ch1, tst1, val1, ch2, tst2, val2 = response.split(",")
            print(f"Channel: {ch1} Time: {tst1} Value: {float(val1):.4f}\t", end="")
            print(f"Channel: {ch2} Time: {tst2} Value: {float(val2):.4f}")
            time.sleep(0.1)


def test_another_scan():
    with DAQ6510EthernetInterface() as daq:
        # Initialize

        n_readings = 50

        daq.write("*RST")  # This also clears the default buffers

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
                print(daq.trans(cmd))
            else:
                print(f"Sending {cmd}...")
                daq.write(cmd)

        # Read out the channels

        for _ in range(10):
            daq.write("INIT:IMM")
            daq.write("*WAI")

            # Reading the data

            response = daq.trans(f'TRAC:DATA? 1, {n_readings}, "defbuffer1", CHAN, TST, READ')
            print(f"{response = }")
            # ch1, tst1, val1, ch2, tst2, val2 = response.split(",")
            # print(f"Channel: {ch1} Time: {tst1} Value: {float(val1):.4f}\t", end="")
            # print(f"Channel: {ch2} Time: {tst2} Value: {float(val2):.4f}")
            time.sleep(0.1)
