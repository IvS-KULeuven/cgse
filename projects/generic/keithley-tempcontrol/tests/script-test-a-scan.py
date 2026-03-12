import asyncio

from egse.env import bool_env
from egse.log import logger
from egse.settings import Settings
from egse.tempcontrol.keithley.daq6510_adev import DAQ6510

settings = Settings.load("Keithley DAQ6510")

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")

SCPI_PORT = settings.get("PORT", 5025)
HOSTNAME = settings.get("HOSTNAME", "localhost")


async def test_a_scan():
    async with DAQ6510(HOSTNAME, SCPI_PORT) as daq:
        logger.info("Initialization: resetting device...")

        await daq.write("*RST")  # this also the user-defined buffer "test1"

        init_commands = [
            ('TRAC:MAKE "test1", 1000', False),  # create a new buffer
            # settings for channel 1 and 2 of slot 1
            ('SENS:FUNC "TEMP", (@101:102)', False),  # set the function to temperature
            ("SENS:TEMP:TRAN FRTD, (@101)", False),  # set the transducer to 4-wire RTD
            ("SENS:TEMP:RTD:FOUR PT100, (@101)", False),  # set the type of the 4-wire RTD
            ("SENS:TEMP:TRAN RTD, (@102)", False),  # set the transducer to 2-wire RTD
            ("SENS:TEMP:RTD:TWO PT100, (@102)", False),  # set the type of the 2-wire RTD
            ('ROUT:SCAN:BUFF "test1"', False),  # set the buffer for the scan
            ("ROUT:SCAN:CRE (@101:102)", False),  # create a scan list with channels 101 and 102
            ("ROUT:CHAN:OPEN (@101:102)", False),  # open the channels
            ("ROUT:STAT? (@101:102)", True),  # check if the channels are open
            ("ROUT:SCAN:STAR:STIM NONE", False),  # set the trigger to immediate
            ("ROUT:SCAN:ADD:SING (@101, 102)", False),  # add the channels to the scan list
            ("ROUT:SCAN:COUN:SCAN 1", False),  # set the number of scans to 1
            ("ROUT:SCAN:INT 1", False),  # set the scan interval to 1 second
        ]

        response = await daq.initialize(init_commands)
        if VERBOSE_DEBUG:
            logger.debug(f"Initialization response: {response}")

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

            response = await daq.trans('TRAC:DATA? 1, 2, "test1", CHAN, TST, READ')  # read 2 values from buffer "test1"
            if VERBOSE_DEBUG:
                print(f"{response = }")
            ch1, tst1, val1, ch2, tst2, val2 = response.decode().split(",")
            print(f"Channel: {ch1} Time: {tst1} Value: {float(val1):.4f}")
            print(f"Channel: {ch2} Time: {tst2} Value: {float(val2):.4f}")

            await asyncio.sleep(1.0)


if __name__ == "__main__":
    try:
        main_task = asyncio.run(test_a_scan())
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, terminating.")
