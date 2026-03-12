import datetime
import threading
from typing import Callable

from labjack import ljm
from labjack.ljm.ljm import LJMError

from egse.daq.labjack import CS_SETTINGS, PROXY_TIMEOUT
from egse.daq.labjack.t7_devif import T7UsbInterface
from egse.device import DeviceInterface
from egse.mixin import DynamicCommandMixin
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address


def get_all_usb_t7() -> None:
    """Lists all LabJack T7 devices that are accessible via USB."""

    num_devices, device_types, connection_types, serials, ips = ljm.listAll(
        ljm.constants.dtT7,  # Only T7 devices
        ljm.constants.ctUSB,  # Only USB connections
    )

    print(f"Found {num_devices} LabJack T7 device(s) over USB.\n")

    for i in range(num_devices):
        print(f"LabJack T7 #{i}:")
        print("  Device type :", device_types[i])
        print("  Connection  :", connection_types[i])
        print("  Serial      :", serials[i])
        print("  IP address  :", ljm.numberToIP(ips[i]))  # USB devices return 0.0.0.0


def get_all_ethernet_t7() -> None:
    """Lists all LabJack T7 devices that are accessible via Ethernet"""

    num, device_types, connection_types, serials, ips = ljm.listAll(
        ljm.constants.dtT7,  # Only T7 devices
        ljm.constants.ctETHERNET,  # Only Ethernet connections
    )

    print(f"Found {num} T7 device(s) over Ethernet.\n")

    for i in range(num):
        print(f"T7 #{i}:")
        print("  Device type :", device_types[i])
        print("  Connection  :", connection_types[i])
        print("  Serial      :", serials[i])
        print("  IP address  :", ljm.numberToIP(ips[i]))

