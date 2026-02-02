# Unit Tests were created by GitHub Copilot and adapted/improved afterward.

import asyncio
import socketserver
import threading
import time

import pytest
import pytest_asyncio

from egse.device import DeviceConnectionError
from egse.device import DeviceTimeoutError
from egse.log import logging
from egse.socketdevice import AsyncSocketDevice
from egse.socketdevice import SocketDevice
from egse.system import type_name

logger = logging.getLogger("egse.test.socketdevice")

SEPARATOR = b"\x03"
SEPARATOR_STR = SEPARATOR.decode()


# Synchronous server used by SocketDevice tests
class _SyncEchoHandler(socketserver.BaseRequestHandler):
    """
    Echo handler: sends back a prefix and an ETX (b'\x03') so client read() completes.
    Keeps connection open until client closes socket.
    """

    def handle(self):
        try:
            while True:
                data = self.request.recv(4096)
                if not data:
                    break
                if b"NO-REPLY" in data:
                    continue
                if b"REPLY-IN-PARTS" in data:
                    self.request.sendall(b"RESP:")
                    # time.sleep(0.2)
                    self.request.sendall(data)
                    # time.sleep(0.2)
                    self.request.sendall(SEPARATOR)
                else:
                    self.request.sendall(b"RESP:" + data + SEPARATOR)
        except Exception as exc:
            logger.warning(f"Caught {type_name(exc)}: {exc}")


# Properly close the async_echo_server including active writers
async def close_server(server, active_writers):
    # This coroutine is used by the async_echo_server fixture for the teardown of that fixture,
    # and it is also used by the test_async_cleanup_on_broken_connection test to make sure no active
    # connections exist and the test can succeed.

    server.close()

    try:
        await asyncio.wait_for(server.wait_closed(), timeout=1.0)
    except asyncio.TimeoutError:
        logger.warning("server.wait_closed() timed out; continuing to close active writers")

    logger.info("After server close")

    # explicitly close all existing client connections
    for active_writer in list(active_writers):
        try:
            logger.debug(f"Closing {active_writer=}")
            active_writer.close()
            await active_writer.wait_closed()
        except Exception as exc:
            logger.warning(f"Caught {type_name(exc)}: {exc}")

    logger.info("Server and active connections terminated.")


# Synchronous server used by SocketDevice tests
@pytest.fixture(scope="module")
def sync_echo_server():
    """Start a ThreadingTCPServer serving _SyncEchoHandler on localhost:0 (ephemeral dynamic port)."""
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SyncEchoHandler)
    server.allow_reuse_address = True
    host, port = server.server_address

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield host, port

    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


# Asynchronous server used by AsyncSocketDevice tests
@pytest_asyncio.fixture
async def async_echo_server():
    """
    Start an asyncio server that echos back data with a prefix and an ETX (b'\x03').
    Yields (host, port, server, active_writers) then closes the server on teardown.

    The active writers are used in the test to handle a broken connection.
    """
    active_writers = set()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        active_writers.add(writer)
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                if b"NO-REPLY" in data:
                    continue
                writer.write(b"RESP:" + data + SEPARATOR)
                await writer.drain()
        except Exception as exc:
            logger.warning(f"Caught {type_name(exc)}: {exc}")
        finally:
            active_writers.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as exc:
                logger.warning(f"Caught {type_name(exc)}: {exc}")

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    sockets = server.sockets

    logger.debug(f"{sockets=}, {sockets[0].getsockname()=}")

    assert sockets, "Server sockets missing"
    host, port = sockets[0].getsockname()[:2]  # getsocketname() returns ('127.0.0.1', <port>)

    yield host, port, server, active_writers

    await close_server(server, active_writers)


def test_sync_connect_write_trans_and_disconnect(sync_echo_server):
    host, port = sync_echo_server
    dev = SocketDevice(hostname=host, port=port)

    dev.connect()
    assert dev.is_connected() is True

    # trans (send and get response that contains ETX)
    resp = dev.trans("HELLO")
    assert isinstance(resp, bytes)
    assert resp.endswith(SEPARATOR)
    assert b"RESP:HELLO" in resp

    # trans (send and get response that contains ETX)
    resp = dev.trans("HELLO:REPLY-IN-PARTS")
    assert isinstance(resp, bytes)
    assert resp.endswith(SEPARATOR)
    assert b"RESP:HELLO" in resp

    # write-only (then direct read via trans)
    dev.write("PING:NO-REPLY")
    time.sleep(0.1)
    assert b"RESP:ONE" in dev.trans("ONE")

    with pytest.raises(DeviceTimeoutError):
        dev.read()

    dev.disconnect()
    assert dev.is_connected() is False


