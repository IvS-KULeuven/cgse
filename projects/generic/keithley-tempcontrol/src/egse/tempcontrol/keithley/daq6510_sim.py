from __future__ import annotations

import contextlib
import datetime
import logging
import re
import socket
import time

import typer
from egse.settings import Settings
from egse.system import SignalCatcher

logger = logging.getLogger("daq6510-sim")

HOST = "localhost"
DAQ_SETTINGS = Settings.load("Keithley DAQ6510")


device_time = datetime.datetime.now(datetime.timezone.utc)
reference_time = device_time


app = typer.Typer(help="DAQ6510 Simulator")

error_msg: str | None = None
"""Global error message, always contains the last error. Reset in the inner loop of run_simulator."""


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


COMMAND_ACTIONS_RESPONSES = {
    "*IDN?": (None, "KEITHLEY INSTRUMENTS, MODEL DAQ6510, SIMULATOR"),
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
    response = f"{response}\n".encode()
    logger.debug(f"write: {response = }")
    conn.sendall(response)


def read(conn) -> str:
    """
    Reads one command string from the socket, i.e. until a linefeed ('\n') is received.

    Returns:
        The command string with the linefeed stripped off.
    """

    n_total = 0
    buf_size = 1024 * 4
    command_string = bytes()

    try:
        for _ in range(100):
            data = conn.recv(buf_size)
            n = len(data)
            n_total += n
            command_string += data
            # if data.endswith(b'\n'):
            if n < buf_size:
                break
    except socket.timeout:
        # This timeout is caught at the caller, where the timeout is set.
        raise

    logger.info(f"read: {command_string=}")

    return command_string.decode().rstrip()


def process_command(command_string: str) -> str:
    global COMMAND_ACTIONS_RESPONSES
    global COMMAND_PATTERNS_ACTIONS_RESPONSES
    global error_msg

    # LOGGER.debug(f"{command_string=}")

    try:
        action, response = COMMAND_ACTIONS_RESPONSES[command_string]
        action and action()
        if error_msg:
            return error_msg
        else:
            return response if isinstance(response, str) else response()
    except KeyError:
        # try to match with a value
        for key, value in COMMAND_PATTERNS_ACTIONS_RESPONSES.items():
            if match := re.match(key, command_string, flags=re.IGNORECASE):
                # LOGGER.debug(f"{match=}, {match.groups()}")
                action, response = value
                # LOGGER.debug(f"{action=}, {response=}")
                action and action(*match.groups())
                return error_msg or (response if isinstance(response, str) or response is None else response())
        return f"ERROR: unknown command string: {command_string}"


def run_simulator():
    global error_msg

    logger.info("Starting the DAQ6510 Simulator")

    killer = SignalCatcher()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, DAQ_SETTINGS.PORT))
        s.listen()
        s.settimeout(2.0)
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
                conn.settimeout(2.0)
                try:
                    while True:
                        error_msg = ""
                        with contextlib.suppress(socket.timeout):
                            data = read(conn)
                            logger.info(f"{data = }")
                            if data.strip() == "STOP":
                                logger.info("Client requested to terminate...")
                                s.close()
                                return
                            for cmd in data.split(";"):
                                response = process_command(cmd.strip())
                                if response is not None:
                                    write(conn, response)
                            if not data:
                                logger.info("Client closed connection, accepting new connection...")
                                break
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


def send_request(cmd: str, type_: str = "query"):
    from egse.tempcontrol.keithley.daq6510_dev import DAQ6510EthernetInterface

    response = None

    daq_dev = DAQ6510EthernetInterface(hostname="localhost", port=5025)
    daq_dev.connect()

    if type_.lower().strip() == "query":
        response = daq_dev.query(cmd)
    elif type_.lower().strip() == "write":
        daq_dev.write(cmd)
    else:
        logger.info(f"Unknown type {type_} for send_request.")

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
def command(type_: str, cmd: str):
    response = send_request(cmd, type_)
    logger.info(f"{response}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(threadName)-12s %(levelname)-8s %(name)-12s %(module)-20s %(message)s",
    )

    app()
