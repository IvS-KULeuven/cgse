"""
This module defines base classes and generic functions to work with sockets.
"""

import asyncio
import select
import socket
import time
from typing import Optional

from egse.device import AsyncDeviceInterface
from egse.device import AsyncDeviceTransport
from egse.device import DeviceConnectionError
from egse.device import DeviceConnectionInterface
from egse.device import DeviceTimeoutError
from egse.device import DeviceTransport
from egse.env import bool_env
from egse.log import logger
from egse.system import type_name

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG", default=False)

SEPARATOR = b"\x03"
SEPARATOR_STR = SEPARATOR.decode()


class SocketDevice(DeviceConnectionInterface, DeviceTransport):
    """Base class that implements the socket interface."""

    # We set a default connect timeout of 3.0 sec before connecting and reset
    # to None (=blocking) after connecting. The reason for this is that when no
    # device is available, e.g. during testing, the timeout will take about
    # two minutes which is way too long. It needs to be evaluated if this
    # approach is acceptable and not causing problems during production.

    def __init__(
        self,
        hostname: str,
        port: int,
        connect_timeout: float = 3.0,
        read_timeout: float | None = 1.0,
        separator: bytes = SEPARATOR,
    ):
        super().__init__()
        self.is_connection_open = False
        self.hostname = hostname
        self.port = port
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.separator = separator
        self.separator_str = separator.decode()
        self.socket = None

    @property
    def device_name(self):
        """The name of the device that this interface connects to."""
        return f"SocketDevice({self.hostname}:{self.port})"

    def connect(self):
        """
        Connect the device.

        Raises:
            ConnectionError: When the connection could not be established.
                Check the logging messages for more detail.
            TimeoutError: When the connection timed out.
            ValueError: When hostname or port number are not provided.
        """

        # Sanity checks

        if self.is_connection_open:
            logger.warning(f"{self.device_name}: trying to connect to an already connected socket.")
            return

        if self.hostname in (None, ""):
            raise ValueError(f"{self.device_name}: hostname is not initialized.")

        if self.port in (None, 0):
            raise ValueError(f"{self.device_name}: port number is not initialized.")

        # Create a new socket instance

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as exc:
            raise ConnectionError(f"{self.device_name}: Failed to create socket.") from exc

        try:
            logger.debug(f'Connecting a socket to host "{self.hostname}" using port {self.port}')
            self.socket.settimeout(self.connect_timeout)
            self.socket.connect((self.hostname, self.port))
            self.socket.settimeout(None)
        except ConnectionRefusedError as exc:
            raise ConnectionError(f"{self.device_name}: Connection refused to {self.hostname}:{self.port}.") from exc
        except TimeoutError as exc:
            raise TimeoutError(f"{self.device_name}: Connection to {self.hostname}:{self.port} timed out.") from exc
        except socket.gaierror as exc:
            raise ConnectionError(f"{self.device_name}: Socket address info error for {self.hostname}") from exc
        except socket.herror as exc:
            raise ConnectionError(f"{self.device_name}: Socket host address error for {self.hostname}") from exc
        except OSError as exc:
            raise ConnectionError(f"{self.device_name}: OSError caught ({exc}).") from exc

        self.is_connection_open = True

    def disconnect(self):
        """
        Disconnect from the Ethernet connection.

        Raises:
            ConnectionError when the socket could not be closed.
        """

        assert self.socket is not None  # extra check + for mypy type checking

        try:
            if self.is_connection_open:
                logger.debug(f"Disconnecting from {self.hostname}")
                self.socket.close()
                self.is_connection_open = False
        except Exception as e_exc:
            raise ConnectionError(f"{self.device_name}: Could not close socket to {self.hostname}") from e_exc

    def is_connected(self) -> bool:
        """
        Check if the device is connected.

        Returns:
             True is the device is connected, False otherwise.
        """

        return bool(self.is_connection_open)

    def reconnect(self):
        """
        Reconnect to the device. If the connection is open, this function will first disconnect
        and then connect again.
        """

        if self.is_connection_open:
            self.disconnect()
        self.connect()

    def read(self) -> bytes:
        """
        Read until ETX (b'\x03') or until `self.read_timeout` elapses.
        Uses `select` to avoid blocking indefinitely when no data is available.
        If `self.read_timeout` was set to None in the constructor, this will block anyway.
        """
        if not self.socket:
            raise DeviceConnectionError(self.device_name, "The device is not connected, connect before reading.")

        buf_size = 1024 * 4
        response = bytearray()

        # If read_timeout is None we preserve blocking behavior; otherwise enforce overall timeout.
        if self.read_timeout is None:
            end_time = None
        else:
            end_time = time.monotonic() + self.read_timeout

        try:
            while True:
                # compute the remaining timeout for select, this is needed because we read in different parts
                # until ETX is received, and we want to receive the complete messages including ETX within
                # the read timeout.
                if end_time is None:
                    timeout = None
                else:
                    remaining = end_time - time.monotonic()
                    if remaining <= 0.0:
                        raise DeviceTimeoutError(self.device_name, "Socket read timed out")
                    timeout = remaining

                ready, _, _ = select.select([self.socket], [], [], timeout)

                if not ready:
                    # no socket ready within timeout
                    raise DeviceTimeoutError(self.device_name, "Socket read timed out")

                try:
                    data = self.socket.recv(buf_size)
                except OSError as exc:
                    raise DeviceConnectionError(self.device_name, f"Caught {type_name(exc)}: {exc}") from exc

                if not data:
                    # remote closed connection (EOF)
                    raise DeviceConnectionError(self.device_name, "Connection closed by peer")

                response.extend(data)

                if self.separator in response:
                    break

        except DeviceTimeoutError:
            raise
        except DeviceConnectionError:
            raise
        except Exception as exc:
            # unexpected errors - translate to DeviceConnectionError
            raise DeviceConnectionError(self.device_name, "Socket read error") from exc

        return bytes(response)

    def write(self, command: str):
        """
        Send a command to the device.

        No processing is done on the command string, except for the encoding into a bytes object.

        Args:
            command: the command string including terminators.

        Raises:
            A DeviceTimeoutError when the send timed out, and a DeviceConnectionError if
            there was a socket related error.
        """

        if not self.socket:
            raise DeviceConnectionError(self.device_name, "The device is not connected, connect before writing.")

        try:
            command += self.separator_str if not command.endswith(self.separator_str) else ""
            if VERBOSE_DEBUG:
                logger.debug(f"Writing to {self.device_name}: {command!r}")
            self.socket.sendall(command.encode())
        except socket.timeout as exc:
            raise DeviceTimeoutError(self.device_name, "Socket timeout error") from exc
        except socket.error as exc:
            # Interpret any socket-related error as an I/O error
            raise DeviceConnectionError(self.device_name, "Socket communication error.") from exc

    def trans(self, command: str) -> bytes:
        """
        Send a command to the device and wait for the response.

        No processing is done on the command string, except for the encoding into a bytes object.

        Args:
            command: the command string including terminators.

        Returns:
            A bytes object containing the response from the device. No processing is done
            on the response.

        Raises:
            A DeviceTimeoutError when the send timed out, and a DeviceConnectionError if
            there was a socket related error.
        """

        if not self.socket:
            raise DeviceConnectionError(self.device_name, "The device is not connected, connect before writing.")

        self.write(command)
        response = self.read()

        if VERBOSE_DEBUG:
            logger.debug(f"Read from {self.device_name}: {response!r}")

        return response


