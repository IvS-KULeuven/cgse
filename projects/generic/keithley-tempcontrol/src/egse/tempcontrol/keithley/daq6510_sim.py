"""
Keithley DAQ6510 simulator.

A socket server on the SCPI port of the DAQ6510 that passes every command to a `DAQ6510Model`. The model keeps
a reading buffer that is filled by a background scan, so the control server can be run without hardware:

    $ daq6510_sim start
    $ daq6510_cs start --auto-scan --setup-file SETUP.yaml

Set the HOSTNAME of the "Keithley DAQ6510" settings to localhost to connect to the simulator.
"""

import contextlib
import socket
import threading
from typing import Annotated

import typer

from egse.env import bool_env
from egse.log import logging
from egse.settings import Settings
from egse.system import SignalCatcher
from egse.tempcontrol.keithley.daq6510_model import DAQ6510Model

logger = logging.getLogger("egse.daq6510-sim")

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")
HOST = "localhost"
DAQ_SETTINGS = Settings.load("Keithley DAQ6510")

READ_TIMEOUT = 2.0
"""The timeout set on the connection socket, applicable when reading from the socket with `recv`."""
CONNECTION_TIMEOUT = 2.0
"""The timeout set on the socket before accepting a connection."""

SEPARATOR = b"\n"
SEPARATOR_STR = SEPARATOR.decode()

app = typer.Typer(help="DAQ6510 Simulator")

model = DAQ6510Model()
"""The simulated device, it keeps its state across client connections."""
model_lock = threading.Lock()
"""Serializes the commands of all clients, the model is not thread-safe."""


def write(conn, response: str):
    response_b = f"{response}{SEPARATOR_STR}".encode()
    if VERBOSE_DEBUG:
        logger.debug(f"write: {response_b = }")
    conn.sendall(response_b)


# Keep a receive buffer per connection
_recv_buffers: dict[int, bytes] = {}


def read(conn) -> str:
    """
    Read bytes from `conn` until a `SEPARATOR` is found (or connection closed / timeout).
    Returns the first chunk (separator stripped). Any bytes after the separator are kept
    in a per-connection buffer for the next call.
    """
    fileno = conn.fileno()
    buf = _recv_buffers.get(fileno, b"")

    try:
        while True:
            # If we already have a full line in the buffer, split and return it.
            if SEPARATOR in buf:
                line, rest = buf.split(SEPARATOR, 1)
                _recv_buffers[fileno] = rest
                logger.debug(f"read: {line=}")
                return line.decode().rstrip()

            # Read more data
            data = conn.recv(1024 * 4)
            if not data:
                # Connection closed by peer; return whatever we have (may be empty)
                _recv_buffers.pop(fileno, None)
                logger.info(f"read (connection closed): {buf=}")
                return buf.decode().rstrip()
            buf += data
            _recv_buffers[fileno] = buf

    except socket.timeout:
        # If we have accumulated data without a separator, return it (partial read),
        # otherwise propagate the timeout so caller can handle/suppress it.
        if buf:
            _recv_buffers[fileno] = buf
            logger.info(f"read (timeout, partial): {buf=}")
            return buf.decode().rstrip()
        raise


def process_command(command_string: str) -> str | None:
    """Process the given command string and return a response."""

    if VERBOSE_DEBUG:
        logger.debug(f"{command_string=}")

    with model_lock:
        response = model.process(command_string)

    if VERBOSE_DEBUG:
        logger.debug(f"{response=}")

    return response


def handle_connection(conn: socket.socket, addr, stop: threading.Event):
    """Serves one client until it closes the connection or the simulator is stopped. Runs in its own thread."""
    with conn:
        logger.info(f"Accepted connection from {addr}")
        # The DAQ6510 doesn't send a string after connection
        conn.settimeout(READ_TIMEOUT)
        try:
            while not stop.is_set():
                with contextlib.suppress(socket.timeout):
                    data = read(conn)
                    if VERBOSE_DEBUG:
                        logger.debug(f"{data = }")
                    if not data:
                        logger.info(f"Client {addr} closed connection.")
                        return
                    if data.strip() == "STOP":
                        logger.info("Client requested to terminate...")
                        stop.set()
                        return
                    response = process_command(data.strip())
                    if response is not None:
                        write(conn, response)
        except ConnectionResetError as exc:
            logger.info(f"ConnectionResetError: {exc}")
        except Exception as exc:
            logger.info(f"{exc.__class__.__name__} caught: {exc.args}")


