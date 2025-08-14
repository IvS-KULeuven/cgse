import asyncio
import socket
from typing import Any
from typing import Dict
from typing import Optional

from egse.device import AsyncDeviceTransport
from egse.device import DeviceConnectionError
from egse.device import DeviceError
from egse.device import DeviceTimeoutError
from egse.log import logger

# Constants that can be overridden by specific device implementations
DEFAULT_READ_TIMEOUT = 1.0  # seconds
DEFAULT_CONNECT_TIMEOUT = 3.0  # seconds
IDENTIFICATION_QUERY = "*IDN?"


class SCPICommand:
    """Base class for SCPI commands."""

    def get_cmd_string(self, *args, **kwargs) -> str:
        """Constructs the command string, based on the given arguments.

        Args:
            *args: Positional arguments for the command
            **kwargs: Keyword arguments for the command

        Returns:
            Complete command string
        """
        raise NotImplementedError("Subclasses must implement get_cmd_string().")


class AsyncSCPIInterface(AsyncDeviceTransport):
    """Generic asynchronous interface for devices that use SCPI commands over Ethernet."""

    def __init__(
        self,
        device_name: str,
        hostname: str,
        port: int,
        settings: Optional[Dict[str, Any]] = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        id_validation: Optional[str] = None,
    ):
        """Initialize an asynchronous Ethernet interface for SCPI communication.

        Args:
            device_name: Name of the device (used in error messages)
            hostname: Hostname or IP address of the device
            port: TCP port number for communication
            settings: Additional device-specific settings
            connect_timeout: Timeout for connection attempts in seconds
            read_timeout: Timeout for read operations in seconds
            id_validation: String that should appear in the device's identification response
        """
        self.device_name = device_name
        self.hostname = hostname
        self.port = port
        self.settings = settings or {}
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.id_validation = id_validation

        self._reader = None
        self._writer = None
        self._is_connection_open = False
        self._connect_lock = asyncio.Lock()
        """Prevents multiple, simultaneous connect or disconnect attempts."""
        self._io_lock = asyncio.Lock()
        """Prevents multiple coroutines from attempting to read, write or query from the same stream
        at the same time."""

    async def connect(self) -> None:
        """Connect to the device asynchronously.

        Raises:
            DeviceConnectionError: When the connection could not be established
            DeviceTimeoutError: When the connection timed out
            ValueError: When hostname or port are invalid
        """
        async with self._connect_lock:
            # Sanity checks
            if self._is_connection_open:
                logger.warning(f"{self.device_name}: Trying to connect to an already connected device.")
                return

            if not self.hostname:
                raise ValueError(f"{self.device_name}: Hostname is not initialized.")

            if not self.port:
                raise ValueError(f"{self.device_name}: Port number is not initialized.")

            # Attempt to establish a connection
            try:
                logger.debug(f'Connecting to {self.device_name} at "{self.hostname}" using port {self.port}')

                connect_task = asyncio.open_connection(self.hostname, self.port)
                self._reader, self._writer = await asyncio.wait_for(connect_task, timeout=self.connect_timeout)

                self._is_connection_open = True

                logger.debug(f"Successfully connected to {self.device_name}.")

            except asyncio.TimeoutError as exc:
                raise DeviceTimeoutError(
                    self.device_name, f"Connection to {self.hostname}:{self.port} timed out"
                ) from exc
            except ConnectionRefusedError as exc:
                raise DeviceConnectionError(
                    self.device_name, f"Connection refused to {self.hostname}:{self.port}"
                ) from exc
            except socket.gaierror as exc:
                raise DeviceConnectionError(self.device_name, f"Address resolution error for {self.hostname}") from exc
            except socket.herror as exc:
                raise DeviceConnectionError(self.device_name, f"Host address error for {self.hostname}") from exc
            except OSError as exc:
                raise DeviceConnectionError(self.device_name, f"OS error: {exc}") from exc

            # Validate device identity if requested
            if self.id_validation:
                logger.debug("Validating connection..")
                if not await self.is_connected():
                    await self.disconnect()
                    raise DeviceConnectionError(self.device_name, "Device connected but failed identity verification")

    async def disconnect(self) -> None:
        """Disconnect from the device asynchronously.

        Raises:
            DeviceConnectionError: When the connection could not be closed properly
        """
        async with self._connect_lock:
            try:
                if self._is_connection_open and self._writer is not None:
                    logger.debug(f"Disconnecting from {self.device_name} at {self.hostname}")
                    self._writer.close()
                    await self._writer.wait_closed()
                    self._writer = None
                    self._reader = None
                    self._is_connection_open = False
            except Exception as exc:
                raise DeviceConnectionError(self.device_name, f"Could not close connection: {exc}") from exc

    async def reconnect(self) -> None:
        """Reconnect to the device asynchronously."""
        async with self._connect_lock:
            if self._is_connection_open:
                await self.disconnect()
                await asyncio.sleep(0.1)
            await self.connect()

    async def is_connected(self) -> bool:
        """Check if the device is connected and responds correctly to identification.

        Returns:
            True if the device is connected and validated, False otherwise
        """
        if not self._is_connection_open:
            return False

        try:
            # Query device identification
            id_response = (await self.query(IDENTIFICATION_QUERY)).decode().strip()

            # Validate the response if validation string is provided
            if self.id_validation and self.id_validation not in id_response:
                logger.error(
                    f"{self.device_name}: Device did not respond correctly to identification query. "
                    f'Expected "{self.id_validation}" in response, got: {id_response}'
                )
                await self.disconnect()
                return False

            return True

        except DeviceError as exc:
            logger.exception(exc)
            logger.error(f"{self.device_name}: Connection test failed")
            await self.disconnect()
            return False

    async def write(self, command: str) -> None:
        """Send a command to the device without waiting for a response, handle line termination, and write timeouts.

        Args:
            command: Command string to send

        Raises:
            DeviceConnectionError: When there's a communication problem
            DeviceTimeoutError: When the operation times out
        """
        async with self._io_lock:
            try:
                if not self._is_connection_open or self._writer is None:
                    raise DeviceConnectionError(self.device_name, "Device not connected, use connect() first")

                # Ensure command ends with newline
                if not command.endswith("\n"):
                    command += "\n"

                self._writer.write(command.encode())
                await self._writer.drain()

            except asyncio.TimeoutError as exc:
                raise DeviceTimeoutError(self.device_name, "Write operation timed out") from exc
            except (ConnectionError, OSError) as exc:
                raise DeviceConnectionError(self.device_name, f"Communication error: {exc}") from exc

    async def read(self) -> bytes:
        """
        Read response from the device asynchronously and return it unaltered.

        Returns:
            Response bytes from the device.

        Raises:
            DeviceConnectionError: When there's a communication problem
            DeviceTimeoutError: When the read operation times out
        """
        async with self._io_lock:
            if not self._is_connection_open or self._reader is None:
                raise DeviceConnectionError(self.device_name, "Device not connected, use connect() first")

            try:
                # First, small delay to allow device to prepare response
                await asyncio.sleep(0.01)

                # Try to read until newline (common SCPI terminator)
                try:
                    response = await asyncio.wait_for(
                        self._reader.readuntil(separator=b"\n"), timeout=self.read_timeout
                    )
                    return response

                except asyncio.IncompleteReadError as exc:
                    # Connection closed before receiving full response
                    logger.warning(f"{self.device_name}: Incomplete read, got {len(exc.partial)} bytes")
                    return exc.partial if exc.partial else b"\r\n"

                except asyncio.LimitOverrunError:
                    # Response too large for buffer
                    logger.warning(f"{self.device_name}: Response exceeded buffer limits")
                    # Fall back to reading a large chunk
                    return await asyncio.wait_for(
                        self._reader.read(8192),  # Larger buffer for exceptional cases
                        timeout=self.read_timeout,
                    )

            except asyncio.TimeoutError as exc:
                raise DeviceTimeoutError(self.device_name, "Read operation timed out") from exc
            except Exception as exc:
                raise DeviceConnectionError(self.device_name, f"Read error: {exc}") from exc

    async def trans(self, command: str) -> bytes:
        """
        Send a single command to the device controller and block until a response from the
        controller.

        Args:
            command: command string

        Returns:
            Response bytes object from the device (including whitespace)

        Raises:
            DeviceConnectionError: When there's a communication problem.
            DeviceTimeoutError: When the operation times out.
        """

        async with self._io_lock:
            try:
                if not self._is_connection_open or self._writer is None:
                    raise DeviceConnectionError(self.device_name, "Device not connected, use connect() first")

                # Ensure command ends with newline
                if not command.endswith("\n"):
                    command += "\n"

                self._writer.write(command.encode())
                await self._writer.drain()

                # First, small delay to allow device to prepare response
                await asyncio.sleep(0.01)

                # Try to read until newline (common SCPI terminator)
                try:
                    response = await asyncio.wait_for(
                        self._reader.readuntil(separator=b"\n"), timeout=self.read_timeout
                    )
                    return response

                except asyncio.IncompleteReadError as exc:
                    # Connection closed before receiving full response
                    logger.warning(f"{self.device_name}: Incomplete read, got {len(exc.partial)} bytes")
                    return exc.partial if exc.partial else b"\r\n"

                except asyncio.LimitOverrunError:
                    # Response too large for buffer
                    logger.warning(f"{self.device_name}: Response exceeded buffer limits")
                    # Fall back to reading a large chunk
                    return await asyncio.wait_for(
                        self._reader.read(8192),  # Larger buffer for exceptional cases
                        timeout=self.read_timeout,
                    )

            except asyncio.TimeoutError as exc:
                raise DeviceTimeoutError(self.device_name, "Communication timed out") from exc
            except (ConnectionError, OSError) as exc:
                raise DeviceConnectionError(self.device_name, f"Communication error: {exc}") from exc
            except Exception as exc:
                raise DeviceConnectionError(self.device_name, f"Transaction error: {exc}") from exc

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
