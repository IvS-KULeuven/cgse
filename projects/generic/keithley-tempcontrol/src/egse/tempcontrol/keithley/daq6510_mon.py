import asyncio
import datetime
import json
import logging
import signal
import time
from asyncio import Task
from pathlib import Path
from typing import Any
from typing import Optional

import zmq
import zmq.asyncio

from egse.device import DeviceConnectionError
from egse.device import DeviceTimeoutError
from egse.tempcontrol.keithley.daq6510_adev import DAQ6510

logger = logging.getLogger("daq6510-mon")


class DAQ6510Monitor:
    """
    DAQ6510 temperature monitoring service with ZeroMQ command interface.

    """

    def __init__(
            self,
            daq_hostname: str,
            daq_port: int = 5025,
            zmq_port: int = 5556,
            log_file: str = "temperature_readings.log",
            channels: list[str] = None,
            poll_interval: float = 60.0
    ):
        """Initialize the DAQ6510 monitoring service.

        Args:
            daq_hostname: Hostname or IP of the DAQ6510
            daq_port: TCP port for DAQ6510 SCPI interface
            zmq_port: Port for ZeroMQ command interface
            log_file: Path to log file for temperature readings
            channels: List of channels to monitor (e.g. ["101", "102"])
            poll_interval: Initial polling interval in seconds
        """
        self.daq_hostname = daq_hostname
        self.daq_port = daq_port
        self.zmq_port = zmq_port
        self.log_file = Path(log_file)
        self.channels = channels or ["101", "102", "103", "104"]
        self.poll_interval = poll_interval

        # Setup ZeroMQ context
        self.ctx = zmq.asyncio.Context()
        self.socket = self.ctx.socket(zmq.ROUTER)
        self.socket.bind(f"tcp://*:{zmq_port}")

        # Service state
        self.running = False
        self.polling_active = False
        self.daq_interface = None
        self.command_handlers = {
            "START_POLLING": self._handle_start_polling,
            "STOP_POLLING": self._handle_stop_polling,
            "SET_INTERVAL": self._handle_set_interval,
            "SET_CHANNELS": self._handle_set_channels,
            "GET_STATUS": self._handle_get_status,
            "GET_READING": self._handle_get_reading,
            "GET_LAST_READING": self._handle_get_last_reading,
            "SHUTDOWN": self._handle_shutdown
        }

        # Keep a record of the last measurement
        self._last_reading: dict = {}

        # Make sure the log directory exists
        self.log_file.parent.mkdir(exist_ok=True, parents=True)

        # Create DAQ interface
        self.daq_interface = DAQ6510(hostname=daq_hostname, port=daq_port)

    async def start(self):
        """Start the monitoring service."""
        logger.info(f"Starting DAQ6510 Monitoring Service on ZMQ port {self.zmq_port}")
        self.running = True

        # Register signal handlers for graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            asyncio.get_event_loop().add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # Start the main service tasks
        await asyncio.gather(
            self.command_listener(),
            self.connect_daq(),
            return_exceptions=True
        )

    def done_polling(self, task: Task):
        if task.exception():
            logger.error(f"Polling loop ended unexpectedly: {task.exception()}")
        logger.info(f"Done polling ({task.get_name()}).")
        self.polling_active = False

    async def connect_daq(self):
        """Establish connection to the DAQ6510."""
        while self.running:
            try:
                logger.info(f"Connecting to DAQ6510 at {self.daq_hostname}:{self.daq_port}")
                await self.daq_interface.connect()
                logger.info("Successfully connected to DAQ6510.")
                await self.daq_interface.initialize()
                logger.info("Successfully initialized DAQ6510 for measurements.")

                # If we were polling before, restart it.
                # The first time we enter this loop, we are not polling.
                if self.polling_active:
                    # QUESTION: Do we need to await here?
                    polling_task = asyncio.create_task(self.polling_loop())

                    # But we can add error handling for the task
                    polling_task.add_done_callback(self.done_polling)

                # Keep checking connection status periodically
                while self.running and await self.daq_interface.is_connected():
                    logger.info("Checking DAQ6510 connection...")
                    await asyncio.sleep(10)

                if self.running:
                    logger.warning("Lost connection to DAQ6510")
                    await self.daq_interface.disconnect()

            except (DeviceConnectionError, DeviceTimeoutError) as exc:
                logger.error(f"Failed to connect to DAQ6510: {exc}")
                await asyncio.sleep(5)  # Wait before retrying

    async def polling_loop(self):
        """Main polling loop for temperature measurements."""
        logger.info(f"Starting temperature polling loop (interval: {self.poll_interval}s, channels: {self.channels})")

        # The next lines are a way to calculate the sleep time between two measurements, this takes the time of the
        # measurement itself into account.
        def interval():
            next_time = time.perf_counter()
            while True:
                next_time += self.poll_interval
                yield max(next_time - time.perf_counter(), 0)

        g_interval = interval()

        while self.running and self.polling_active:

            try:
                if not await self.daq_interface.is_connected():
                    logger.warning("DAQ6510 not connected, skipping temperature reading")
                    await asyncio.sleep(5)
                    continue

                timestamp = datetime.datetime.now().isoformat()
                readings = {}

                # Read temperature from each channel
                for channel in self.channels:
                    try:
                        # temp = random.random()
                        temp = await self.daq_interface.get_measurement(channel)
                        readings[channel] = temp
                    except (DeviceConnectionError, DeviceTimeoutError, ValueError) as exc:
                        logger.error(f"Error reading channel {channel}: {exc}")
                        readings[channel] = None

                # Log the readings
                log_entry = {"timestamp": timestamp, "readings": readings}

                # Append to log file
                with open(self.log_file, "a") as fd:
                    fd.write(json.dumps(log_entry) + "\n")

                self._last_reading.update({"timestamp": timestamp, "readings": readings})

                logger.info(f"Temperature readings: {readings}")

            except Exception as exc:
                logger.exception(f"Error in polling loop: {exc}")

            finally:
                # Wait for next polling interval, we account for the time needed to perform the measurement.
                await asyncio.sleep(next(g_interval))

        logger.info("Temperature polling loop stopped")

    async def command_listener(self):
        """ZeroMQ command interface listener."""
        logger.info("Command listener started")

        while self.running:
            try:
                # Wait for next message
                message = await self.socket.recv_multipart()

                # Parse the message
                if len(message) < 3:
                    logger.warning(f"Received malformed message: {message}")
                    continue

                identity, empty, *payload = message

                try:
                    # Parse the command and parameters
                    command_data = json.loads(payload[0].decode('utf-8'))
                    command = command_data.get("command")
                    params = command_data.get("params", {})

                    logger.info(f"Received command: {command} from {identity}")

                    # Handle the command
                    if command in self.command_handlers:
                        response = await self.command_handlers[command](params)
                    else:
                        response = {"status": "error", "message": f"Unknown command: {command}"}

                except json.JSONDecodeError:
                    response = {"status": "error", "message": "Invalid JSON format"}
                except Exception as exc:
                    logger.exception(f"Error processing command: {exc}")
                    response = {"status": "error", "message": str(exc)}

                # Send response
                await self.socket.send_multipart(
                    [
                        identity,
                        b"",
                        json.dumps(response).encode('utf-8')
                    ]
                )

            except Exception as exc:
                logger.exception(f"Error in command listener: {exc}")
                await asyncio.sleep(1)

    async def _handle_start_polling(self, params: dict[str, Any]) -> dict[str, Any]:
        """Start temperature polling."""
        if not self.polling_active:
            self.polling_active = True

            # If channels provided, update them
            if "channels" in params:
                self.channels = params["channels"]

            # If interval provided, update it
            if "interval" in params:
                self.poll_interval = float(params["interval"])

            # Start polling loop
            polling_task = asyncio.create_task(self.polling_loop())

            # But we can add error handling for the task
            polling_task.add_done_callback(
                lambda t: logger.error(f"Polling loop ended unexpectedly: {t.exception()}")
                if t.exception() else None
            )

            return {
                    "status": "ok",
                    "message": f"Polling started with interval {self.poll_interval}s and channels {self.channels}"
                }
        else:
            return {
                "status": "ok",
                "message": "Polling already active"
            }

    async def _handle_stop_polling(self, params: dict[str, Any]) -> dict[str, Any]:
        """Stop temperature polling."""
        if self.polling_active:
            self.polling_active = False
            return {
                "status": "ok",
                "message": "Polling stopped"
            }
        else:
            return {
                "status": "ok",
                "message": "Polling already stopped"
            }

    async def _handle_set_interval(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set polling interval."""
        if "interval" not in params:
            return {
                "status": "error",
                "message": "Missing required parameter: interval"
            }

        try:
            interval = float(params["interval"])
            if interval <= 0:
                return {
                    "status": "error",
                    "message": "Interval must be positive"
                }

            old_interval = self.poll_interval
            self.poll_interval = interval

            return {
                "status": "ok",
                "message": f"Polling interval changed from {old_interval}s to {interval}s"
            }
        except ValueError:
            return {
                "status": "error",
                "message": "Invalid interval format"
            }

    async def _handle_set_channels(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set channels to monitor."""
        if "channels" not in params or not isinstance(params["channels"], list):
            return {
                "status": "error",
                "message": "Missing or invalid parameter: channels (should be a list)"
            }

        old_channels = self.channels.copy()
        self.channels = params["channels"]

        return {
            "status": "ok",
            "message": f"Monitoring channels changed from {old_channels} to {self.channels}"
        }

    async def _handle_get_last_reading(self, params: dict[str, Any]):
        return self._last_reading

    async def _handle_get_reading(self, params: dict[str, Any]):
        """Get a reading for the given channel(s)."""
        logger.info(f"GET_READING – {params = }")

        readings = {
            'status': "ok",
            'data': {}
        }

        for channel in params['channels']:
            try:
                temp = await self.daq_interface.get_measurement(channel)
                readings['data'][channel] = temp
            except (DeviceConnectionError, DeviceTimeoutError, ValueError, RuntimeError) as exc:
                logger.error(f"Error reading channel {channel}: {exc}")
                readings['data'][channel] = None
                readings.update({'status': "error", "message": f"Error reading channel {channel}"})

        return readings

    async def _handle_get_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get current service status."""
        connected = False
        try:
            if self.daq_interface:
                connected = await self.daq_interface.is_connected()
        except Exception:
            connected = False

        return {
            "status": "ok",
            "data": {
                "service_running": self.running,
                "polling_active": self.polling_active,
                "poll_interval": self.poll_interval,
                "channels": self.channels,
                "daq_connected": connected,
                "daq_hostname": self.daq_hostname,
                "daq_port": self.daq_port
            }
        }

    async def _handle_shutdown(self, params: dict[str, Any]) -> dict[str, Any]:
        """Shutdown the service."""
        # Schedule shutdown after sending response
        _ = asyncio.create_task(self.shutdown())

        return {
            "status": "ok",
            "message": "Service shutting down"
        }

    async def shutdown(self):
        """Gracefully shut down the service."""
        logger.info("Shutting down DAQ Monitoring Service...")

        # Stop the main loops
        self.running = False
        self.polling_active = False

        # Disconnect DAQ
        try:
            logger.info("Disconnecting the DAQ6510...")
            if self.daq_interface and await self.daq_interface.is_connected():
                await self.daq_interface.disconnect()
        except Exception as exc:
            logger.error(f"Error disconnecting from DAQ: {exc}")

        # Close ZeroMQ socket
        try:
            logger.info("Closing ZeroMQ socket and terminate context...")
            self.socket.close()
            self.ctx.term()
        except Exception as exc:
            logger.error(f"Error closing ZeroMQ socket: {exc}")

        logger.info("Service shutdown complete")


class DAQMonitorClient:
    """Simple client for interacting with the DAQ Monitor Service."""

    def __init__(self, server_address: str = "localhost", port: int = 5556, timeout: float = 5.0):
        """Initialize the client.

        Args:
            server_address: Address of the monitoring service
            port: ZeroMQ port
            timeout: Command timeout in seconds
        """
        self.server_address = server_address
        self.port = port
        self.timeout = timeout

        self.ctx = zmq.Context().instance()
        self.socket = None

    def connect(self):
        """Connect to the DAQ Monitoring service."""
        self.socket = self.ctx.socket(zmq.DEALER)
        self.socket.connect(f"tcp://{self.server_address}:{self.port}")
        self.socket.setsockopt(zmq.RCVTIMEO, int(self.timeout * 1000))

    def disconnect(self):
        """Close the client connection."""
        self.socket.close(linger=100)
        self.ctx.term()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        if exc_type:
            logger.error(f"Caught {exc_type}: {exc_val}")

    def _send_command(self, command: str, params: dict[str, Any] = None) -> dict[str, Any]:
        """Send a command to the monitoring service.

        Args:
            command: Command name
            params: Optional command parameters

        Returns:
            Response from the service
        """
        params = params or {}
        message = {"command": command, "params": params}

        try:
            self.socket.send_multipart([b"", json.dumps(message).encode('utf-8')])
            _, response_data = self.socket.recv_multipart()
            return json.loads(response_data.decode('utf-8'))
        except zmq.ZMQError as exc:
            return {"status": "error", "message": f"ZMQ error: {exc}"}
        except Exception as exc:
            return {"status": "error", "message": f"Error: {exc}"}

    def start_polling(self, channels: Optional[list[str]] = None, interval: Optional[float] = None) -> dict[str, Any]:
        """Start polling on specified channels.

        Args:
            channels: List of channels to monitor
            interval: Polling interval in seconds

        Returns:
            Response from the service
        """
        params = {}
        if channels is not None:
            params["channels"] = channels
        if interval is not None:
            params["interval"] = interval

        return self._send_command("START_POLLING", params)

    def stop_polling(self) -> dict[str, Any]:
        """Stop polling.

        Returns:
            Response from the service
        """
        return self._send_command("STOP_POLLING")

    def set_interval(self, interval: float) -> dict[str, Any]:
        """Set polling interval.

        Args:
            interval: New polling interval in seconds

        Returns:
            Response from the service
        """
        return self._send_command("SET_INTERVAL", {"interval": interval})

    def set_channels(self, channels: list[str]) -> dict[str, Any]:
        """Set channels to monitor.

        Args:
            channels: List of channel identifiers

        Returns:
            Response from the service
        """
        return self._send_command("SET_CHANNELS", {"channels": channels})

    def get_reading(self, channels: list[str]) -> dict[str, float]:
        """Get a reading from the given channel.

        Returns:
            A dictionary with the value of the measurement for the given channel.
        """
        return self._send_command("GET_READING", {"channels": channels})

    def get_last_reading(self) -> dict:
        return self._send_command("GET_LAST_READING")

    def get_status(self) -> dict[str, Any]:
        """Get current service status.

        Returns:
            Status information
        """
        return self._send_command("GET_STATUS")

    def shutdown(self) -> dict[str, Any]:
        """Shutdown the service.

        Returns:
            Response from the service
        """
        return self._send_command("SHUTDOWN")



async def main():

    monitor = DAQ6510Monitor(
        daq_hostname="192.168.68.77",
        daq_port=5025,
        zmq_port=5556,
        log_file="temperature_readings.log",
        channels=["101", "102"],
        poll_interval=10.0
    )

    await monitor.start()

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s "
               "%(name)-12s %(lineno)5d:%(module)-20s %(message)s",
    )

    asyncio.run(main())
