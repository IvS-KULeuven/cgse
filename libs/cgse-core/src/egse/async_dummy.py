from __future__ import annotations

import asyncio
import logging
import random
import sys
import threading
from typing import Any
from typing import Callable

try:
    from typing import override
except ImportError:
    try:
        from typing_extensions import override
    except ImportError:

        def override(method, /):
            return method


import typer

from egse.async_control import AcquisitionAsyncControlServer
from egse.async_control import TypedAsyncControlClient
from egse.log import logger
from egse.logger import remote_logging
from egse.system import TyperAsyncCommand
from egse.system import do_every
from egse.zmq_ser import zmq_json_response
from egse.zmq_ser import zmq_string_response


class DummyDAQSimulator:
    """Minimal DAQ-like simulator that invokes a callback from a dedicated thread.

    This simulator produces records with a simple sequence number and random value at a configurable interval.
    It can be instantiated and started/stopped multiple times to test acquisition lifecycle management
    in the control server. The acquisition callback is invoked in a try/except block to prevent thread crashes
    from exceptions in the callback, which can help with debugging issues in the control server without
    losing the simulator thread.

    An example use can be found in the `start-acquisition` command handler of `DummyAsyncControlServer`,
    which creates and starts the simulator, and in the `stop_acquisition` method, which stops it.
    """

    def __init__(self, callback: Callable[..., None], interval_s: float):
        """Create a thread-backed producer.

        Args:
            callback: Acquisition callback provided by the control server.
            interval_s: Time between produced records.
        """
        self._callback = callback
        self._interval_s = interval_s
        self._running = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sequence = 0
        self.logger = logging.getLogger("egse.dummy_daq_simulator")

    @property
    def running(self) -> bool:
        """Return True when the simulator thread is alive and acquisition is enabled."""
        return self._running.is_set() and self._thread is not None and self._thread.is_alive()

    def start(self):
        """Start the simulator thread if it is not already running."""
        if self.running:
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dummy-daq-simulator")
        self._thread.start()

    def stop(self):
        """Stop the simulator thread and wait briefly for it to exit."""
        self._running.clear()
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.0)
        self._thread = None

    def _callback_wrapper(self):
        """Invoke the acquisition callback and catch any exceptions to prevent thread crashes.

        This simulates a device driver invoking a callback for each produced record of device information/data.
        The callback is expected to be provided by the control server and can perform any processing or forwarding
        of the produced record. Wrapping the callback in a try/except block allows us to log any exceptions that
        occur without crashing the simulator thread, which can help with debugging issues in the control server's
        acquisition handling.

        The callback is expected to accept at least one argument which can be anything, but in this case we provide a
        dictionary with a sequence number and random value to simulate produced records of device data.
        The callback can also accept additional keyword arguments for metadata, source, etc. if desired.
        """
        try:
            self._sequence += 1
            self._callback(
                {
                    "sequence": self._sequence,
                    "value": random.random(),
                },
                source="dummy-acquisition",
                metadata={"interval": self._interval_s, "origin": "dummy-daq-simulator"},
            )
        except Exception as exc:
            # Log exceptions from the callback to help debug issues without crashing the thread
            self.logger.error(f"Exception in DummyDAQSimulator callback: {type(exc).__name__}: {exc}")

    def _run(self):
        do_every(self._interval_s, self._callback_wrapper, stop_event=self._stop)