def run_simulator():
    """Accepts client connections and serves each of them in a separate thread, like the real device which
    accepts multiple connections on its SCPI port. All clients talk to the same model."""
    logger.info("Starting the DAQ6510 Simulator")

    killer = SignalCatcher()
    stop = threading.Event()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, DAQ_SETTINGS.PORT))
        s.listen()
        s.settimeout(CONNECTION_TIMEOUT)
        while not stop.is_set():
            with contextlib.suppress(socket.timeout):
                conn, addr = s.accept()
                threading.Thread(target=handle_connection, args=(conn, addr, stop), daemon=True).start()
            if killer.term_signal_received:
                logger.info("Terminating...")
                stop.set()
            if killer.user_signal_received:
                logger.info(f"{killer.signal_name} is not supported by this simulator")
                killer.clear()


class SimulatorClient:
    """A minimal blocking client for the simulator CLI commands.

    This deliberately doesn't use the DAQ6510 driver, so a problem in the driver can't hide the state of the
    simulator.

    Raises:
        ConnectionError: when the simulator is not running.
        TimeoutError: when the simulator doesn't answer a query in time.
    """

    def __init__(self, hostname: str = HOST, port: int | None = None, timeout: float = 5.0):
        self.hostname = hostname
        self.port = port or DAQ_SETTINGS.PORT
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buffer = b""

    def __enter__(self):
        self._sock = socket.create_connection((self.hostname, self.port), timeout=self.timeout)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sock.close()
        self._sock = None

    def write(self, command: str):
        self._sock.sendall(command.encode() + SEPARATOR)

    def query(self, command: str) -> str:
        self.write(command)
        while SEPARATOR not in self._buffer:
            data = self._sock.recv(4096)
            if not data:
                raise ConnectionError("The simulator closed the connection.")
            self._buffer += data
        line, self._buffer = self._buffer.split(SEPARATOR, 1)
        return line.decode().strip()


def _not_running():
    print(f"DAQ6510 simulator: not running (no connection on {HOST}:{DAQ_SETTINGS.PORT})")
    raise typer.Exit(1)


def _not_responding():
    print(f"DAQ6510 simulator: not responding on {HOST}:{DAQ_SETTINGS.PORT}")
    print("  The port accepts connections, but the simulator doesn't answer, it might be busy with another client.")
    raise typer.Exit(1)


@app.command()
def start():
    run_simulator()


@app.command()
def status():
    """Prints the status of the simulator: identification, scan state and buffer content.

    The exit code is 1 when the simulator is not running.
    """
    queries = {
        "identification": "*IDN?",
        "scan state": "ROUT:SCAN:STAT?",
        "readings in defbuffer1": 'TRAC:ACT? "defbuffer1"',
        "device time": "SYST:TIME? 1",
    }
    try:
        with SimulatorClient() as sim:
            info = {name: sim.query(cmd) for name, cmd in queries.items()}
    except ConnectionError:
        _not_running()
    except TimeoutError:
        _not_responding()

    print(f"DAQ6510 simulator: running on {HOST}:{DAQ_SETTINGS.PORT}")
    for name, value in info.items():
        print(f"  {name}: {value}")


@app.command()
def stop():
    """Stops the simulator."""
    try:
        with SimulatorClient() as sim:
            sim.write("STOP")
    except ConnectionError:
        _not_running()
    print("DAQ6510 simulator: stop requested")


@app.command()
def command(
    cmd: str,
    cmd_type: Annotated[str, typer.Argument(help="either 'write', 'query'")] = "query",
):
    """Send an SCPI command directly to the simulator and print the response of a query."""
    cmd_type = cmd_type.lower().strip()
    if cmd_type not in ("query", "write"):
        print(f"Unknown command type {cmd_type!r}, use 'query' or 'write'.")
        raise typer.Exit(2)

    try:
        with SimulatorClient() as sim:
            if cmd_type == "query":
                print(sim.query(cmd))
            else:
                sim.write(cmd)
    except ConnectionError:
        _not_running()
    except TimeoutError:
        _not_responding()


if __name__ == "__main__":
    app()
