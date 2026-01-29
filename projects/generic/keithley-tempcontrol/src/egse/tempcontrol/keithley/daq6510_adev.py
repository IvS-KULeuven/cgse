"""
Keithley DAQ6510 device implementation as an SCPI interface.

This module provides an asynchronous interface to communicate with
the Keithley DAQ6510 data acquisition unit using SCPI commands.

Classes:
    DAQ6510: An asynchronous SCPI interface for the Keithley DAQ6510 device.

"""

__all__ = [
    "DAQ6510",
]

import asyncio
from typing import Any
from typing import Dict
from typing import Optional

from egse.log import logger
from egse.scpi import AsyncSCPIInterface
from egse.settings import Settings

dev_settings = Settings.load("Keithley DAQ6510")

DEV_HOST = dev_settings.get("HOSTNAME", "localhost")
DEV_PORT = dev_settings.get("PORT", 5025)
DEVICE_NAME = dev_settings.get("DEVICE_NAME", "DAQ6510")
DEV_ID_VALIDATION = "DAQ6510"


class DAQ6510(AsyncSCPIInterface):
    """Keithley DAQ6510 specific implementation."""

    def __init__(self, hostname: str = DEV_HOST, port: int = DEV_PORT, settings: Optional[Dict[str, Any]] = None):
        """Initialize a Keithley DAQ6510 interface.

        Args:
            hostname: Hostname or IP address
            port: TCP port (default 5025 for SCPI)
            settings: Additional device settings
        """
        super().__init__(
            device_name=DEVICE_NAME,
            hostname=hostname,
            port=port,
            settings=settings,
            id_validation=DEV_ID_VALIDATION,  # String that must appear in IDN? response
            read_timeout=5.0,
        )

        self._measurement_lock = asyncio.Lock()

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
