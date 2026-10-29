"""
A stateful model of the Keithley DAQ6510, used by the simulator and by the unit tests.

The model understands the subset of SCPI commands that is used by the asynchronous DAQ6510 driver
(`daq6510_adev.py`). It keeps a reading buffer that is filled by a background scan, computed lazily from a clock, so
there are no threads involved. Pass in your own `clock` to make the model deterministic in tests.

Commands are matched on their SCPI short form, so both `ROUTE:SCAN:COUNT:SCAN 0` and `ROUT:SCAN:COUN:SCAN 0` work.
Unknown commands and invalid arguments put an error in the error queue (read with `SYST:ERR?`) instead of being
silently ignored. Queries always return a response.

What is _not_ modelled: the response format of the real device for the UNIT, SEConds/FRACtional and TSTamp buffer
elements has not been verified against hardware yet.
"""

__all__ = [
    "DAQ6510Model",
    "ModelledDAQ6510",
]

import datetime
import math
import time
from dataclasses import dataclass
from functools import partial
from typing import Callable

from egse.device import DeviceConnectionError
from egse.scpi import get_channel_names
from egse.tempcontrol.keithley.daq6510_adev import DAQ6510

IDN = "KEITHLEY INSTRUMENTS,MODEL DAQ6510,SIMULATOR,0.2.0"

DEFAULT_BUFFERS = ("defbuffer1", "defbuffer2")
DEFAULT_CAPACITY = 100_000

UNITS = {"CELSIUS": "Celsius", "KELVIN": "Kelvin", "FAHRENHEIT": "Fahrenheit"}

VOWELS = set("AEIOU")

TEMPERATURE_PROFILE = (
    (0, 20.0),
    (300, 20.0),
    (600, 40.0),
    (900, 40.0),
    (1080, 50.0),
    (1380, 50.0),
    (1560, 60.0),
    (1860, 60.0),
    (2460, -100.0),
    (2880, -100.0),
    (3420, 20.0),
    (3600, 20.0),
)
"""The simulated temperature cycle as (time [s], temperature [°C]) points, linear in between. Starting from room
temperature, the temperature goes through three high plateaus, cools down to a low plateau and goes back to room
temperature. The cycle repeats, the last time is the duration of the cycle. The model uses the UTC wall clock as
time (seconds since the Unix epoch), so each cycle starts at a whole hour and continues across simulator restarts."""


def profile_temperature(t: float) -> float:
    """Returns the temperature [°C] of the TEMPERATURE_PROFILE at time t [s], the profile repeats indefinitely."""
    t %= TEMPERATURE_PROFILE[-1][0]
    for (t0, temp0), (t1, temp1) in zip(TEMPERATURE_PROFILE, TEMPERATURE_PROFILE[1:]):
        if t <= t1:
            return temp0 + (temp1 - temp0) * (t - t0) / (t1 - t0)
    return TEMPERATURE_PROFILE[-1][1]


def channel_temperature(channel: str, t: float) -> float:
    """Returns the simulated temperature [°C] of a channel at time t [s], the model uses seconds since the Unix epoch.

    All channels follow the TEMPERATURE_PROFILE with small, deterministic differences, so they can be told apart:
    a time lag, an offset and a ripple with a different period.
    """
    k = int(channel) % 100  # the channel number on the card
    lag = 20.0 * ((k - 1) % 6)
    offset = 0.15 * ((k - 1) % 5) - 0.3
    ripple = 0.1 * math.sin(2 * math.pi * t / (90.0 + 13.0 * k))
    return profile_temperature(max(t - lag, 0.0)) + offset + ripple


# Optional SCPI nodes that are dropped from the header before matching.
OPTIONAL_NODES = {"IMM", "NEXT"}


