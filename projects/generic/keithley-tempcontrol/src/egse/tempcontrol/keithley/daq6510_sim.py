import datetime
import logging
import re
import socket

import contextlib

import rich
import typer

from egse.settings import Settings
from egse.system import SignalCatcher

logging.basicConfig(level=logging.DEBUG)

_LOGGER = logging.getLogger("egse.daq6510.sim")

HOST = "localhost"
DAQ_SETTINGS = Settings.load("Keithley DAQ6510")


device_time = datetime.datetime.now(datetime.timezone.utc)
reference_time = device_time


app = typer.Typer(help="DAQ6510 Simulator")


def create_datetime(year, month, day, hour, minute, second):
    global device_time, reference_time
    device_time = datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc)
    reference_time = datetime.datetime.now(datetime.timezone.utc)


def nothing():
    return None


def set_time(year, month, day, hour, minute, second):
    print(f"TIME {year}, {month}, {day}, {hour}, {minute}, {second}")
    create_datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))


def get_time():
    current_device_time = device_time + (datetime.datetime.now(datetime.timezone.utc) - reference_time)
    msg = current_device_time.strftime("%a %b %d %H:%M:%S %Y")
    print(f":SYST:TIME? {msg = }")
    return msg


def beep(a, b):
    print(f"BEEP {a=}, {b=}")


def reset():
    print("RESET")


COMMAND_ACTIONS_RESPONSES = {
    "*IDN?": (None, "KEITHLEY INSTRUMENTS, MODEL DAQ6510, SIMULATOR"),
}


COMMAND_PATTERNS_ACTIONS_RESPONSES = {
    r":?\*RST": (reset, None),
    r":?SYST(?:em)*:TIME (\d+), (\d+), (\d+), (\d+), (\d+), (\d+)": (set_time, None),
    r":?SYST(?:em)*:TIME\? 1": (nothing, get_time),
    r":?SYST(?:em)*:BEEP(?:er)* (\d+), (\d+(?:\.\d+)?)": (beep, None),
}


def write(conn, response: str):

    response = f"{response}\n".encode()
    _LOGGER.debug(f"write: {response = }")
    conn.sendall(response)


def read(conn) -> str:
    """
    Reads one command string from the socket, i.e. until a linefeed ('\n') is received.

    Returns:
        The command string with the linefeed stripped off.
    """

    idx, n_total = 0, 0
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
    except socket.timeout as e_timeout:
        # LOGGER.warning(f"Socket timeout error from {e_timeout}")
        # This timeout is catched at the caller, where the timeout is set.
        raise

    # _LOGGER.debug(f"Total number of bytes received is {n_total}, idx={idx}")
    _LOGGER.info(f"read: {command_string=}")

    return command_string.decode().rstrip()


def process_command(command_string: str) -> str:

    global COMMAND_ACTIONS_RESPONSES
    global COMMAND_PATTERNS_ACTIONS_RESPONSES

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
            if match := re.match(key, command_string):
                # LOGGER.debug(f"{match=}, {match.groups()}")
                action, response = value
                # LOGGER.debug(f"{action=}, {response=}")
                action and action(*match.groups())
                return error_msg or (response if isinstance(response, str) or response is None else response())
        return f"ERROR: unknown command string: {command_string}"


def run_simulator():
    global error_msg

    _LOGGER.info("Starting the DAQ6510 Simulator")

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
                _LOGGER.info(f'Accepted connection from {addr}')
                write(conn, 'This is PLATO DAQ6510 X.X.sim')
                conn.settimeout(2.0)
                try:
                    error_msg = ""
                    while True:
                        with contextlib.suppress(socket.timeout):
                            data = read(conn)
                            _LOGGER.info(f"{data = }")
                            if data.strip() == "STOP":
                                _LOGGER.info("Client requested to terminate...")
                                s.close()
                                return
                            for cmd in data.split(';'):
                                response = process_command(cmd.strip())
                                if response is not None:
                                    write(conn, response)
                            if not data:
                                _LOGGER.info("Client closed connection, accepting new connection...")
                                break
                        if killer.term_signal_received:
                            _LOGGER.info("Terminating...")
                            s.close()
                            return
                        if killer.user_signal_received:
                            if killer.signal_name == "SIGUSR1":
                                _LOGGER.info("SIGUSR1 is not supported by this simulator")
                            if killer.signal_name == "SIGUSR2":
                                _LOGGER.info("SIGUSR2 is not supported by this simulator")
                            killer.clear()

                except ConnectionResetError as exc:
                    _LOGGER.info(f"ConnectionResetError: {exc}")
                except Exception as exc:
                    _LOGGER.info(f"{exc.__class__.__name__} caught: {exc.args}")


def send_request(cmd: str):

    from egse.tempcontrol.keithley.daq6510_devif import DAQ6510EthernetInterface

    daq_dev = DAQ6510EthernetInterface(hostname="localhost", port=5025)
    daq_dev.connect()

    response = daq_dev.query(cmd)

    daq_dev.disconnect()

    return response


@app.command()
def start():
    run_simulator()


@app.command()
def status():
    response = send_request("*IDN?")
    print(f"{response}")


@app.command()
def stop():
    response = send_request("STOP")
    print(f"{response}")


if __name__ == '__main__':
    app()
