"""
Scan configuration for the Keithley DAQ6510.

The configuration is read from the `gse.DAQ6510` section of the Setup. A typical entry looks like this:

```yaml
gse:
    DAQ6510:
        channels: (@101:105)
        sensors:
            PT100:
                temperature:
                    TRANSDUCER: FRTD
                    RTD:
                        FOUR: PT100
                    UNIT: CELSIUS
                    channels: (@101:105)
        route:
            scan:
                INTERVAL: 10
```

The `channels` key defines the channels that are part of the scan, the `sensors` section defines how the channels
are configured, and `route.scan.INTERVAL` is the time between the start of two consecutive scans [s].

The keys in a sensor function (except `channels`) are flattened with a colon and sent as
`SENSe:<FUNCTION>:<KEY> <VALUE>, <channels>`, e.g. `RTD: {FOUR: PT100}` becomes `SENS:TEMPERATURE:RTD:FOUR PT100`.
"""

__all__ = [
    "DEFAULT_BUFFER",
    "DEFAULT_BUFFER_CAPACITY",
    "DEFAULT_SCAN_INTERVAL",
    "ScanConfig",
    "SensorConfig",
    "scan_config_from_setup",
]

from dataclasses import dataclass
from dataclasses import field
from typing import Any

from egse.scpi import get_channel_names
from egse.system import flatten_dict

DEFAULT_BUFFER = "defbuffer1"
DEFAULT_BUFFER_CAPACITY = 100_000
DEFAULT_SCAN_INTERVAL = 10.0


@dataclass(frozen=True)
class SensorConfig:
    """Configuration of one measurement function for a set of channels."""

    function: str
    """The measurement function, e.g. 'TEMPERATURE' or 'VOLTAGE:DC'."""
    channel_list: str
    """The channels this configuration applies to, e.g. '(@101:104)'."""
    settings: list[tuple[str, str]] = field(default_factory=list)
    """Ordered (command, value) pairs, e.g. [('TRANSDUCER', 'FRTD'), ('RTD:FOUR', 'PT100')]."""


@dataclass(frozen=True)
class ScanConfig:
    """Everything needed to configure and run a background scan on the DAQ6510."""

    channel_list: str
    """All channels in the scan, e.g. '(@101:105)'."""
    interval: float = DEFAULT_SCAN_INTERVAL
    """Time between the start of two consecutive scans [s]."""
    sensors: list[SensorConfig] = field(default_factory=list)
    buffer_name: str = DEFAULT_BUFFER
    buffer_capacity: int = DEFAULT_BUFFER_CAPACITY

    def __post_init__(self):
        n_channels = len(self.channel_names)
        if n_channels == 0:
            raise ValueError(f"Invalid channel list for the scan: {self.channel_list!r}")
        if self.interval < 0:
            raise ValueError(f"The scan interval must be >= 0, got {self.interval}")
        if self.buffer_capacity < 2 * n_channels:
            raise ValueError(f"The buffer capacity ({self.buffer_capacity}) must hold at least two scans.")

    @property
    def channel_names(self) -> list[str]:
        return get_channel_names(self.channel_list)


def _get(mapping: Any, key: str, default: Any = None) -> Any:
    """Case-insensitive key lookup, Setups are not consistent in the case of their keys."""
    if mapping is None:
        return default
    for k in mapping:
        if str(k).lower() == key.lower():
            return mapping[k]
    return default


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    return str(value)


def scan_config_from_setup(setup: Any, **overrides: Any) -> ScanConfig:
    """Creates a ScanConfig from the `gse.DAQ6510` section of the given Setup.

    Args:
        setup: the Setup, or any mapping that contains a `gse.DAQ6510` section
        **overrides: ScanConfig fields that take precedence over the Setup, e.g. `buffer_capacity`

    Raises:
        ValueError: when the Setup has no DAQ6510 section or no channels are defined.
    """

    daq = _get(_get(setup, "gse"), "DAQ6510")
    if daq is None:
        raise ValueError("No gse.DAQ6510 section in the Setup.")

    channel_list = _get(daq, "channels")
    if not channel_list:
        raise ValueError("No channels defined in the gse.DAQ6510 section of the Setup.")

    sensors = []
    for sensor in (_get(daq, "sensors") or {}).values():
        for function, settings in sensor.items():
            settings = dict(settings)
            function_channels = _get(settings, "channels", channel_list)
            sensors.append(
                SensorConfig(
                    function=str(function).upper(),
                    channel_list=function_channels,
                    settings=[
                        (key.upper(), _format_value(value))
                        for key, value in flatten_dict(settings).items()
                        if key.lower() != "channels"
                    ],
                )
            )

    interval = _get(_get(_get(daq, "route"), "scan"), "interval", DEFAULT_SCAN_INTERVAL)

    kwargs = {"channel_list": channel_list, "interval": float(interval), "sensors": sensors}
    kwargs.update({k: v for k, v in overrides.items() if v is not None})

    return ScanConfig(**kwargs)
