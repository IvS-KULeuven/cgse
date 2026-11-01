"""
Keithley DAQ6510 device implementation as an asynchronous SCPI interface.

The driver uses the instrument's own background scan: the scan is configured and started once, and the instrument
fills a reading buffer at the configured interval. Readings are then fetched incrementally with `TRACe:ACTual:END?`
and `TRACe:DATA?`, so no request ever waits for a scan to complete.

Classes:
    DAQ6510: An asynchronous SCPI interface for the Keithley DAQ6510 device.
    Reading: One reading from the reading buffer.
"""

__all__ = [
    "DAQ6510",
    "Reading",
]

import datetime
from dataclasses import dataclass

from egse.log import logger
from egse.scpi import AsyncSCPIInterface
from egse.settings import Settings
from egse.tempcontrol.keithley.daq6510_config import DEFAULT_BUFFER
from egse.tempcontrol.keithley.daq6510_config import ScanConfig

dev_settings = Settings.load("Keithley DAQ6510")

DEV_HOST = dev_settings.get("HOSTNAME", "localhost")
DEV_PORT = dev_settings.get("PORT", 5025)
DEVICE_NAME = dev_settings.get("DEVICE_NAME", "DAQ6510")
READ_TIMEOUT = dev_settings.get("TIMEOUT", 5.0)
DEV_ID_VALIDATION = "DAQ6510"

SIMULATOR_SERIAL_NUMBER = "SIMULATOR"
"""The simulator identifies itself with this serial number, see `daq6510_model.IDN`."""

BUFFER_ELEMENTS = ("CHAN", "SEC", "FRAC", "READ", "UNIT")
"""The buffer elements requested for each reading, the order matters for parsing."""


@dataclass(frozen=True)
class Reading:
    """One reading from the DAQ6510 reading buffer."""

    channel: str
    timestamp: datetime.datetime
    """Time of the measurement in UTC, as recorded by the instrument."""
    value: float
    unit: str


def parse_readings(response: str, elements: tuple[str, ...] = BUFFER_ELEMENTS) -> list[Reading]:
    """Parses the response of `TRACe:DATA?` with the given buffer elements into a list of Readings.

    Raises:
        ValueError: when the number of values in the response is not a multiple of the number of elements.
    """

    values = [x.strip() for x in response.strip().split(",")] if response.strip() else []

    n = len(elements)
    if len(values) % n:
        raise ValueError(f"Expected a multiple of {n} values in the buffer data, got {len(values)}: {response!r}")

    readings = []
    for idx in range(0, len(values), n):
        item = dict(zip(elements, values[idx : idx + n]))
        epoch = int(item["SEC"]) + float(item["FRAC"])
        readings.append(
            Reading(
                channel=item["CHAN"],
                timestamp=datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc),
                value=float(item["READ"]),
                unit=item["UNIT"],
            )
        )
    return readings