class T7Interface(DeviceInterface):

    def __init__(self, device_id: str):
        """Initialisation of an LabJack T7 interface.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__()

        self.device_id = device_id

    def configure(self, ain_channels: list[int],
                  scan_rate: float = 496,
                  voltage_range: float | list[float] = 0.1,
                  neg_voltage_range: float | list[float] = 10.0,
                  resolution_index: int | list[int] = 0,
                  resync_interval_s: int = 60,
                  buffer_size: int = 32768) -> None:

        raise NotImplementedError

    def start_stream(self, callback: Callable):
        raise NotImplementedError

    def stop_stream(self):
        raise NotImplementedError

class T7Controller(T7Interface, DynamicCommandMixin):

    def __init__(self, device_id: str):

        super().__init__(device_id)

        self.transport = self.t7 = T7UsbInterface(device_id=device_id) # FIXME Offer the choice here USB/Ethernet?

        self.ain_channels: list[int] = []
        self.scan_rate = 0
        self.resync_interval_s: int = 0
        self.buffer_size: int = 0

        self.voltage_ranges: float | list[float] = 0.
        self.neg_voltage_ranges: float | list[float] = 0.
        self.resolution_indices: int | list[int] = 0

        # Derived
        self.neg_channels: float | list[float] = 0.
        self.channel_names: str | list[str] = ""
        self.num_addresses = 0
        self.scans_per_read: int = 0

        # State
        self._actual_scan_rate = None
        self._callback = None
        self._lock = threading.Lock()
        self._streaming = False

        # Timestamp tracking
        self._t_anchor = None
        self._stream_start_time = None
        self._anchor_scan_count = 0
        self._scan_index = 0
        self._resync_interval_scans: int = 0

    # noinspection PyMethodMayBeStatic
    def is_simulator(self):

        return False

    def is_connected(self) -> bool:

        return self.t7.is_connected()

    def connect(self):

        self.t7.connect()

    def disconnect(self):

        self.t7.disconnect()

    def reconnect(self):

        self.t7.reconnect()

    @property
    def actual_scan_rate(self):
        return self._actual_scan_rate

    @property
    def stream_start_time(self):
        return self._stream_start_time

    @staticmethod
    def _expand(value, n, label):
        """Accept a scalar or list; return a list of length *n*."""
        if isinstance(value, (list, tuple)):
            if len(value) != n:
                raise ValueError(
                    f"{label}: expected {n} values, got {len(value)}"
                )
            return list(value)
        return [value] * n

    def configure(self, ain_channels: list[int],
        scan_rate: float = 496,
        voltage_range: float | list[float] = 0.1,
        neg_voltage_range: float | list[float] = 10.0,
        resolution_index: int | list[int] = 0,
        resync_interval_s: int = 60,
        buffer_size: int = 32768) -> None:
        """


        Args:
            ain_channels (list[int]): Positive AIN channel numbers
            scan_rate (float): Scan rate [Hz].
            voltage_range (float | list[float]): Voltage range for positive AIN channels.  Either a single value for
                                                 all channels or a list with one value per channel.
            neg_voltage_range (float | list[float]): Voltage range for negative reference channels.  Either a single
                                                     value for all channels or a list with one value per channel.
            resolution_index (int | list[int]): Stream resolution index.  Either a single value for all channels or
                                                a list with one value per channel.  Zero mean auto.
            resync_interval_s (int): Time between host-clock re-anchor points to limit drift [s].
            buffer_size (int): Stream buffer size [bytes].
        """

        self.resync_interval_s = resync_interval_s
        self.buffer_size = buffer_size

        n = len(ain_channels)
        self.voltage_ranges = self._expand(voltage_range, n, "voltage_range")
        self.neg_voltage_ranges = self._expand(neg_voltage_range, n, "neg_voltage_range")
        self.resolution_indices = self._expand(resolution_index, n, "resolution_index")

        # Derived
        self.neg_channels = [ch + 1 for ch in ain_channels]
        self.channel_names = [f"AIN{ch}" for ch in ain_channels]
        self.num_addresses = n
        self.scans_per_read = int(scan_rate / 2)

        # State
        self._actual_scan_rate = None
        self._callback = None
        self._lock = threading.Lock()
        self._streaming = False

        # Timestamp tracking
        self._t_anchor = None
        self._stream_start_time = None
        self._anchor_scan_count = 0
        self._scan_index = 0
        self._resync_interval_scans = int(scan_rate * resync_interval_s)

        ###

        names = []
        values = []

        for ch, neg_ch in zip(self.ain_channels, self.neg_channels):
            names.append(f"AIN{ch}_NEGATIVE_CH")
            values.append(neg_ch)

        for ch, vr in zip(self.ain_channels, self.voltage_ranges):
            names.append(f"AIN{ch}_RANGE")
            values.append(vr)

        for neg_ch, nvr in zip(self.neg_channels, self.neg_voltage_ranges):
            names.append(f"AIN{neg_ch}_RANGE")
            values.append(nvr)

        for ch, ri in zip(self.ain_channels, self.resolution_indices):
            names.append(f"AIN{ch}_RESOLUTION_INDEX")
            values.append(ri)

        names += [
            "STREAM_TRIGGER_INDEX",
            "STREAM_CLOCK_SOURCE",
            "STREAM_RESOLUTION_INDEX",
            "STREAM_SETTLING_US",
            "STREAM_NUM_SCANS",
            "STREAM_BUFFER_SIZE_BYTES",
        ]
        values += [
            0,                        # free-running
            0,                        # internal clock
            0,                        # stream-level resolution (per-channel set above)
            0.0,                      # auto settling (float < 1)
            0,                        # continuous
            self.buffer_size,
        ]

        ljm.eWriteNames(self._handle, len(names), names, values)

        print("Configuration written:")
        for n, v in zip(names, values):
            print(f"    {n} : {v}")

    def _stream_callback(self, handle):
        if handle != self.t7.handle or not self._streaming:
            return

        try:
            ret = ljm.eStreamRead(handle)
        except LJMError as err:
            if err.errorCode == ljm.errorcodes.STREAM_NOT_RUNNING:
                return
            raise

        raw_data = ret[0]
        device_backlog = ret[1]
        ljm_backlog = ret[2]

        timestamps = []
        readings = []

        with self._lock:
            for i in range(0, len(raw_data), self.num_addresses):
                scans_since_anchor = self._scan_index - self._anchor_scan_count
                elapsed = datetime.timedelta(
                    seconds=scans_since_anchor / self._actual_scan_rate
                )
                scan_time = self._t_anchor + elapsed

                timestamps.append(scan_time)
                readings.append(raw_data[i: i + self.num_addresses])
                self._scan_index += 1

            # Re-anchor between batches
            if (self._scan_index - self._anchor_scan_count) >= self._resync_interval_scans:
                self._t_anchor = datetime.datetime.now()
                self._anchor_scan_count = self._scan_index
                print(f"[Re-anchored host clock at scan {self._scan_index}]")

        if self._callback:
            self._callback(
                timestamps=timestamps,
                readings=readings,
                channel_names=self.channel_names,
                device_backlog=device_backlog,
                ljm_backlog=ljm_backlog,
            )

    def start_stream(self, callback: Callable):
        self._callback = callback

        scan_list = ljm.namesToAddresses(self.num_addresses, self.channel_names)[0]
        self._actual_scan_rate = ljm.eStreamStart(
            self.t7.handle, self.scans_per_read, self.num_addresses,
            scan_list, self.scan_rate,
        )

        self._t_anchor = datetime.datetime.now()
        self._stream_start_time = self._t_anchor
        self._anchor_scan_count = 0
        self._scan_index = 0
        self._streaming = True

        ljm.setStreamCallback(self._handle, self._stream_callback)

        print(
            f"Stream started at {self._actual_scan_rate:.1f} Hz  "
            f"({self.scans_per_read} scans/read, "
            f"re-anchor every {self._resync_interval_scans} scans)"
        )

    def stop_stream(self):
        self._streaming = False
        try:
            ljm.eStreamStop(self._handle)
        except Exception:
            pass
        print("Stream stopped.")


class T7Simulator(T7Interface):

    def __init__(self, device_id: str):

        super().__init__(device_id)

        self._is_connected = True

    # noinspection PyMethodMayBeStatic
    def is_simulator(self):
        return True

    def is_connected(self):
        return self._is_connected

    def connect(self):
        self._is_connected = True

    def disconnect(self):
        self._is_connected = False

    def reconnect(self):
        self._is_connected = True

class T7Proxy(DynamicProxy, T7Interface):

    def __init__(self, device_id: str):

        hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")
        protocol = CS_SETTINGS[device_id].get("PROTOCOL", "tcp")
        commanding_port = CS_SETTINGS[device_id].get("COMMANDING_PORT", 0)
        service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "tgf4000_cs")

        # Fixed ports -> Use information from settings

        if commanding_port != 0:
            super().__init__(connect_address(protocol, hostname, commanding_port))

        # Dynamic port allocation -> Use Registry Client

        else:
            with RegistryClient() as reg:
                service = reg.discover_service(service_type)

                if service:
                    protocol = service.get("protocol", "tcp")
                    hostname = service["host"]
                    port = service["port"]

                    super().__init__(connect_address(protocol, hostname, port), timeout=PROXY_TIMEOUT)

                else:
                    raise RuntimeError(f"No service registered as {service_type}")

        self.device_id = device_id
