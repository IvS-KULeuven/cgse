import asyncio
import logging
from typing import Any
from typing import Dict
from typing import Optional

from egse.scpi import AsyncSCPIInterface

logger = logging.getLogger(__name__)


class DAQ6510(AsyncSCPIInterface):
    """Keithley DAQ6510 specific implementation."""

    def __init__(self, hostname: str, port: int = 5025, settings: Optional[Dict[str, Any]] = None):
        """Initialize a Keithley DAQ6510 interface.

        Args:
            hostname: Hostname or IP address
            port: TCP port (default 5025 for SCPI)
            settings: Additional device settings
        """
        super().__init__(
            device_name="DAQ6510",
            hostname=hostname,
            port=port,
            settings=settings,
            id_validation="DAQ6510",  # String that must appear in IDN? response
        )

        self._measurement_lock = asyncio.Lock()

    async def initialize(self):
        # Initialize

        await self.write("*RST")  # this also the user-defined buffer "test1"

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
                logger.info(f"Sending {cmd}...")
                response = (await self.trans(cmd)).decode().strip()
                logger.info(f"{response = }")
            else:
                logger.info(f"Sending {cmd}...")
                await self.write(cmd)

    async def get_measurement(self, channel: str) -> float:
        """Get a measurement from a specific channel.

        Args:
            channel: Channel to measure (e.g., "101")

        Returns:
            The measured value as a float
        """
        async with self._measurement_lock:
            cmd = "INIT:IMM"
            logger.info(f"Sending {cmd}...")
            await self.write(cmd)
            cmd = "*WAI"
            logger.info(f"Sending {cmd}...")
            await self.write(cmd)

            if channel == "101":
                start_index = end_index = 1
            elif channel == "102":
                start_index = end_index = 2
            else:
                return float("nan")

            response = (
                (await self.trans(f'TRAC:DATA? {start_index}, {end_index}, "test1", CHAN, TST, READ')).decode().strip()
            )

            logger.info(f"{response = }")

            ch, tst, val = response.split(",")

            logger.info(f"Channel: {ch} Time: {tst} Value: {float(val):.4f}")

            return float(val)