class DAQ6510(AsyncSCPIInterface):
    """Keithley DAQ6510 specific implementation."""

    def __init__(self, hostname: str = DEV_HOST, port: int = DEV_PORT, read_timeout: float = READ_TIMEOUT):
        """Initialize a Keithley DAQ6510 interface.

        Args:
            hostname: Hostname or IP address
            port: TCP port (default 5025 for SCPI)
            read_timeout: Timeout when waiting for a response [s]
        """
        super().__init__(
            device_name=DEVICE_NAME,
            hostname=hostname,
            port=port,
            id_validation=DEV_ID_VALIDATION,  # String that must appear in IDN? response
            read_timeout=read_timeout,
        )

    @property
    def is_connection_open(self) -> bool:
        """True when the socket connection is open. Unlike `is_connected()`, this doesn't talk to the device."""
        return self._is_connection_open

    async def query_str(self, command: str) -> str:
        return (await self.trans(command)).decode().strip()

    async def get_idn(self) -> str:
        return await self.query_str("*IDN?")

    def is_simulator(self) -> bool:
        """True when the identification at connect has the serial number of the simulator (`daq6510_sim`).

        The identification is "<manufacturer>,<model>,<serial number>,<firmware>". Before the first connection the
        identification is not known and this returns False, see `identification`.
        """
        fields = (self.identification or "").split(",")
        return len(fields) > 2 and fields[2].strip() == SIMULATOR_SERIAL_NUMBER

    async def reset(self) -> None:
        """Resets the instrument to its default settings. This also aborts a running scan and clears the buffers."""
        await self.write("*RST")
        await self.write("*CLS")

    async def get_errors(self) -> list[str]:
        """Reads and removes all errors from the error queue. Returns an empty list when there are no errors."""
        errors = []
        for _ in range(100):  # the queue holds max 1000 entries, don't loop forever on a misbehaving device
            response = await self.query_str("SYST:ERR?")
            if response.startswith("0,") or not response:
                break
            errors.append(response)
        return errors

    async def set_time(self, dt: datetime.datetime | None = None) -> None:
        """Sets the date and time of the instrument, default is the current time in UTC."""
        dt = dt or datetime.datetime.now(datetime.timezone.utc)
        await self.write(f"SYST:TIME {dt.year}, {dt.month}, {dt.day}, {dt.hour}, {dt.minute}, {dt.second}")

    async def get_time(self) -> str:
        return await self.query_str("SYST:TIME? 1")

    async def configure_scan(self, config: ScanConfig) -> None:
        """Configures the sensors, the reading buffer and the scan list. The scan is not started.

        The buffer is cleared and resized to the configured capacity. The scan repeats until aborted
        (scan count = 0).
        """

        for sensor in config.sensors:
            await self.write(f'SENS:FUNC "{sensor.function}", {sensor.channel_list}')
            for setting, value in sensor.settings:
                await self.write(f"SENS:{sensor.function}:{setting} {value}, {sensor.channel_list}")

        buffer = config.buffer_name
        if buffer != DEFAULT_BUFFER and buffer != "defbuffer2":
            logger.warning(f"Using user-defined buffer {buffer!r}, it must already exist on the instrument.")

        await self.write(f'TRAC:POIN {config.buffer_capacity}, "{buffer}"')  # this also clears the buffer
        await self.write(f'TRAC:FILL:MODE CONT, "{buffer}"')

        await self.write(f"ROUT:SCAN:CRE {config.channel_list}")
        await self.write(f'ROUT:SCAN:BUFF "{buffer}"')
        await self.write("ROUT:SCAN:STAR:STIM NONE")  # start immediately on INIT, don't wait for a trigger event
        await self.write("ROUT:SCAN:COUN:SCAN 0")  # repeat until aborted
        await self.write(f"ROUT:SCAN:INT {config.interval}")

    async def start_scan(self) -> None:
        await self.write("INIT")

    async def abort(self) -> None:
        """Stops the trigger model and the scan."""
        await self.write("ABOR")

    async def clear_buffer(self, buffer_name: str = DEFAULT_BUFFER) -> None:
        await self.write(f'TRAC:CLE "{buffer_name}"')

    async def get_scan_state(self) -> str:
        """Returns the state of the scan as reported by `ROUT:SCAN:STAT?`, e.g. 'RUNNING;1;2'."""
        return await self.query_str("ROUT:SCAN:STAT?")

    async def get_buffer_count(self, buffer_name: str = DEFAULT_BUFFER) -> int:
        """Returns the number of readings in the buffer."""
        return int(await self.query_str(f'TRAC:ACT? "{buffer_name}"'))

    async def get_buffer_end(self, buffer_name: str = DEFAULT_BUFFER) -> int:
        """Returns the index of the last reading in the buffer, 0 when the buffer is empty."""
        return int(await self.query_str(f'TRAC:ACT:END? "{buffer_name}"'))

    async def read_buffer(self, start: int, end: int, buffer_name: str = DEFAULT_BUFFER) -> list[Reading]:
        """Returns the readings with index start to end (inclusive) from the buffer."""
        elements = ", ".join(BUFFER_ELEMENTS)
        response = await self.query_str(f'TRAC:DATA? {start}, {end}, "{buffer_name}", {elements}')
        return parse_readings(response)