def test_sync_connect_read_failures(sync_echo_server):
    host, port = sync_echo_server
    dev = SocketDevice(hostname=host, port=port, read_timeout=None)

    dev.connect()
    assert dev.is_connected() is True

    # the following line will hang forever, don't do this now
    # dev.read()

    dev.disconnect()

    dev = SocketDevice(hostname=host, port=port, read_timeout=1.0)

    dev.connect()
    assert dev.is_connected() is True


def test_sync_connect_invalid_parameters_raises():
    dev = SocketDevice(hostname="", port=1234)
    with pytest.raises(ValueError):
        dev.connect()

    dev = SocketDevice(hostname="127.0.0.1", port=0)
    with pytest.raises(ValueError):
        dev.connect()


def test_sync_connect_failures():
    dev = SocketDevice(hostname="127.0.0.1", port=1234)
    with pytest.raises(ConnectionError):
        dev.connect()

    # Connecting to a non-routable IP address results in a timeout error.
    # The port number doesn't really matter as long as it is not 0 (zero) because
    # that is checked by the SocketDevice constructor

    # dev = SocketDevice(hostname="10.255.255.1", port=25)
    # dev = SocketDevice(hostname="10.255.255.0", port=20)
    dev = SocketDevice(hostname="10.0.0.0", port=1)
    with pytest.raises(TimeoutError):
        dev.connect()

    # Connecting to a server where a port is blocked by the firewall also results in a timeout error
    dev = SocketDevice(hostname="www.google.com", port=81)
    with pytest.raises(TimeoutError):
        dev.connect()

    # Check proper handling of address name errors, " " is an invalid hostname
    dev = SocketDevice(hostname=" ", port=81)
    with pytest.raises(ConnectionError, match="Socket address info error"):
        dev.connect()


def test_sync_reconnect_behaviour(sync_echo_server):
    host, port = sync_echo_server
    dev = SocketDevice(hostname=host, port=port)

    dev.connect()
    assert dev.is_connected() is True

    # reconnect should first disconnect then connect again
    dev.reconnect()
    assert dev.is_connected() is True

    dev.disconnect()
    assert dev.is_connected() is False


@pytest.mark.asyncio
async def test_async_connect_write_trans_and_disconnect(async_echo_server):
    host, port, server, _active_writers = async_echo_server
    dev = AsyncSocketDevice(hostname=host, port=port, connect_timeout=1.0, read_timeout=1.0)

    await dev.connect()
    assert dev.is_connected() is True

    # trans should return bytes that end with ETX and contain the echoed payload
    got = await dev.trans("CMD-ASYNC")
    assert isinstance(got, bytes)
    assert got.endswith(SEPARATOR)
    assert b"RESP:CMD-ASYNC" in got

    # write-only then read via trans
    # since our test server doesn't interpret what is sent and always returns something,
    # you will also find 'W1' in the response of trans(), then need to do a read() again.
    await dev.write("W1:NO-REPLY")
    await asyncio.sleep(0.1)
    assert b"RESP:W2" in await dev.trans("W2")

    # Confirm there is not more data on the socket
    with pytest.raises(DeviceTimeoutError):
        await dev.read()

    # disconnect
    await dev.disconnect()
    assert dev.is_connected() is False


@pytest.mark.asyncio
async def test_async_read_timeout_raises_device_timeout(tmp_path):
    """
    Start a server that accepts data but intentionally does not send the ETX,
    so AsyncSocketDevice.read() should raise DeviceTimeoutError due to read_timeout.
    """

    # handler that reads but does NOT send ETX (simulate stuck/partial response)
    async def partial_handler(reader, writer):
        try:
            _ = await reader.read(4096)  # consume what client sends
            # intentionally do not write ETX back; keep connection open
            await asyncio.sleep(2.0)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(partial_handler, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]

    dev = AsyncSocketDevice(hostname=host, port=port, connect_timeout=1.0, read_timeout=0.2)
    try:
        await dev.connect()
        # write a command; the server won't return ETX so readuntil should time out
        with pytest.raises(DeviceTimeoutError):
            await dev.trans("NOETX")
    finally:
        await dev.disconnect()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_async_cleanup_on_broken_connection(async_echo_server):
    host, port, server, active_writers = async_echo_server
    dev = AsyncSocketDevice(hostname=host, port=port, connect_timeout=1.0, read_timeout=1.0)

    # connect and then shut down server to simulate connection drop
    await dev.connect()
    assert dev.is_connected() is True

    logger.info("Before server close")

    # close server so subsequent reads/writes fail
    await close_server(server, active_writers)

    # reads/writes should raise DeviceConnectionError and device should clean up its state
    with pytest.raises(DeviceConnectionError):
        logger.info("Before read()")
        await dev.read()
        logger.info("After read()")

    with pytest.raises(DeviceConnectionError):
        await dev.write("X")

    assert dev.is_connected() is False