class DummyAsyncControlServer(AcquisitionAsyncControlServer):
    """Example async control server showing what belongs in a subclass.

    The superclass handles sockets, request/response framing, registration, lifecycle,
    task management, and common service commands. This subclass only defines
    device-specific commands and extra service metadata.
    """

    service_type = "dummy-async-control-server"

    def __init__(self):
        self._last_value: str | None = None
        self._echo_count = 0
        self._acquisition_logged_count = 0
        self._acquisition_interval_s = 0.05
        self._daq_simulator: DummyDAQSimulator | None = None
        super().__init__()

    @override
    def register_custom_handlers(self):
        """Register dummy command handlers, including acquisition lifecycle commands."""
        self.add_device_command_handler("echo", self._do_echo)
        self.add_device_command_handler("set-value", self._do_set_value)
        self.add_device_command_handler("start-acquisition", self._do_start_acquisition)
        self.add_device_command_handler("stop-acquisition", self._do_stop_acquisition)
        self.add_service_command_handler("health", self._handle_health)

    @override
    def get_service_info(self) -> dict[str, Any]:
        """Return service metadata, including acquisition state and counters."""
        info = super().get_service_info()
        info.update(
            {
                "supports": [
                    "echo",
                    "set-value",
                    "start-acquisition",
                    "stop-acquisition",
                    "health",
                    "ping",
                    "info",
                    "terminate",
                ],
                "echo count": self._echo_count,
                "last value": self._last_value,
                "acquisition running": self._is_acquisition_running(),
                "acquisition logged": self._acquisition_logged_count,
                "acquisition interval": self._acquisition_interval_s,
            }
        )
        return info

    async def _do_echo(self, cmd: dict[str, Any]) -> list:
        """Echo the provided message and increment a call counter."""
        payload = str(cmd.get("message", ""))
        self._echo_count += 1
        return zmq_string_response(payload)

    async def _do_set_value(self, cmd: dict[str, Any]) -> list:
        """Store a value in memory so tests can verify device state transitions."""
        self._last_value = str(cmd.get("value", ""))
        return zmq_json_response({"success": True, "message": {"stored": self._last_value}})

    def _is_acquisition_running(self) -> bool:
        """Return True when the DAQ simulator is actively producing samples."""
        return self._daq_simulator is not None and self._daq_simulator.running

    def custom_callback(self, data, *args, **kwargs):
        # Do some custom processing of the device driver record here, this might be to extract data from the record, but
        # the 'record' might also be a handle to a device driver object that can be queried for more information, or it
        # could be any other data structure depending on how the acquisition callback is invoked by the device
        # driver/simulator. In this example, we just log the record sequence and value for demonstration purposes,
        # but in a real control server this is where you would implement the logic to handle incoming acquisition
        # records, such as parsing the data, applying calibrations, checking for alerts, forwarding to other services,
        # etc.

        # The DummyDAQSimulator provides a dictionary as the record, but this could be any data structure.
        record = data
        logger.debug(f"Custom processing of record {record.get('sequence')} with value {record.get('value')}")

        # Then pass it to the default callback for further processing and finally enqueuing in the acquisition queue.
        self.on_acquisition_data(record, source="custom", metadata={"processed": True})

    async def _do_start_acquisition(self, cmd: dict[str, Any]) -> list:
        """Start the DAQ simulator and stream samples through the acquisition callback."""
        interval_s = float(cmd.get("interval", self._acquisition_interval_s))
        if interval_s <= 0:
            return zmq_json_response(
                {
                    "success": False,
                    "message": {"error": "interval must be > 0"},
                }
            )

        self._acquisition_interval_s = interval_s

        # Don't start a new simulator if one is already running, but return success with the current state
        if self._is_acquisition_running():
            return zmq_json_response(
                {
                    "success": True,
                    "message": {
                        "running": True,
                        "interval": self._acquisition_interval_s,
                        "already_running": True,
                    },
                }
            )

        # This will return the default acquisition callback function that is defined in the superclass.
        # The default callback expects one positional argument for the acquisition record, which can be any data
        # structure but in this case we provide a dictionary with a sequence number and random value to simulate
        # produced records of device data. The default callback also accept optional keyword arguments,
        # in this case, 'source' and 'metadata' are provided.

        callback = self.get_acquisition_callback()

        # Alternatively, you could also define a custom callback function here in the control server subclass that
        # performs additional processing or forwarding of the produced records, and pass that to the device
        # acquisition method instead of the default callback from the superclass.
        # For example:

        # callback = self.custom_callback

        # The DummyDAQSimulator runs in a separate thread and invokes the callback for each produced record.
        self._daq_simulator = DummyDAQSimulator(callback=callback, interval_s=self._acquisition_interval_s)
        self._daq_simulator.start()

        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "running": True,
                    "interval": self._acquisition_interval_s,
                    "already_running": False,
                },
            }
        )

    async def _do_stop_acquisition(self, cmd: dict[str, Any]) -> list:
        """Stop acquisition and return status/counter information."""
        was_running = await self.stop_acquisition()
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "running": False,
                    "stopped": was_running,
                    "acquisition logged": self._acquisition_logged_count,
                },
            }
        )

    async def stop_acquisition(self) -> bool:
        """Stop the simulator thread without blocking the event loop.

        Returns:
            True if acquisition was running and has been stopped, otherwise False.
        """
        simulator = self._daq_simulator
        if simulator is None:
            return False

        self._daq_simulator = None
        await asyncio.to_thread(simulator.stop)
        return True

    @override
    async def handle_acquisition_record(self, record: dict[str, Any]):
        """Receive one processed acquisition record and log it."""
        self._acquisition_logged_count += 1
        self.logger.info(f"Dummy acquisition record {self._acquisition_logged_count}: {record.get('data')}")

    async def _handle_health(self, cmd: dict[str, Any]) -> list:
        """Return a compact health payload for monitoring and tests."""
        return zmq_json_response(
            {
                "success": True,
                "message": {
                    "status": "ok",
                    "echo count": self._echo_count,
                    "last value": self._last_value,
                    "acquisition running": self._is_acquisition_running(),
                    "acquisition logged": self._acquisition_logged_count,
                },
            }
        )

    @override
    def stop(self):
        """Stop acquisition first, then stop the base server lifecycle."""
        if self._is_acquisition_running():
            if self._loop is not None and self._loop.is_running():
                self._loop.create_task(self.stop_acquisition())
            elif self._daq_simulator is not None:
                self._daq_simulator.stop()
                self._daq_simulator = None
        super().stop()