def short_form(header: str) -> str:
    """Returns the SCPI short form of a command header, e.g. 'ROUTe:SCAN:COUNt:SCAN' -> 'ROUT:SCAN:COUN:SCAN'.

    The short form of a mnemonic longer than four characters is its first four characters, or the first three when
    the fourth is a vowel. A leading colon and the optional nodes [:IMMediate] and [:NEXT] are removed.
    """
    is_query = header.endswith("?")
    header = header.rstrip("?").lstrip(":").upper()

    nodes = []
    for node in header.split(":"):
        if node.startswith("*"):
            nodes.append(node)
            continue
        short = node[:3] if len(node) > 4 and node[3] in VOWELS else node[:4]
        if short not in OPTIONAL_NODES:
            nodes.append(short)

    return ":".join(nodes) + ("?" if is_query else "")


def split_arguments(arguments: str) -> list[str]:
    """Splits SCPI arguments on commas, keeping channel lists '(@...)' and quoted strings together."""
    args, current, depth, quoted = [], "", 0, False
    for char in arguments:
        if char == '"':
            quoted = not quoted
        elif char == "(" and not quoted:
            depth += 1
        elif char == ")" and not quoted:
            depth -= 1
        if char == "," and depth == 0 and not quoted:
            args.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        args.append(current.strip())
    return args


def unquote(value: str) -> str:
    return value.strip().strip('"')


class SCPIError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Reading:
    channel: str
    seconds: int
    fractional: float
    value: float
    unit: str


class Buffer:
    def __init__(self, capacity: int = DEFAULT_CAPACITY, fill_mode: str = "CONT"):
        self.capacity = capacity
        self.fill_mode = fill_mode
        self.readings: list[Reading] = []

    def append(self, reading: Reading):
        if len(self.readings) < self.capacity:
            self.readings.append(reading)
        elif self.fill_mode == "CONT":
            self.readings.pop(0)
            self.readings.append(reading)
        # fill mode ONCE: the buffer is full and new readings are discarded

    def clear(self):
        self.readings.clear()


