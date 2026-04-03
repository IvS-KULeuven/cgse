from __future__ import annotations

import asyncio
import datetime
import json
import pickle
import uuid
from asyncio import Event
from asyncio import Task
from enum import Enum
from enum import auto
from typing import Any
from typing import Callable
from typing import Coroutine

import zmq.asyncio
from rich.traceback import Traceback

from egse.env import bool_env
from egse.exceptions import InitializationError
from egse.log import logging

# from egse.process import ProcessStatus
from egse.registry.client import AsyncRegistryClient
from egse.system import Periodic
from egse.system import get_current_location
from egse.system import get_host_ip
from egse.system import humanize_seconds
from egse.system import log_rich_output
from egse.system import type_name
from egse.zmq_ser import get_port_number
from egse.zmq_ser import set_address_port
from egse.zmq_ser import zmq_error_response
from egse.zmq_ser import zmq_json_request
from egse.zmq_ser import zmq_json_response
from egse.zmq_ser import zmq_string_request
from egse.zmq_ser import zmq_string_response

logger = logging.getLogger("egse.async_control")

# When zero (0) ports will be dynamically allocated by the system
CONTROL_SERVER_DEVICE_COMMANDING_PORT = 0
CONTROL_SERVER_SERVICE_COMMANDING_PORT = 0

CONTROL_SERVER_SERVICE_TYPE = "async-control-server"
CONTROL_CLIENT_ID = "async-control-client"

VERBOSE_DEBUG: bool = bool_env("VERBOSE_DEBUG")

RECREATE_SOCKET = False
"""Recreate ZeroMQ socket after a timeout. Set to True when experiencing problems
with corrupted socket states. This is mainly used for REQ-REP protocols."""


class SocketType(Enum):
    """The socket type defines which socket to use for the intended communication."""

    DEVICE = auto()
    SERVICE = auto()


async def is_control_server_active(service_type: str, timeout: float = 0.5) -> bool:
    """
    Checks if the Control Server is running.

    This function sends a *Ping* message to the Control Server and expects a *Pong* answer back within the timeout
    period.

    Args:
        service_type (str): the service type of the control server to check
        timeout (float): Timeout when waiting for a reply [s, default=0.5]

    Returns:
        True if the Control Server is running and replied with the expected answer; False otherwise.
    """

    # I have a choice here to check if the control server is active/healthy.
    #
    # 1. I can connect to the ServiceRegistry, and analyse the 'health' field if it is 'passing', or

    async with AsyncRegistryClient() as registry:
        service = await registry.discover_service(service_type)
    if service:
        return True if service["health"] == "passing" else False
    else:
        return False

    # 2. I can connect to the control server (by first contacting the service registry) and send a ping.

    # try:
    #     async with AsyncControlClient(service_type=service_type) as client:
    #         response = await client.ping()
    #     return response == "pong"
    # except InitializationError:
    #     return False


