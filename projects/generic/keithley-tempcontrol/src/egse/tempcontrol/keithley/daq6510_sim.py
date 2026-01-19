import contextlib
import datetime
import re
import socket
import time
from functools import partial
from typing import Annotated

import typer

from egse.env import bool_env
from egse.log import logging
from egse.settings import Settings
from egse.system import SignalCatcher

logger = logging.getLogger("egse.daq6510-sim")

VERSION = "0.1.0"
VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")
HOST = "localhost"
DAQ_SETTINGS = Settings.load("Keithley DAQ6510")

READ_TIMEOUT = 2.0
"""The timeout set on the connection socket, applicable when reading from the socket with `recv`."""
CONNECTION_TIMEOUT = 2.0
"""The timeout set on the socket before accepting a connection."""

SEPARATOR = b"\n"
SEPARATOR_STR = SEPARATOR.decode()

device_time = datetime.datetime.now(datetime.timezone.utc)
reference_time = device_time


app = typer.Typer(help="DAQ6510 Simulator")

error_msg: str = ""
"""Global error message, always contains the last error. Reset to an empty string in the inner loop of run_simulator."""


def create_datetime(year, month, day, hour, minute, second):
    global device_time, reference_time
    device_time = datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc)
    reference_time = datetime.datetime.now(datetime.timezone.utc)


def nothing():
    return None


def set_time(year, month, day, hour, minute, second):
    logger.info(f"TIME {year}, {month}, {day}, {hour}, {minute}, {second}")
    create_datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))


def get_time():
    current_device_time = device_time + (datetime.datetime.now(datetime.timezone.utc) - reference_time)
    msg = current_device_time.strftime("%a %b %d %H:%M:%S %Y")
    logger.info(f":SYST:TIME? {msg = }")
    return msg


def beep(a, b):
    logger.info(f"BEEP {a=}, {b=}")


def block(secs: str):
    logger.info(f"Blocking execution for {secs} seconds.")
    time.sleep(float(secs))


def reset():
    logger.info("RESET")


def log(level: int, msg: str):
    logger.log(level, msg)


COMMAND_ACTIONS_RESPONSES = {
    "*IDN?": (None, f"KEITHLEY INSTRUMENTS,DAQ6510,SIMULATOR,{VERSION}"),
    "*ACTION-RESPONSE?": (partial(log, logging.INFO, "Requested action with response."), get_time),
    "*ACTION-NO-RESPONSE": (partial(log, logging.INFO, "Requested action without response."), None),
}

# Check the regex at https://regex101.com

COMMAND_PATTERNS_ACTIONS_RESPONSES = {
    r":?\*RST": (reset, None),
    r":?SYST(?:em)*:TIME (\d+), (\d+), (\d+), (\d+), (\d+), (\d+)": (set_time, None),
    r":?SYST(?:em)*:TIME\? 1": (nothing, get_time),
    r":?SYST(?:em)*:BEEP(?:er)* (\d+), (\d+(?:\.\d+)?)": (beep, None),
    # Command to test how the software reacts if the device is busy and blocked
    r"BLOCK:TIME (\d+(?:\.\d+)?)": (block, None),
}


def write(conn, response: str):
    response = f"{response}{SEPARATOR_STR}".encode()
    if VERBOSE_DEBUG:
        logger.debug(f"write: {response = }")
    conn.sendall(response)


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
                logger.info(f"read: {line=}")
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
    global COMMAND_ACTIONS_RESPONSES
    global COMMAND_PATTERNS_ACTIONS_RESPONSES
    global error_msg

    if VERBOSE_DEBUG:
        logger.debug(f"{command_string=}")

    try:
        action, response = COMMAND_ACTIONS_RESPONSES[command_string]
        if VERBOSE_DEBUG:
            logger.debug(f"{action=}, {response=}")

        if action:
            action()

        if response:
            if error_msg:
                return error_msg
            else:
                return response() if callable(response) else response
        else:
            if error_msg:
                logger.error(f"Error occurred during process command: {error_msg}")
            return None
    except KeyError:
        # try to match with a value
        for key, value in COMMAND_PATTERNS_ACTIONS_RESPONSES.items():
            if match := re.match(key, command_string, flags=re.IGNORECASE):
                if VERBOSE_DEBUG:
                    logger.debug(f"{match=}, {match.groups()}")
                action, response = value
                if VERBOSE_DEBUG:
                    logger.debug(f"{action=}, {response=}")

                if action:
                    action(*match.groups())

                if response:
                    if error_msg:
                        return error_msg
                    else:
                        return response() if callable(response) else response
                else:
                    if error_msg:
                        logger.error(f"Error occurred during process command: {error_msg}")
                    return None

        logger.error(f"ERROR: unknown command string: {command_string}")
        return None


def run_simulator():
    global error_msg

    logger.info("Starting the DAQ6510 Simulator")

    killer = SignalCatcher()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, DAQ_SETTINGS.PORT))
        s.listen()
        s.settimeout(CONNECTION_TIMEOUT)
        while True:
            while True:
                with contextlib.suppress(socket.timeout):
                    conn, addr = s.accept()
                    break
                if killer.term_signal_received:
                    return
            with conn:
                logger.info(f"Accepted connection from {addr}")
                write(conn, "This is PLATO DAQ6510 X.X.sim")
                conn.settimeout(READ_TIMEOUT)
                try:
                    while True:
                        error_msg = ""
                        with contextlib.suppress(socket.timeout):
                            data = read(conn)
                            if VERBOSE_DEBUG:
                                logger.debug(f"{data = }")
                            if not data:
                                logger.info("Client closed connection, accepting new connection...")
                                break
                            if data.strip() == "STOP":
                                logger.info("Client requested to terminate...")
                                s.close()
                                return
                            for cmd in data.split(";"):
                                response = process_command(cmd.strip())
                                if response is not None:
                                    write(conn, response)
                        if killer.term_signal_received:
                            logger.info("Terminating...")
                            s.close()
                            return
                        if killer.user_signal_received:
                            if killer.signal_name == "SIGUSR1":
                                logger.info("SIGUSR1 is not supported by this simulator")
                            if killer.signal_name == "SIGUSR2":
                                logger.info("SIGUSR2 is not supported by this simulator")
                            killer.clear()

                except ConnectionResetError as exc:
                    logger.info(f"ConnectionResetError: {exc}")
                except Exception as exc:
                    logger.info(f"{exc.__class__.__name__} caught: {exc.args}")


def send_request(cmd: str, cmd_type: str = "query") -> str | None:
    from egse.tempcontrol.keithley.daq6510_dev import DAQ6510

    response = None

    daq_dev = DAQ6510(hostname="localhost", port=5025)
    daq_dev.connect()

    if cmd_type.lower().strip() == "query":
        response = daq_dev.query(cmd)
    elif cmd_type.lower().strip() == "write":
        daq_dev.write(cmd)
    else:
        logger.info(f"Unknown command type {cmd_type} for send_request.")

    daq_dev.disconnect()

    return response


@app.command()
def start():
    run_simulator()


@app.command()
def status():
    response = send_request("*IDN?")
    logger.info(f"{response}")


@app.command()
def stop():
    response = send_request("STOP", "write")
    logger.info(f"{response}")


@app.command()
def command(
    cmd: str,
    cmd_type: Annotated[str, typer.Argument(help="either 'write', 'query'")] = "query",
):
    """Send an SCPI command directly to the simulator. The response will be in the log info."""
    response = send_request(cmd, cmd_type)
    logger.info(f"{response}")


if __name__ == "__main__":
    app()