class DAQ6510Model:
    """A model of the DAQ6510 that processes SCPI command strings.

    Args:
        clock: function returning a monotonic time in seconds, defaults to `time.monotonic`
        wall_clock: function returning the current UTC time, called once to relate the clock to the device time
        scan_duration: time it takes to measure all channels in one scan [s]
        sleep: function used by `*WAI` and `*OPC?` to wait for a finite scan to complete, defaults to `time.sleep`
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime.datetime] | None = None,
        scan_duration: float = 0.1,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.clock = clock
        self.scan_duration = scan_duration
        self.sleep = sleep

        # The device time is derived from the clock, so all timestamps are consistent with a fake clock
        self._wall_epoch = (wall_clock or (lambda: datetime.datetime.now(datetime.timezone.utc)))()
        self._clock_epoch = clock()

        self.commands: list[str] = []
        """All command strings received by the model, useful for assertions in tests."""

        self.reset()

    # ----- state ---------------------------------------------------------------------------------------------------

    def reset(self):
        """Puts the model in the state after power-up or *RST."""
        self.buffers: dict[str, Buffer] = {name: Buffer() for name in DEFAULT_BUFFERS}
        self.errors: list[tuple[int, str]] = []
        self.function: dict[str, str] = {}
        """Measurement function per channel."""
        self.sense: dict[tuple[str, str], str] = {}
        """Sense settings per (channel, setting)."""
        self.scan_channels: list[str] = []
        self.scan_count = 1
        self.scan_interval = 0.0
        self.scan_buffer = "defbuffer1"
        self.scan_start_stimulus = "NONE"
        self.scan_state = "IDLE"
        self._scan_start: float | None = None
        self._scans_done = 0
        self._time_offset = datetime.timedelta(0)

    def _wall_time(self) -> datetime.datetime:
        return self._wall_epoch + datetime.timedelta(seconds=self.clock() - self._clock_epoch)

    def device_time(self) -> datetime.datetime:
        return self._wall_time() + self._time_offset

    def _update_scan(self):
        """Adds the readings of all scans that have completed since the last update."""
        if self.scan_state != "RUNNING" or self._scan_start is None:
            return

        elapsed = self.clock() - self._scan_start
        if elapsed < self.scan_duration:
            return

        period = max(self.scan_interval, self.scan_duration)
        completed = int((elapsed - self.scan_duration) // period) + 1
        if self.scan_count:
            completed = min(completed, self.scan_count)

        buffer = self.buffers[self.scan_buffer]
        now = self.clock()
        for scan in range(self._scans_done, completed):
            # The device timestamp of the end of this scan
            age = now - (self._scan_start + scan * period + self.scan_duration)
            timestamp = self.device_time() - datetime.timedelta(seconds=age)
            for idx, channel in enumerate(self.scan_channels):
                delay = self.scan_duration * idx / len(self.scan_channels)
                ts = timestamp + datetime.timedelta(seconds=delay)
                epoch = ts.timestamp()
                # The profile follows the wall clock (not the device time that can be set with SYST:TIME), so it
                # continues where it was when the simulator is restarted.
                t = self._wall_epoch.timestamp() + now - age + delay - self._clock_epoch
                buffer.append(
                    Reading(
                        channel=channel,
                        seconds=int(epoch),
                        fractional=epoch - int(epoch),
                        value=self._measure(channel, t),
                        unit=self._unit(channel),
                    )
                )
        self._scans_done = completed

        if self.scan_count and completed >= self.scan_count:
            self.scan_state = "SUCCESS"

    def _unit(self, channel: str) -> str:
        unit = self.sense.get((channel, "UNIT"), "CELSIUS").upper()
        for key, name in UNITS.items():
            if key.startswith(unit[:4]):
                return name
        return "Celsius"

    def _measure(self, channel: str, t: float) -> float:
        """The temperature of the channel at time t [s] since the start of the model, in the unit of the channel."""
        value = channel_temperature(channel, t)
        unit = self._unit(channel)
        if unit == "Kelvin":
            value += 273.15
        elif unit == "Fahrenheit":
            value = value * 9 / 5 + 32
        return value

    def _buffer(self, name: str | None) -> Buffer:
        name = unquote(name) if name else "defbuffer1"
        if name not in self.buffers:
            raise SCPIError(-224, f'Illegal parameter value, buffer "{name}" does not exist')
        return self.buffers[name]

    # ----- command processing --------------------------------------------------------------------------------------

    def process(self, command_string: str) -> str | None:
        """Processes one or more SCPI commands separated by ';' and returns the response, if any.

        Multiple responses are joined with ';', like the real device does.
        """
        responses = []
        for command in command_string.split(";"):
            command = command.strip()
            if not command:
                continue
            self.commands.append(command)
            response = self._process_one(command)
            if response is not None:
                responses.append(response)

        return ";".join(responses) if responses else None

    def _process_one(self, command: str) -> str | None:
        header, _, arguments = command.partition(" ")
        key = short_form(header)
        args = split_arguments(arguments)

        self._update_scan()

        handler = self._handlers().get(key)

        # The sense settings, e.g. SENS:TEMP:TRAN, are too many to list, they are handled generically.
        if handler is None and key.startswith("SENS:") and not key.endswith("?"):
            handler = partial(self._sense_setting, key)

        if handler is None:
            self.errors.append((-113, f"Undefined header;1;{command}"))
            return "" if key.endswith("?") else None

        try:
            return handler(args)
        except SCPIError as exc:
            self.errors.append((exc.code, exc.message))
        except (ValueError, IndexError) as exc:
            self.errors.append((-224, f"Illegal parameter value;1;{command} ({exc})"))
        return "" if key.endswith("?") else None

    def _handlers(self) -> dict[str, Callable[[list[str]], str | None]]:
        return {
            "*IDN?": lambda args: IDN,
            "*RST": lambda args: self.reset(),
            "*CLS": lambda args: self.errors.clear(),
            "*OPC?": lambda args: self._wait_for_scan() or "1",
            "*WAI": lambda args: self._wait_for_scan(),
            "SYST:ERR?": self._system_error,
            "SYST:TIME": self._set_time,
            "SYST:TIME?": self._get_time,
            "SYST:BEEP": lambda args: None,
            "SENS:FUNC": self._sense_function,
            "TRAC:MAKE": self._trace_make,
            "TRAC:CLE": lambda args: self._buffer(args[0] if args else None).clear(),
            "TRAC:POIN": self._trace_points,
            "TRAC:POIN?": lambda args: str(self._buffer(args[0] if args else None).capacity),
            "TRAC:FILL:MODE": self._trace_fill_mode,
            "TRAC:ACT?": lambda args: str(len(self._buffer(args[0] if args else None).readings)),
            "TRAC:ACT:STAR?": self._trace_actual_start,
            "TRAC:ACT:END?": lambda args: str(len(self._buffer(args[0] if args else None).readings)),
            "TRAC:DATA?": self._trace_data,
            "ROUT:SCAN": self._route_scan_create,
            "ROUT:SCAN:CRE": self._route_scan_create,
            "ROUT:SCAN:COUN:SCAN": self._route_scan_count,
            "ROUT:SCAN:COUN:SCAN?": lambda args: str(self.scan_count),
            "ROUT:SCAN:INT": self._route_scan_interval,
            "ROUT:SCAN:INT?": lambda args: str(self.scan_interval),
            "ROUT:SCAN:BUFF": self._route_scan_buffer,
            "ROUT:SCAN:STAR:STIM": self._route_scan_start_stimulus,
            "ROUT:SCAN:STAR:STIM?": lambda args: self.scan_start_stimulus,
            "ROUT:SCAN:STAT?": lambda args: f"{self.scan_state};{self._scans_done};{len(self.scan_channels)}",
            "INIT": self._initiate,
            "ABOR": self._abort,
        }

    def _system_error(self, args) -> str:
        if not self.errors:
            return '0,"No error;0;0 0"'
        code, message = self.errors.pop(0)
        return f'{code},"{message}"'

    def _set_time(self, args):
        year, month, day, hour, minute, second = (int(x) for x in args)
        target = datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc)
        self._time_offset = target - self._wall_time()

    def _get_time(self, args) -> str:
        return self.device_time().strftime("%a %b %d %H:%M:%S %Y")

    @staticmethod
    def _channels(channel_list: str) -> list[str]:
        channels = get_channel_names(channel_list)
        if not channels:
            raise SCPIError(-224, f"Illegal parameter value, invalid channel list {channel_list}")
        return channels

    def _sense_function(self, args):
        function = unquote(args[0]).upper()
        channels = self._channels(args[1]) if len(args) > 1 else []
        for channel in channels:
            self.function[channel] = function

    def _sense_setting(self, key: str, args: list[str]):
        # key is e.g. 'SENS:TEMP:RTD:FOUR', the setting is everything after the function
        setting = ":".join(key.split(":")[2:])
        value = args[0]
        channels = self._channels(args[1]) if len(args) > 1 else []
        for channel in channels:
            self.sense[(channel, setting)] = value

    def _trace_make(self, args):
        name = unquote(args[0])
        if name in self.buffers:
            raise SCPIError(1115, f'Parameter error, buffer name "{name}" already exists')
        self.buffers[name] = Buffer(capacity=int(args[1]), fill_mode="ONCE")

    def _trace_points(self, args):
        buffer = self._buffer(args[1] if len(args) > 1 else None)
        buffer.capacity = int(args[0])
        buffer.clear()

    def _trace_fill_mode(self, args):
        buffer = self._buffer(args[1] if len(args) > 1 else None)
        mode = args[0].upper()
        if mode.startswith("CONT"):
            buffer.fill_mode = "CONT"
        elif mode == "ONCE":
            buffer.fill_mode = "ONCE"
        else:
            raise ValueError(f"unknown fill mode {mode}")
        buffer.clear()

    def _trace_actual_start(self, args) -> str:
        return "1" if self._buffer(args[0] if args else None).readings else "0"

    def _trace_data(self, args) -> str:
        start, end = int(args[0]), int(args[1])
        buffer = self._buffer(args[2] if len(args) > 2 else None)
        elements = [short_form(e) for e in args[3:]] or ["READ"]

        if start < 1 or end < start or end > len(buffer.readings):
            raise SCPIError(-222, f"Data out of range;1;TRAC:DATA? {start}, {end}")

        values = []
        for reading in buffer.readings[start - 1 : end]:
            for element in elements:
                if element == "CHAN":
                    values.append(reading.channel)
                elif element == "READ":
                    values.append(f"{reading.value:.6E}")
                elif element == "UNIT":
                    values.append(reading.unit)
                elif element == "SEC":
                    values.append(str(reading.seconds))
                elif element == "FRAC":
                    values.append(f"{reading.fractional:.9f}")
                elif element == "TST":
                    ts = datetime.datetime.fromtimestamp(reading.seconds, tz=datetime.timezone.utc)
                    values.append(f"{ts:%m/%d/%Y %H:%M:%S}.{round(reading.fractional * 1e9):09d}")
                else:
                    raise SCPIError(1133, f"Parameter 4, Syntax error, element {element} not supported by model")
        return ",".join(values)

    def _route_scan_create(self, args):
        self.scan_channels = self._channels(args[0])

    def _route_scan_count(self, args):
        count = int(args[0])
        if count < 0:
            raise ValueError("scan count must be >= 0")
        self.scan_count = count

    def _route_scan_interval(self, args):
        self.scan_interval = float(args[0])

    def _route_scan_buffer(self, args):
        name = unquote(args[0])
        self._buffer(name)
        self.scan_buffer = name

    def _route_scan_start_stimulus(self, args):
        self.scan_start_stimulus = args[0].upper()

    def _initiate(self, args):
        if not self.scan_channels:
            raise SCPIError(-221, "Settings conflict, no scan list defined")
        if self.scan_start_stimulus != "NONE":
            # The scan waits for a trigger event that the model never generates
            self.scan_state = "WAITING"
            return
        self.scan_state = "RUNNING"
        self._scan_start = self.clock()
        self._scans_done = 0

    def _wait_for_scan(self):
        """Blocks until a running scan with a finite scan count has completed, like `*WAI` on the device.

        A scan that repeats until aborted never completes, the device would wait forever. The model returns
        immediately instead.
        """
        if self.scan_state != "RUNNING" or not self.scan_count or self._scan_start is None:
            return
        period = max(self.scan_interval, self.scan_duration)
        end = self._scan_start + (self.scan_count - 1) * period + self.scan_duration
        remaining = end - self.clock()
        if remaining > 0:
            self.sleep(remaining + 1e-6)  # margin for rounding in the scan count calculation
        self._update_scan()

    def _abort(self, args):
        if self.scan_state == "RUNNING":
            self.scan_state = "ABORTED"
        self._scan_start = None


class ModelledDAQ6510(DAQ6510):
    """The asynchronous DAQ6510 driver, talking to a DAQ6510Model instead of a socket.

    All the command formatting and response parsing of the driver is exercised, only the transport is replaced.
    """

    def __init__(self, model: DAQ6510Model | None = None):
        super().__init__(hostname="model", port=5025)
        self.model = model or DAQ6510Model()
        self.fail_next: Exception | None = None
        """Set an exception to be raised by the next write or trans, to test error handling."""
        self.connection_broken = False
        """When True, every write or trans fails until the driver reconnects, like a socket closed by the device."""

    def break_connection(self):
        """Simulates the device closing the connection, e.g. on a power cycle. Only a reconnect recovers from this."""
        self.connection_broken = True

    def _check_failure(self):
        if self.connection_broken:
            raise DeviceConnectionError(self.device_name, "Communication error: [Errno 32] Broken pipe")
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc

    async def connect(self) -> None:
        self._is_connection_open = True
        self.connection_broken = False

    async def disconnect(self) -> None:
        self._is_connection_open = False

    async def is_connected(self) -> bool:
        return self._is_connection_open and not self.connection_broken

    async def write(self, command: str) -> None:
        self._check_failure()
        self.model.process(command.strip())

    async def trans(self, command: str) -> bytes:
        self._check_failure()
        response = self.model.process(command.strip())
        return f"{response or ''}\n".encode()

    async def query(self, command: str) -> bytes:
        return await self.trans(command)