class DummyAsyncControlClient(TypedAsyncControlClient):
    """Example client wrapper with strongly named methods for dummy commands."""

    service_type = DummyAsyncControlServer.service_type

    async def echo(self, message: str, timeout: float | None = None) -> str | None:
        """Send an `echo` device command and return the echoed message."""
        response = await self.send_device_command({"command": "echo", "message": message}, timeout=timeout)
        return self._success_message_as_str(response, "echo")

    async def set_value(self, value: str, timeout: float | None = None) -> str | None:
        """Send `set-value` and return the stored value from the device response."""
        response = await self.send_device_command({"command": "set-value", "value": value}, timeout=timeout)
        message = self._success_message_as_dict(response, "set-value")
        if message is None:
            return None
        return str(message.get("stored"))

    async def health(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Return the dummy server health payload."""
        response = await self.send_service_command("health", timeout=timeout)
        return self._success_message_as_dict(response, "health")

    async def start_acquisition(self, interval: float = 0.05, timeout: float | None = None) -> dict[str, Any] | None:
        """Start simulator-backed acquisition with the requested sample interval."""
        response = await self.send_device_command(
            {"command": "start-acquisition", "interval": interval},
            timeout=timeout,
        )
        return self._success_message_as_dict(response, "start-acquisition")

    async def stop_acquisition(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Stop simulator-backed acquisition and return final acquisition status."""
        response = await self.send_device_command({"command": "stop-acquisition"}, timeout=timeout)
        return self._success_message_as_dict(response, "stop-acquisition")


app = typer.Typer()


@app.command(cls=TyperAsyncCommand)
async def start_cs():
    """Start the dummy async control server on localhost."""

    with remote_logging():
        try:
            control_server = DummyAsyncControlServer()
            await control_server.start()
        except KeyboardInterrupt:
            print("Shutdown requested...exiting")
        except SystemExit as exit_code:
            print(f"System Exit with code {exit_code}.")
            sys.exit(-1)
        except Exception:  # noqa
            import traceback

            traceback.print_exc(file=sys.stdout)


@app.command(cls=TyperAsyncCommand)
async def stop_cs():
    """Send a quit service command to the dummy async control server."""
    async with DummyAsyncControlClient() as dummy:
        logger.info("Sending a stop_server() to the async dummy control server.")
        await dummy.stop_server()


if __name__ == "__main__":
    app()