class AsyncControlServer:
    service_type = CONTROL_SERVER_SERVICE_TYPE

    def __init__(self):
        self.interrupted: Event = asyncio.Event()
        self.logger = logging.getLogger("egse.async_control.server")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._start_time = datetime.datetime.now()

        self.mon_delay = 1000
        """Delay between publish status information [ms]."""
        self.hk_delay = 1000
        """Delay between saving housekeeping information [ms]."""

        # self._process_status = ProcessStatus()

        self._service_id = None

        self._sequential_queue: asyncio.Queue[Coroutine[Any, Any, Any]] = asyncio.Queue()
        """Queue for sequential operations that must preserve order of execution."""

        self.device_command_port = CONTROL_SERVER_DEVICE_COMMANDING_PORT
        """The device commanding port for the control server. This will be 0 at start and dynamically assigned by the
        system."""

        self.service_command_port = CONTROL_SERVER_SERVICE_COMMANDING_PORT
        """The service commanding port for the control server. This will be 0 at start and dynamically assigned by the
        system."""

        self.device_command_handlers: dict[str, Callable] = {}
        """Dictionary mapping device command names to their handler functions."""

        self.service_command_handlers: dict[str, Callable] = {}
        """Dictionary mapping service command names to their handler functions."""

        self._tasks: list[Task] = []
        """The background top-level tasks that are performed by the control server."""

        self._ctx = zmq.asyncio.Context.instance()

        # Socket to handle device commanding pattern - ROUTER-DEALER
        self.device_command_socket: zmq.asyncio.Socket = self._ctx.socket(zmq.ROUTER)

        # Socket to handle service commanding pattern - ROUTER-DEALER
        self.service_command_socket: zmq.asyncio.Socket = self._ctx.socket(zmq.ROUTER)

        self.register_default_device_command_handlers()
        self.register_default_service_command_handlers()

        # Call the hook for registering custom handlers, so that they are registered before the server
        # starts accepting commands.
        self.register_custom_handlers()

        self.registry = AsyncRegistryClient()

    def register_default_device_command_handlers(self):
        """Register baseline device handlers that are useful for diagnostics and examples."""
        self.add_device_command_handler("block", self._do_block)
        self.add_device_command_handler("say", self._do_say)

    def register_default_service_command_handlers(self):
        """Register baseline service handlers for lifecycle and health checks."""
        self.add_service_command_handler("terminate", self._handle_terminate)
        self.add_service_command_handler("info", self._handle_info)
        self.add_service_command_handler("ping", self._handle_ping)
        self.add_service_command_handler("block", self._handle_block)

    def register_custom_handlers(self):
        """Hook for subclasses to register device-specific command handlers."""

    def get_service_info(self) -> dict[str, Any]:
        """Service info payload returned by the `info` service command."""
        return {
            "name": type(self).__name__,
            "hostname": self.get_ip_address(),
            "device commanding port": self.device_command_port,
            "service commanding port": self.service_command_port,
            "service type": self.service_type,
            "uptime": humanize_seconds(
                (datetime.datetime.now() - self._start_time).total_seconds(), include_micro_seconds=False
            ),
        }

    @staticmethod
    def get_ip_address() -> str:
        """Returns the IP address of the current host or localhost."""
        return get_host_ip() or "localhost"

    def connect_device_command_socket(self):
        self.device_command_socket.bind(f"tcp://*:{self.device_command_port}")
        self.device_command_port = get_port_number(self.device_command_socket)

    def connect_service_command_socket(self):
        self.service_command_socket.bind(f"tcp://*:{self.service_command_port}")
        self.service_command_port = get_port_number(self.service_command_socket)

    def stop(self):
        self.logger.warning(f"Stopping the async control server {type(self).__name__}.")
        self.interrupted.set()

    async def start(self):
        self._loop = asyncio.get_running_loop()

        self.connect_device_command_socket()
        self.connect_service_command_socket()

        await self.register_service()

        self._tasks = self._create_background_tasks()

        try:
            while not self.interrupted.is_set():
                await self._check_tasks_health()
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            self.logger.debug(f"Caught CancelledError on server keep-alive loop, terminating {type(self).__name__}.")
        finally:
            await self._cleanup_running_tasks()

        await self.deregister_service()

        self.disconnect_device_command_socket()
        self.disconnect_service_command_socket()

    def _create_background_tasks(self) -> list[Task]:
        """Create top-level server tasks.

        Subclasses can override this method and append extra tasks while keeping
        the base command/service lifecycle unchanged.
        """
        return [
            asyncio.create_task(self.process_device_command(), name="process-device-commands"),
            asyncio.create_task(self.process_service_command(), name="process-service-commands"),
            asyncio.create_task(self.send_status_updates(), name="send-status-updates"),
            asyncio.create_task(self.process_sequential_queue(), name="process-sequential-queue"),
        ]

    async def register_service(self):
        self.logger.info(f"Registering service {type(self).__name__} as type {self.service_type}")

        await self.registry.connect()

        self._service_id = await self.registry.register(
            name=type_name(self),
            host=get_host_ip() or "127.0.0.1",
            port=get_port_number(self.device_command_socket),
            service_type=self.service_type,
            metadata={"service_port": get_port_number(self.service_command_socket)},
        )
        await self.registry.start_heartbeat()

    async def deregister_service(self):
        await self.registry.stop_heartbeat()
        await self.registry.deregister()

        await self.registry.disconnect()

    async def _check_tasks_health(self):
        """Check if any tasks unexpectedly terminated."""
        for task in self._tasks:
            if task.done() and not task.cancelled():
                try:
                    # This will raise any exception that occurred in the task
                    task.result()
                except Exception as exc:
                    self.logger.error(f"Task {task.get_name()} failed: {exc}", exc_info=True)
                    # Potentially restart the task or shut down service

    async def _cleanup_running_tasks(self):
        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                self.logger.debug(f"Cancelling task {task.get_name()}.")
                task.cancel()

        # Wait for tasks to complete their cancellation
        if self._tasks:
            try:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            except asyncio.CancelledError as exc:
                self.logger.debug(f"Caught {type_name(exc)}: {exc}.")
                pass

    def disconnect_device_command_socket(self):
        self.logger.debug("Cleaning up device command sockets.")
        if self.device_command_socket:
            self.device_command_socket.close(linger=100)

    def disconnect_service_command_socket(self):
        self.logger.debug("Cleaning up service command sockets.")
        if self.service_command_socket:
            self.service_command_socket.close(linger=100)

    async def process_device_command(self):
        self.logger.info("Starting device command processing ...")

        while not self.interrupted.is_set():
            try:
                # Wait for a request with timeout to allow checking if still running
                try:
                    parts = await asyncio.wait_for(self.device_command_socket.recv_multipart(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if VERBOSE_DEBUG:
                    self.logger.debug(f"Received multipart message: {parts}")

                # For commanding, we only accept simple commands as a string or a complex command with arguments as
                # JSON data. In both cases, there are only three parts in this multipart message.
                client_id, sequence_id, message_type, data = parts
                if message_type == b"MESSAGE_TYPE:STRING":
                    device_command = {"command": data.decode("utf-8")}
                elif message_type == b"MESSAGE_TYPE:JSON":
                    device_command = json.loads(data.decode())
                else:
                    filename, lineno, function_name = get_current_location()
                    # We have an unknown message format, send an error message back
                    message = zmq_error_response(
                        {
                            "success": False,
                            "message": f"Incorrect message type: {message_type}",
                            "metadata": {
                                "data": data.decode(),
                                "file": filename,
                                "lineno": lineno,
                                "function": function_name,
                            },
                        }
                    )
                    await self.device_command_socket.send_multipart([client_id, sequence_id, *message])
                    continue

                self.logger.debug(f"Received device command: {device_command}")

                self.logger.debug("Process the command...")
                response = await self._process_device_command(device_command)

                self.logger.debug("Send the response...")
                await self.device_command_socket.send_multipart([client_id, sequence_id, *response])

            except asyncio.CancelledError:
                self.logger.debug("Device command handling task cancelled.")
                break

    async def _process_device_command(self, cmd: dict[str, Any]) -> list:
        command = cmd.get("command")
        if not command:
            return zmq_error_response(
                {
                    "success": False,
                    "message": "no command field provide, don't know what to do.",
                }
            )

        handler = self.device_command_handlers.get(command)
        if not handler:
            filename, lineno, function_name = get_current_location()
            return zmq_error_response(
                {
                    "success": False,
                    "message": f"Unknown command: {command}",
                    "metadata": {"file": filename, "lineno": lineno, "function": function_name},
                }
            )

        return await handler(cmd)

    def add_device_command_handler(self, command_name: str, command_handler: Callable):
        self.device_command_handlers[command_name] = command_handler

    def add_service_command_handler(self, command_name: str, command_handler: Callable):
        self.service_command_handlers[command_name] = command_handler

    async def _do_say(self, cmd: dict[str, Any]) -> list:
        self.logger.debug(f"Executing command: '{cmd['command']}")
        self.logger.debug(f"Message: {cmd['message']}")
        return zmq_string_response(f"Message said: {cmd['message']}")

    async def _do_block(self, cmd: dict[str, Any]) -> list:
        self.logger.debug(f"Blocking the commanding for {cmd['sleep']}s...")
        await asyncio.sleep(cmd["sleep"])
        self.logger.debug(f"Blocking finished after {cmd['sleep']}s.")
        return zmq_string_response("block: ACK")

    async def _handle_block(self, cmd: dict[str, Any]) -> list:
        self.logger.debug(f"Handling '{cmd['command']}' service request.")
        await asyncio.sleep(cmd["sleep"])
        self.logger.debug(f"Blocking finished after {cmd['sleep']}s.")
        return zmq_string_response("block: ACK")

    async def _handle_ping(self, cmd: dict[str, Any]) -> list:
        self.logger.debug(f"Handling '{cmd['command']}' service request.")
        return zmq_string_response("pong")

    async def _handle_info(self, cmd: dict[str, Any]) -> list:
        self.logger.debug(f"Handling '{cmd['command']}' service request.")
        return zmq_json_response(
            {
                "success": True,
                "message": self.get_service_info(),
            }
        )

    async def _handle_terminate(self, cmd: dict[str, Any]) -> list:
        self.logger.debug(f"Handling '{cmd['command']}' request.")

        self.stop()

        return zmq_json_response(
            {
                "success": True,
                "message": {"status": "terminating"},
            }
        )

    async def process_service_command(self):
        self.logger.info("Starting service command processing ...")

        while not self.interrupted.is_set():
            try:
                # Wait for a request with timeout to allow checking if still running
                try:
                    parts = await asyncio.wait_for(self.service_command_socket.recv_multipart(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if VERBOSE_DEBUG:
                    self.logger.debug(f"{parts=}")

                # For commanding, we only accept simple commands as a string or a complex command with arguments as
                # JSON data. In both cases, there are only three parts in this multipart message.
                client_id, sequence_id, message_type, data = parts
                if message_type == b"MESSAGE_TYPE:STRING":
                    service_command = {"command": data.decode("utf-8")}
                elif message_type == b"MESSAGE_TYPE:JSON":
                    service_command = json.loads(data.decode())
                else:
                    filename, lineno, function_name = get_current_location()
                    # We have an unknown message format, send an error message back
                    message = zmq_error_response(
                        {
                            "success": False,
                            "message": f"Incorrect message type: {message_type}",
                            "metadata": {
                                "data": data.decode(),
                                "file": filename,
                                "lineno": lineno,
                                "function": function_name,
                            },
                        }
                    )
                    await self.service_command_socket.send_multipart([client_id, sequence_id, *message])
                    continue

                self.logger.debug(f"Received service request: {service_command}")

                self.logger.debug("Process the command...")
                response = await self._process_service_command(service_command)

                self.logger.debug("Send the response...")
                await self.service_command_socket.send_multipart([client_id, sequence_id, *response])

            except asyncio.CancelledError:
                self.logger.debug("Service command handling task cancelled.")
                break

    async def _process_service_command(self, cmd: dict[str, Any]) -> list:
        command = cmd.get("command")
        if not command:
            return zmq_error_response(
                {
                    "success": False,
                    "message": "no command field provide, don't know what to do.",
                }
            )

        handler = self.service_command_handlers.get(command)
        if not handler:
            filename, lineno, function_name = get_current_location()
            return zmq_error_response(
                {
                    "success": False,
                    "message": f"Unknown command: {command}",
                    "metadata": {"file": filename, "lineno": lineno, "function": function_name},
                }
            )

        return await handler(cmd)

    async def process_sequential_queue(self):
        """
        Process operations that need to be executed sequentially.

        When the operation return "Quit" the processing is interrupted.
        """

        self.logger.info("Starting sequential queue processing ...")

        while not self.interrupted.is_set():
            try:
                operation = await asyncio.wait_for(self._sequential_queue.get(), 0.1)
                await operation
                self._sequential_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.logger.error(f"Error processing sequential operation: {exc}")

    async def send_status_updates(self):
        """
        Send status information about the control server and the device connection to the monitoring channel.
        """

        self.logger.info("Starting status updates ...")

        async def status():
            self.logger.info(f"{datetime.datetime.now()} Sending status updates.")
            await asyncio.sleep(0.5)  # ideally, should not be larger than periodic interval

        try:
            periodic = Periodic(interval=1.0, callback=status)
            periodic.start()

            await self.interrupted.wait()

            periodic.stop()

        except asyncio.CancelledError:
            self.logger.debug("Caught CancelledError on status updates keep-alive loop.")

    async def enqueue_sequential_operation(self, operation: Coroutine[Any, Any, Any]):
        """
        Add an operation to the sequential queue.

        Args:
            operation: A coroutine object to be executed sequentially.
        """

        if self._sequential_queue is not None:  # sanity check
            self._sequential_queue.put_nowait(operation)

    async def _execute_sequential(self, operation: Coroutine[Any, Any, Any]) -> Any:
        """Execute one coroutine through the sequential queue and await its result.

        Use this helper from command handlers, service handlers, and internal tasks
        when all hardware-facing work must be serialized through one lane.
        """

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[Any] = loop.create_future()

        async def wrapped_operation():
            try:
                result = await operation
            except Exception as exc:
                if not result_future.done():
                    result_future.set_exception(exc)
                return

            if not result_future.done():
                result_future.set_result(result)

        try:
            await self.enqueue_sequential_operation(wrapped_operation())
        except Exception:
            operation.close()
            raise

        return await result_future


class AcquisitionAsyncControlServer(AsyncControlServer):
    """Async control server variant with callback-based acquisition queueing support."""

    def __init__(self):
        super().__init__()

        self.acquisition_queue_maxsize = 10_000
        """Maximum number of acquisition records buffered in memory."""

        self._acquisition_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.acquisition_queue_maxsize)
        """Queue for acquisition records received through callback ingestion."""

        self.acquisition_dropped_count = 0
        """Number of acquisition records dropped because the queue was full."""

        self.acquisition_batch_enabled = False
        """Enable grouped acquisition processing for higher-rate producers."""

        self.acquisition_batch_max_size = 100
        """Maximum number of records grouped into one batch before sink dispatch."""

        self.acquisition_batch_max_wait_s = 0.05
        """Maximum wait time [s] to collect records into a batch."""

    def get_service_info(self) -> dict[str, Any]:
        """Service info payload including acquisition queue statistics."""
        info = super().get_service_info()
        info.update(
            {
                "acquisition queue size": self._acquisition_queue.qsize(),
                "acquisition dropped": self.acquisition_dropped_count,
                "acquisition batch enabled": self.acquisition_batch_enabled,
                "acquisition batch size": self.acquisition_batch_max_size,
            }
        )
        return info

    def _create_background_tasks(self) -> list[Task]:
        tasks = super()._create_background_tasks()
        tasks.append(asyncio.create_task(self.process_acquisition_data(), name="process-acquisition-data"))
        return tasks

    def get_acquisition_callback(self) -> Callable[[Any], None]:
        """Return a callback that device drivers can call to ingest acquisition samples."""
        return self.on_acquisition_data

    def on_acquisition_data(
        self,
        data: Any,
        *,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Ingest one acquisition record from any thread.

        This function is intentionally sync/thread-safe so it can be used as a
        device-driver callback.
        """

        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": source,
            "data": data,
            "metadata": metadata or {},
        }

        loop = self._loop
        if loop is None or not loop.is_running():
            self.logger.warning("Dropping acquisition record because event loop is not running yet.")
            self.acquisition_dropped_count += 1
            return

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            self._enqueue_acquisition_record(record)
        else:
            loop.call_soon_threadsafe(self._enqueue_acquisition_record, record)

    def _enqueue_acquisition_record(self, record: dict[str, Any]):
        try:
            self._acquisition_queue.put_nowait(record)
        except asyncio.QueueFull:
            self.acquisition_dropped_count += 1
            if self.acquisition_dropped_count % 1000 == 1:
                self.logger.warning(
                    "Acquisition queue full, dropping records "
                    f"(dropped={self.acquisition_dropped_count}, maxsize={self.acquisition_queue_maxsize})."
                )

    async def process_acquisition_data(self):
        """Drain acquisition records from the queue and dispatch them to sink hooks."""

        self.logger.info("Starting acquisition data processing ...")

        while not self.interrupted.is_set():
            try:
                if not self.acquisition_batch_enabled:
                    try:
                        record = await asyncio.wait_for(self._acquisition_queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue
                    batch = [record]
                else:
                    try:
                        first_record = await asyncio.wait_for(
                            self._acquisition_queue.get(), timeout=self.acquisition_batch_max_wait_s
                        )
                    except asyncio.TimeoutError:
                        continue

                    batch = [first_record]

                    # Drain additional records without blocking to create a compact, ordered batch.
                    while len(batch) < self.acquisition_batch_max_size:
                        try:
                            batch.append(self._acquisition_queue.get_nowait())
                        except asyncio.QueueEmpty:
                            break

                try:
                    await self.handle_acquisition_batch(batch)
                finally:
                    for _ in batch:
                        self._acquisition_queue.task_done()

            except asyncio.CancelledError:
                self.logger.debug("Acquisition data task cancelled.")
                break
            except Exception as exc:
                self.logger.error(f"Error processing acquisition record: {exc}", exc_info=True)

    async def handle_acquisition_batch(self, records: list[dict[str, Any]]):
        """Hook for batch sinks; default keeps strict sequential per-record processing."""
        for record in records:
            await self.handle_acquisition_record(record)

    async def handle_acquisition_record(self, record: dict[str, Any]):
        """Hook for subclasses to forward acquisition data to DB, storage manager, or other services."""
        self.logger.debug(
            f"Acquisition record received (source={record.get('source')}, queue={self._acquisition_queue.qsize()})."
        )


DEFAULT_CLIENT_REQUEST_TIMEOUT = 5.0  # seconds
"""Default timeout for sending requests to the control server."""
DEFAULT_LINGER = 100  # milliseconds
"""Default linger for ZeroMQ sockets."""


class AsyncControlClient:
    service_type: str | None = None

    def __init__(
        self,
        endpoint: str | None = None,
        service_type: str | None = None,
        client_id: str = CONTROL_CLIENT_ID,
        timeout: float = DEFAULT_CLIENT_REQUEST_TIMEOUT,
        linger: int = DEFAULT_LINGER,
    ):
        self.logger = logging.getLogger("egse.async_control.client")

        self.endpoint = endpoint
        self.service_type = service_type or self.__class__.service_type
        self.timeout = timeout  # seconds
        self.linger = linger  # milliseconds
        self._client_id = f"{client_id}-{uuid.uuid4()}".encode()
        self._sequence = 0

        self.context: zmq.asyncio.Context = zmq.asyncio.Context.instance()

        self.device_command_socket: zmq.asyncio.Socket | None = self.context.socket(zmq.DEALER)
        self.service_command_socket: zmq.asyncio.Socket | None = self.context.socket(zmq.DEALER)

        self.device_command_port: int = 0
        self.service_command_port: int = 0

        self._post_init_is_done = False

    async def _post_init(self) -> bool:
        """
        A post initialization method that sets the device and service commanding
        ports and the endpoint for this client. The information is retrieved from
        the service registry.

        Returns:
            The method returns True if the device and service commanding port and
            the endpoint could be determined from the service registry.

            If the post initialization step has already been called, a warning is
            issued, and the method returns True.

            If no service_type is known or the service_type is not registered,
            False is returned.

        """
        if self._post_init_is_done:
            if VERBOSE_DEBUG:
                self.logger.debug("The post_init function is already called, returning.")
            return True

        self._post_init_is_done = True
        if self.service_type:
            async with AsyncRegistryClient() as registry:
                service = await registry.discover_service(self.service_type)
            if service:
                hostname = service["host"]
                self.device_command_port = port = service["port"]
                self.service_command_port = service["metadata"]["service_port"]
                self.endpoint = f"tcp://{hostname}:{port}"
                return True
            else:
                return False

        return False

    # Q: Why do we need this create method here?
    # A: The constructor (`__init__`) can not be an async method and to properly initialise the client,
    # we need to contact the ServiceRegistry for the hostname and port numbers. The service discovery
    # is an async operation.
    #
    # Additionally, it's not a good idea to perform such initialization inside the constructor of the
    # class anyway. The class can also be called as an async context manager, in which case the create()
    # is not needed and the post initialization will be done in the `__aenter__` method.

    @classmethod
    async def create(cls, service_type: str | None = None) -> AsyncControlClient:
        """Factory method that creates an AsyncControlClient and collects information about the service it needs to
        connect to."""
        resolved_service_type = service_type or cls.service_type
        if not resolved_service_type:
            raise InitializationError(
                "Could not initialise AsyncControlClient, no service_type provided and no class default configured."
            )

        client = cls(service_type=resolved_service_type)
        if not await client._post_init():
            raise InitializationError(
                "Could not initialise AsyncControlClient, "
                f"no service_type ({resolved_service_type}) found. "
                "Will not be able to connect to the control server."
            )
        return client

    async def send_device_command(
        self,
        request: dict[str, Any] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a command over the device command channel."""
        return await self._send_request(SocketType.DEVICE, request, timeout=timeout)

    async def send_service_command(
        self,
        request: dict[str, Any] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a command over the service command channel."""
        return await self._send_request(SocketType.SERVICE, request, timeout=timeout)

    def connect(self):
        self.connect_device_command_socket()
        self.connect_service_command_socket()

    def disconnect(self):
        self.disconnect_device_command_socket()
        self.disconnect_service_command_socket()

    def connect_device_command_socket(self):
        if self.endpoint is None:
            self.logger.warning("Cannot connect device command socket: endpoint is not defined.")
            return
        if self.device_command_socket is None:
            self.device_command_socket = self.context.socket(zmq.DEALER)
        self.device_command_socket.setsockopt(zmq.LINGER, self.linger)
        self.device_command_socket.setsockopt(zmq.IDENTITY, self._client_id)
        self.device_command_socket.connect(self.endpoint)

    def connect_service_command_socket(self):
        if self.endpoint is None:
            self.logger.warning("Cannot connect service command socket: endpoint is not defined.")
            return

        if self.service_command_port == 0:
            self.logger.warning("Service command port is 0 when connecting socket.")

        if self.service_command_socket is None:
            self.service_command_socket = self.context.socket(zmq.DEALER)
        self.service_command_socket.setsockopt(zmq.LINGER, self.linger)
        self.service_command_socket.setsockopt(zmq.IDENTITY, self._client_id)
        self.service_command_socket.connect(set_address_port(self.endpoint, self.service_command_port))

    def disconnect_device_command_socket(self):
        if self.device_command_socket:
            self.device_command_socket.setsockopt(zmq.LINGER, 100)
            self.device_command_socket.close()
            self.device_command_socket = None

    def disconnect_service_command_socket(self):
        if self.service_command_socket:
            self.service_command_socket.setsockopt(zmq.LINGER, 100)
            self.service_command_socket.close()
            self.service_command_socket = None

    async def __aenter__(self):
        if not self._post_init_is_done:
            if not await self._post_init():
                raise InitializationError(
                    f"Could not initialise AsyncControlClient, no service_type ({self.service_type}) found. Will not "
                    f"be able to connect to the control server."
                )
                return self

        self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    async def do(self, cmd: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
        """
        Sends a device command to the control server and waits for a response.

        Args:
            cmd (dict): The command to send. Should contain at least a 'command' key.
            timeout (float, optional): Maximum time to wait for a response in seconds. Defaults to 5.0.

        Returns:
            dict: The response from the control server. Contains at least:
                - 'success' (bool): True if the command was processed successfully, False otherwise.
                - 'message' (str or dict): The server's response or an error message.

        Notes:
            If the request times out or a socket error occurs, the method attempts
            to reset the sockets and returns a response with 'success' set to False
            and an appropriate error message.
        """
        response = await self.send_device_command(cmd, timeout=timeout)
        return response

    async def block(self, sleep: int, timeout: int | None = None) -> str | None:
        cmd = {"command": "block", "sleep": sleep}
        response = await self.send_service_command(cmd, timeout=timeout)
        if response["success"]:
            return response["message"]
        else:
            self.logger.error(f"Server returned an error: {response['message']}")
            return None

    async def ping(self, timeout: int | None = None) -> str | None:
        response = await self.send_service_command("ping", timeout=timeout)
        if response["success"]:
            return response["message"]
        else:
            self.logger.error(f"Server returned an error: {response['message']}")
            return None

    async def info(self) -> str | None:
        response = await self.send_service_command("info")
        if response["success"]:
            return response["message"]
        else:
            self.logger.error(f"Server returned an error: {response['message']}")
            return None

    async def stop_server(self) -> dict | None:
        response = await self.send_service_command("terminate")
        if response["success"]:
            return response["message"]
        else:
            self.logger.error(f"Server returned an error: {response['message']}")
            return None

    async def _send_request(
        self,
        socket_type: SocketType,
        request: dict[str, Any] | str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Send a request to the control server and get the response.

        A request can be a string with a simple command, e.g. 'ping', or it can be a dictionary
        in which case it will be sent as a JSON request. The dictionary shall have the following format:

            request = {
                'command': <the command string without arguments>,
                'args': [*args],
                'kwargs': {**kwargs},
            }

        The response from the server will always be a dictionary with at least the following structure:

            response = {
                'success': <True or False>,
                'message': <The content of the data returned by the server>,
            }

        Args:
            socket_type: socket type to use for the command request.
            request: The request to send to the control server.
            timeout: how many seconds before the request times out.

        Returns:
            The response from the control server as a dictionary.
        """

        timeout = timeout or self.timeout

        socket = self._get_socket(socket_type)
        self._sequence += 1
        try:
            if socket is None:
                raise RuntimeError("Socket of the AsyncControlClient is not initialized.")

            if isinstance(request, str):
                message = zmq_string_request(request)
            elif isinstance(request, dict):
                message = zmq_json_request(request)
            else:
                raise ValueError(f"request argument shall be a string or a dictionary, not {type(request)}.")

            if VERBOSE_DEBUG:
                self.logger.debug(f"Sending multipart message: {message}")

            await socket.send_multipart([str(self._sequence).encode(), *message])

            while True:
                sequence, msg_type, data = await asyncio.wait_for(socket.recv_multipart(), timeout=timeout)

                if VERBOSE_DEBUG:
                    self.logger.debug(f"Received multipart message: {sequence}, {msg_type}, {data}")

                if int(sequence.decode()) < self._sequence:
                    self.logger.warning(
                        f"Received a reply from a previous command: {int(sequence.decode())}, {msg_type}, {data}, "
                        f"current sequence id = {self._sequence}"
                    )
                    continue
                elif int(sequence.decode()) > self._sequence:
                    self.logger.error(
                        f"Protocol violation: received reply for future request {sequence} "
                        f"(current sequence: {self._sequence}). "
                        f"Possible bug or multiple clients with the same identity."
                    )
                    raise RuntimeError(
                        f"Protocol violation: "
                        f"Got a reply with a future sequence id {sequence}, current sequence id is {self._sequence}."
                    )

                if msg_type == b"MESSAGE_TYPE:STRING":
                    return {"success": True, "message": data.decode("utf-8")}
                elif msg_type == b"MESSAGE_TYPE:JSON":
                    return json.loads(data)
                elif msg_type == b"MESSAGE_TYPE:ERROR":
                    return pickle.loads(data)
                else:
                    msg = f"Unknown server response message type: {msg_type}"
                    self.logger.error(msg)
                    return {"success": False, "message": msg}

        except asyncio.TimeoutError:
            self.logger.error(f"{socket_type.name} request timed out after {timeout:.3f}s")
            self.recreate_socket(socket_type)
            return {
                "success": False,
                "message": f"Request timed out after {timeout:.3f}s",
            }

        except zmq.ZMQError as exc:
            self.logger.error(f"ZMQ error: {exc}")
            self.recreate_socket(socket_type)
            return {
                "success": False,
                "message": f"ZMQError: {exc}",
            }

        except Exception as exc:
            self.logger.error(f"Error sending request: {type(exc).__name__} – {exc}")
            traceback = Traceback.from_exception(
                type(exc),
                exc,
                exc.__traceback__,
                show_locals=True,  # Optional: show local variables
                width=None,  # Optional: use full width
                extra_lines=3,  # Optional: context lines
            )
            log_rich_output(self.logger, logging.ERROR, traceback)
            return {"success": False, "message": str(exc)}

    def _get_socket(self, socket_type: SocketType):
        match socket_type:
            case SocketType.DEVICE:
                return self.device_command_socket
            case SocketType.SERVICE:
                return self.service_command_socket

    def recreate_socket(self, socket_type: SocketType):
        if RECREATE_SOCKET:
            self.logger.warning(f"Recreating {socket_type.name} socket ...")
            match socket_type:
                case SocketType.DEVICE:
                    self.disconnect_device_command_socket()
                    self.connect_device_command_socket()
                case SocketType.SERVICE:
                    self.disconnect_service_command_socket()
                    self.connect_service_command_socket()
        else:
            self.logger.debug("Socket recreation after timeout has been disabled.")


class TypedAsyncControlClient(AsyncControlClient):
    """Small helper base class for client subclasses with typed command wrappers.

    Subclasses can call these helpers to keep command methods concise and consistent.
    """

    def _success_message(self, response: dict[str, Any], command_name: str) -> Any | None:
        if response.get("success"):
            return response.get("message")
        self.logger.error(f"{command_name} failed: {response.get('message')}")
        return None

    def _success_message_as_str(self, response: dict[str, Any], command_name: str) -> str | None:
        message = self._success_message(response, command_name)
        if message is None:
            return None
        if isinstance(message, str):
            return message
        self.logger.error(f"{command_name} returned non-string message: {type(message).__name__}")
        return None

    def _success_message_as_dict(self, response: dict[str, Any], command_name: str) -> dict[str, Any] | None:
        message = self._success_message(response, command_name)
        if message is None:
            return None
        if isinstance(message, dict):
            return message
        self.logger.error(f"{command_name} returned non-dict message: {type(message).__name__}")
        return None


async def cs_test_device_command_timeouts():
    """
    This test is about timeouts on the client and blocking commands on the server
    for *device commands*.

    We start a control server which will register to the service registry and
    send out heartbeats.

    We start a control client that will connect to the server through its service type.
    Then we send the following commands, from the client perspective:

    - send a 'block' device command of 8s and a timeout of 3s. This will block the
      device commanding part on the server for ten seconds. The client will
      time out on this command after three seconds.
    - sleep for ten seconds.
    - send a 'say' command with a timeout of 2s. This will return immediately.

    The client should properly discard the server reply from the timed out block
    command. You should see a warning message saying a reply was received from a
    previous command. The 'say' command should receive its response as expected.

    """

    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    logger.info("Starting Asynchronous Control Server ...")

    # Give the control server the time to start up
    logger.info("Sleep for 0.5s...")
    await asyncio.sleep(0.5)

    # As of now, the server_task is running 'in the background' in the event loop.

    # Now create a control client that will connect to the above server.
    async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 5s...")
        await asyncio.sleep(5.0)

        logger.info("Send a blocking device command, duration is 8s, timeout is 3s.")
        response = await client.do({"command": "block", "sleep": 8}, timeout=3)
        logger.info(f"block: {response=}")

        if response["success"] or "timed out" not in response["message"]:
            logger.error(f"Did not get expected message from server: {response['message']}")

        logger.info("Sleep for 10s...")
        await asyncio.sleep(10.0)

        logger.info("Send a 'say' device command, timeout is 2s.")
        response = await client.do({"command": "say", "message": "Hello, World!"}, timeout=2.0)
        logger.info(f"say: {response=}")

        if not response["success"] or "Hello, World!" not in response["message"]:
            logger.error(f"Did not get expected message from server: {response['message']}")

        is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
        logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

        logger.info("Sleeping 1s before terminating the server...")
        await asyncio.sleep(1.0)

        logger.info("Terminating the server.")
        response = await client.stop_server()
        logger.info(f"stop_server: {response = }")

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

    await server_task

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")


async def cs_test_service_command_timeouts():
    """
    This test is about timeouts on the client and blocking commands on the server
    for *service commands*.

    We start a control server which will register to the service registry and
    send out heartbeats.

    We start a control client that will connect to the server through its service type.
    Then we send the following commands, from the client perspective:

    - send a 'block' service command of 8s and a timeout of 3s. This will block the
      service commanding part on the server for ten seconds. The client will
      time out on this command after three seconds.
    - sleep for ten seconds.
    - send a 'info' command with a timeout of 2s. This will return immediately.

    The client should properly discard the server reply from the timed out block
    command. You should see a warning message saying a reply was received from a
    previous command. The 'info' command should receive its response as expected.

    """

    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    logger.info("Starting Asynchronous Control Server ...")

    # Give the control server the time to start up
    logger.info("Sleep for 0.5s...")
    await asyncio.sleep(0.5)

    # As of now, the server_task is running 'in the background' in the event loop.

    # Now create a control client that will connect to the above server.
    async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 5s...")
        await asyncio.sleep(5.0)

        logger.info("Send a blocking service command, duration is 8s, timeout is 3s.")
        response = await client.block(sleep=8, timeout=3)
        logger.info(f"service block: {response=}")

        logger.info("Sleep for 10s...")
        await asyncio.sleep(10.0)

        logger.info("Get info on the control server.")
        response = await client.info()
        logger.info(f"service info: {response=}")

        is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
        logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

        logger.info("Sleeping 1s before terminating the server...")
        await asyncio.sleep(1.0)

        logger.info("Terminating the server.")
        response = await client.stop_server()
        logger.info(f"stop_server: {response = }")

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

    await server_task

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")


async def control_server_test():
    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    logger.info("Starting Asynchronous Control Server ...")

    # Give the control server the time to start up
    logger.info("Sleep for 0.5s...")
    await asyncio.sleep(0.5)

    # As of now, the server_task is running 'in the background' in the event loop.

    # Now create a control client that will connect to the above server.
    async with AsyncControlClient(service_type=CONTROL_SERVER_SERVICE_TYPE) as client:
        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 5s...")
        await asyncio.sleep(5.0)

        logger.info("Send a 'ping' service command...")
        response = await client.ping()
        logger.info(f"ping service command: {response = }")  # should be: response = 'pong'

        logger.info("Send an 'info' service command...")
        response = await client.info()
        logger.info(f"info service command: {response = }")  # should be: response = {'name': 'AsyncControlServer', ...

        logger.info("Send an 'info' device command...")
        # info() is a service command and not a device command, so this will fail.
        response = await client.do({"command": "info"})
        # should be: response={'success': False, 'message': 'Unknown command: info', ...
        logger.info(f"info device command: {response=}")

        # this will block commanding since device commands are executed in the same task
        # the do() will timeout after 3s, but the block command will run for 10s on the
        # server, and it will send back an ACK (which will be caught and interpreted by
        # –in this case– the seconds do 'say' command, which will not yet have timed out.
        logger.info("Send a blocking device command, duration is 9s, timeout is 3s.")
        response = await client.do({"command": "block", "sleep": 9}, timeout=3.0)
        # should be: response={'success': False, 'message': 'Request timed out after 3.000s'}
        logger.info(f"Blocking device command: {response=}")

        # ping() is a service command, so this is not blocked by the above block() command
        logger.info("Send a 'ping' service command...")
        response = await client.ping()
        logger.info(f"ping service command: {response=}")

        # say() is a device command and will time out after 2s because the above blocking
        # block() command is still running on the server
        logger.info("Send a 'say' device command, timeout is 2s.")
        response = await client.do({"command": "say", "message": "Hello, World!"}, timeout=2.0)
        logger.info(f"say device command: {response=}")

        # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
        logger.info("Sleep for 10s...")
        await asyncio.sleep(10.0)

        # This time we won't let the command time out...
        logger.info("Send a 'say' device command, timeout is 2s.")
        response = await client.do({"command": "say", "message": "Hello, Again!"}, timeout=2.0)
        logger.info(f"say device command: {response=}")

        is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
        logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

        logger.info("Sleeping 1s before terminating the server...")
        await asyncio.sleep(1.0)

        logger.info("Terminating the server.")
        response = await client.stop_server()
        logger.info(f"stop_server: {response = }")

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")

    await server_task

    is_active = await is_control_server_active(service_type=CONTROL_SERVER_SERVICE_TYPE)
    logger.info(f"Server status: {'active' if is_active else 'unreachable'}")


if __name__ == "__main__":
    # The statement logging.captureWarnings(True) redirects Python's warnings module output
    # (such as warnings.warn(...)) to the logging system, so warnings appear in your logs
    # instead of just printing to stderr. This is useful for unified logging and easier
    # debugging, especially in larger applications.
    logging.captureWarnings(True)

    try:
        main_task = asyncio.run(cs_test_device_command_timeouts())
        # main_task = asyncio.run(cs_test_service_command_timeouts())
        # main_task = asyncio.run(control_server_test())
    except KeyboardInterrupt:
        print("Caught KeyboardInterrupt, terminating.")