class AsyncSocketDevice(AsyncDeviceInterface, AsyncDeviceTransport):
    """
    Async socket-backed device using asyncio streams.

    - async connect() / disconnect()
    - async read() reads until ETX (b'\\x03') or timeout
    - async write() and async trans()
    """

    def __init__(
        self,
        hostname: str,
        port: int,
        connect_timeout: float = 3.0,
        read_timeout: float | None = 1.0,
        separator: bytes = SEPARATOR,
    ):
        super().__init__()
        self.hostname = hostname
        self.port = port
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.separator = separator
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_connection_open = False

    @property
    def device_name(self) -> str:
        # Override this property for a decent name
        return f"AsyncSocketDevice({self.hostname}:{self.port})"

    async def connect(self) -> None:
        if self.is_connection_open:
            logger.debug(f"{self.device_name}: already connected")
            return

        if not self.hostname:
            raise ValueError(f"{self.device_name}: hostname is not initialized.")
        if not self.port:
            raise ValueError(f"{self.device_name}: port is not initialized.")

        try:
            logger.debug(f"{self.device_name}: connect() called; is_connection_open={self.is_connection_open}")
            coro = asyncio.open_connection(self.hostname, self.port)
            self.reader, self.writer = await asyncio.wait_for(coro, timeout=self.connect_timeout)
            self.is_connection_open = True
            logger.debug(f"{self.device_name}: connected -> peer={self.writer.get_extra_info('peername')}")

        except asyncio.TimeoutError as exc:
            await self._cleanup()
            logger.warning(f"{self.device_name}: connect timed out")
            raise DeviceTimeoutError(self.device_name, f"Connection to {self.hostname}:{self.port} timed out.") from exc
        except Exception as exc:
            await self._cleanup()
            logger.warning(f"{self.device_name}: connect failed: {type_name(exc)} – {exc}")
            raise DeviceConnectionError(self.device_name, f"Failed to connect to {self.hostname}:{self.port}") from exc

    async def disconnect(self) -> None:
        logger.debug(f"{self.device_name}: disconnect() called; writer_exists={bool(self.writer)}")
        peer = None
        try:
            if self.writer and not self.writer.is_closing():
                peer = self.writer.get_extra_info("peername")
                self.writer.close()
                # wait for close, but don't hang forever
                try:
                    await asyncio.wait_for(self.writer.wait_closed(), timeout=1.0)
                except asyncio.TimeoutError:
                    logger.debug(f"{self.device_name}: wait_closed() timed out for peer={peer}")

        finally:
            await self._cleanup()
            logger.debug(f"{self.device_name}: disconnected ({peer=})")

    def is_connected(self) -> bool:
        return bool(self.is_connection_open and self.writer and not self.writer.is_closing())

    async def _cleanup(self) -> None:
        self.reader = None
        self.writer = None
        self.is_connection_open = False

    async def read(self) -> bytes:
        if not self.reader:
            raise DeviceConnectionError(self.device_name, "Not connected")
        try:
            # readuntil includes the separator; we keep it for parity with existing code
            data = await asyncio.wait_for(self.reader.readuntil(separator=self.separator), timeout=self.read_timeout)
            return data
        except asyncio.IncompleteReadError as exc:
            # EOF before separator
            await self._cleanup()
            raise DeviceConnectionError(self.device_name, "Connection closed while reading") from exc
        except asyncio.TimeoutError as exc:
            raise DeviceTimeoutError(self.device_name, "Socket read timed out") from exc
        except Exception as exc:
            await self._cleanup()
            raise DeviceConnectionError(self.device_name, "Socket read error") from exc

    async def write(self, command: str) -> None:
        if not self.writer:
            raise DeviceConnectionError(self.device_name, "Not connected")
        try:
            self.writer.write(command.encode())
            await asyncio.wait_for(self.writer.drain(), timeout=self.read_timeout)
        except asyncio.TimeoutError as exc:
            raise DeviceTimeoutError(self.device_name, "Socket write timed out") from exc
        except Exception as exc:
            await self._cleanup()
            raise DeviceConnectionError(self.device_name, "Socket write error") from exc

    async def trans(self, command: str) -> bytes:
        if not self.writer or not self.reader:
            raise DeviceConnectionError(self.device_name, "Not connected")
        try:
            await self.write(command)
            return await self.read()
        except (DeviceTimeoutError, DeviceConnectionError):
            raise
        except Exception as exc:
            await self._cleanup()
            raise DeviceConnectionError(self.device_name, "Socket trans error") from exc
