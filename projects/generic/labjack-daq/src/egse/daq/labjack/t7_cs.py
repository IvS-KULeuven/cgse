import os
import threading
from typing import override

import ljm
from egse.zmq_ser import zmq_json_response
from labjack.ljm.ljm import LJMError

from egse.async_control import AcquisitionAsyncControlServer
from egse.log import egse_logger
from egse.metrics import get_metrics_repo


def _expand(value, num_values: int, label):
    """Accept a scalar or list; return a list of length *num_values*."""
    if isinstance(value, (list, tuple)):
        if len(value) != num_values:
            raise ValueError(f"{label}: expected {num_values} values, got {len(value)}")
        return list(value)
    return [value] * num_values


class T7ControlServer(AcquisitionAsyncControlServer):
    def __init__(self):
        super().__init__()

        self.ain_channels: list[int] = []
        self.scan_rate = 0
        self.resync_interval_s: int = 0
        self.buffer_size: int = 0

        self.voltage_ranges: float | list[float] = 0.0
        self.neg_voltage_ranges: float | list[float] = 0.0
        self.resolution_indices: int | list[int] = 0

        # Derived

        self.neg_channels: float | list[float] = 0.0
        self.channel_names: str | list[str] = ""
        self.num_addresses = 0
        self.scans_per_read: int = 0

        # State

        self._handle = None
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

        # Metrics

        self.metrics_client = None
        self._configure_metrics()

        self._connect_to_device()
        self._configure_device()

    def _configure_metrics(self) -> None:
        # Connection to InfluxDB

        token = os.getenv("INFLUXDB3_AUTH_TOKEN")
        database_name = os.getenv("INFLUXDB3_DATABASE_NAME")

        if database_name and token:
            self.metrics_client = get_metrics_repo(
                "influxdb",
                {
                    "host": "http://localhost:8181",
                    "database": database_name,
                    "token": token,
                },
            )
            self.metrics_client.connect()
        else:
            self.metrics_client = None
            egse_logger.warning(
                "INFLUXDB3_AUTH_TOKEN and/or PROJECT environment variable is not set. "
                "Metrics will not be propagated to InfluxDB."
            )

    def _connect_to_device(self) -> None:
        """Open the LabJack and verify that the detected device is a T7."""
        try:
            self._handle = ljm.openS("T7", "USB", "ANY")
        except LJMError as e:
            raise ValueError(f"Could not connect to T7: {e.errorString}") from None

        info = ljm.getHandleInfo(self._handle)
        if info[0] != ljm.constants.dtT7:
            ljm.close(self._handle)
            raise ValueError("Expected T7 device")

        print(f"Opened LabJack T7  Serial: {info[2]}  IP: {ljm.numberToIP(info[3])}  Port: {info[4]}")

    def _configure_device(self) -> None:
        """Writes per-channel differential and stream-wide configuration."""
        names = []
        values = []

        # Each positive channel is read differentially against the next AIN
        # input. For example AIN0 uses AIN1 as the negative reference.
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
            0,  # free-running
            0,  # internal clock
            0,  # stream-level resolution (per-channel set above)
            0.0,  # auto settling (float < 1)
            0,  # continuous
            self.buffer_size,
        ]

        ljm.eWriteNames(self._handle, len(names), names, values)

        print("Configuration written:")
        for n, v in zip(names, values):
            print(f"    {n} : {v}")

    # @property
    # def actual_scan_rate(self):
    #     return self._actual_scan_rate
    #
    # @property
    # def stream_start_time(self):
    #     return self._stream_start_time

    @override
    def register_custom_handlers(self):
        """Registers command handler, incl. acquisition lifecycle commands."""

        self.add_device_command_handler("start-acquisition", self._do_start_acquisition)
        self.add_device_command_handler("stop-acquisition", self._do_stop_acquisition)
        self.add_device_command_handler("health", self._handle_health)

    async def configure(self):
        # TODO
        pass

    def _is_acquisition_running(self) -> bool:
        return self._streaming

    def custom_callback(self, handle, data, user):
        pass

    async def _do_start_acquisition(self):  # start_stream
        # TODO
        pass

    async def _do_stop_acquisition(self):  # stop_stream
        """Stops the active LabJack stream if one is running."""
        was_running = await self.stop_acquisition()

        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "running": False,
                    "stopped": was_running,
                    # "acquisition logged": self._acquisition_logged_count,
                },
            }
        )

    async def _do_stop_acquisition(self, *args, **kwargs):  # stop_stream
        """Stop acquisition and return status/counter information."""
        was_running = await self.stop_acquisition()
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "running": False,
                    "stopped": was_running,
                    # "acquisition logged": self._acquisition_logged_count,
                },
            }
        )

    async def stop_acquisition(self, *args, **kwargs):  # stop_stream
        """Stops the active LabJack stream if one is running."""

        self._streaming = False

        # noinspection PyBroadException
        try:
            ljm.eStreamStop(self._handle)
        except Exception:
            pass
        print("Stream stopped.")

    async def _handle_health(self, *args, **kwargs):
        """Return a compact health payload for monitoring and tests."""
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "status": "ok",
                    # "echo count": self._echo_count,
                    # "last value": self._last_value,
                    "acquisition running": self._is_acquisition_running(),
                    # "acquisition logged": self._acquisition_logged_count,
                },
            }
        )

    @override
    def stop(self):
        # FIXME Check whether data acquisition is still ongoing

        if self._loop is not None and self._loop.is_running():
            self._loop.create_task(self.stop_acquisition())

        if self._handle is not None:
            ljm.close(self._handle)

        super().stop()
