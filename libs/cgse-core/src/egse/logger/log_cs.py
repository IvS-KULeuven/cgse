"""
The Log Server receives all log messages and events from control servers and client applications
and saves those messages in a log file at a given location. The log messages are retrieved over
a ZeroMQ message channel.
"""
__all__ = []

import datetime
import logging
import multiprocessing
import pickle
import sys
from logging import StreamHandler
from logging.handlers import SocketHandler
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

import rich
import typer
import zmq

from egse.env import get_log_file_location
from egse.logger import LOGGER_ID
from egse.logger import get_log_file_name
from egse.logger import send_request
from egse.process import SubProcess
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.signal import FileBasedSignaling
from egse.system import format_datetime
from egse.system import get_caller_info
from egse.system import get_host_ip
from egse.zmq_ser import bind_address
from egse.zmq_ser import get_port_number

CTRL_SETTINGS = Settings.load("Logging Control Server")

LOG_NAME_TO_LEVEL = {
    'CRITICAL': 50,
    'FATAL': 50,
    'ERROR': 40,
    'WARN': 30,
    'WARNING': 30,
    'INFO': 20,
    'DEBUG': 10,
    'NOTSET': 0,
}

# The format for the log file.
# The line that is saved in the log file shall contain as much information as possible.

LOG_FORMAT_FILE = (
    "%(asctime)s:%(processName)s:%(process)s:%(levelname)s:%(lineno)d:%(name)s:%(message)s"
)

LOG_FORMAT_KEY_VALUE = (
    "level=%(levelname)s ts=%(asctime)s process=%(processName)s process_id=%(process)s "
    "name=%(name)s caller=%(filename)s:%(lineno)s function=%(funcName)s msg=\"%(message)s\""
)

LOG_FORMAT_DATE = "%Y-%m-%dT%H:%M:%S,%f"

# The format for the console output.
# The line that is printed on the console shall be concise.

LOG_FORMAT_STREAM = "%(asctime)s:%(levelname)s:%(name)s:%(filename)s:%(funcName)s:%(message)s"

LOG_LEVEL_FILE = logging.DEBUG
LOG_LEVEL_STREAM = logging.ERROR
LOG_LEVEL_SOCKET = 1  # ALL records shall go to the socket handler

LOGGER_NAME = "egse.logger"

PROTOCOL = 'tcp'
RECEIVER_PORT = 0  # dynamically assigned by the system
COMMANDER_PORT = 0  # dynamically assigned by the system

file_handler: Optional[TimedRotatingFileHandler] = None
stream_handler: Optional[StreamHandler] = None
socket_handler: Optional[SocketHandler] = None


class DateTimeFormatter(logging.Formatter):

    def formatTime(self, record, datefmt=None):
        converted_time = datetime.datetime.fromtimestamp(record.created)
        if datefmt:
            return converted_time.strftime(datefmt)
        formatted_time = converted_time.strftime("%Y-%m-%dT%H:%M:%S")
        return f"{formatted_time}.{record.msecs:03.0f}"


file_formatter = DateTimeFormatter(fmt=LOG_FORMAT_KEY_VALUE, datefmt=LOG_FORMAT_DATE)

app_name = "log_cs"
app = typer.Typer(name=app_name, no_args_is_help=True)


@app.command()
def start():
    """Start the Logger Control Server."""

    global file_handler, stream_handler, socket_handler

    multiprocessing.current_process().name = app_name

    log_file_location = Path(get_log_file_location())
    log_file_name = get_log_file_name()

    if not log_file_location.exists():
        raise FileNotFoundError(f"The location for the log files doesn't exist: {log_file_location!s}.")

    file_handler = TimedRotatingFileHandler(filename=log_file_location / log_file_name, when='midnight')
    file_handler.setFormatter(file_formatter)

    # There is no need to set the level for the handlers, because the level is checked by the
    # Logger, and we use the handlers directly here. Use a filter to restrict messages.

    stream_handler = StreamHandler()
    stream_handler.setFormatter(logging.Formatter(fmt=LOG_FORMAT_STREAM))

    # Log records are also sent to the textualog listening server

    socket_handler = SocketHandler(CTRL_SETTINGS.TEXTUALOG_IP_ADDRESS, CTRL_SETTINGS.TEXTUALOG_LISTENING_PORT)
    socket_handler.setFormatter(file_formatter)

    context = zmq.Context.instance()

    endpoint = bind_address(PROTOCOL, RECEIVER_PORT)
    receiver = context.socket(zmq.PULL)
    receiver.bind(endpoint)

    endpoint = bind_address(PROTOCOL, COMMANDER_PORT)
    commander = context.socket(zmq.REP)
    commander.bind(endpoint)

    poller = zmq.Poller()
    poller.register(receiver, zmq.POLLIN)
    poller.register(commander, zmq.POLLIN)

    client = RegistryClient()
    client.connect()
    service_id = client.register(
        name=LOGGER_ID,
        host=get_host_ip() or "127.0.0.1",
        port=get_port_number(commander),
        service_type="LOGGER",
        metadata={
            'receiver_port': get_port_number(receiver),
        }
    )
    if service_id is None:
        record = _create_log_record(logging.ERROR, "Registration of LOGGER service failed.")
        handle_log_record(record)
        return

    client.start_heartbeat()

    def reregister_service(force: bool = False):
        nonlocal service_id

        record = _create_log_record(logging.WARNING, f"Re-registration of Logger {force = }.")
        handle_log_record(record)

        if client.get_service(service_id):
            if force is True:
                client.deregister(service_id)
            else:
                return

        service_id = client.register(
            name=LOGGER_ID,
            host=get_host_ip() or "127.0.0.1",
            port=get_port_number(commander),
            service_type="LOGGER",
            metadata={
                'receiver_port': get_port_number(receiver),
            }
        )
        if service_id is None:
            record = _create_log_record(logging.ERROR, "Registration of LOGGER service failed.")
            handle_log_record(record)

    signaling = FileBasedSignaling(app_name)
    signaling.start_monitoring()
    signaling.register_handler("reregister", reregister_service)

    while True:
        try:
            signaling.process_pending_commands()

            socks = dict(poller.poll(timeout=1000))  # timeout in milliseconds

            if commander in socks:
                pickle_string = commander.recv()
                command = pickle.loads(pickle_string)

                if command.lower() == "quit":
                    commander.send(pickle.dumps("ACK"))
                    break

                response = handle_command(command)
                commander.send(pickle.dumps(response))

            if receiver in socks:
                pickle_string = receiver.recv()
                record = pickle.loads(pickle_string)
                record = logging.makeLogRecord(record)
                handle_log_record(record)

        except KeyboardInterrupt:
            rich.print("KeyboardInterrupt caught!")
            break

    record = _create_log_record(level=logging.WARNING, msg="Logger terminated.")
    handle_log_record(record)

    file_handler.close()
    stream_handler.close()
    commander.close(linger=0)
    receiver.close(linger=0)

    client.stop_heartbeat()
    client.deregister(service_id)
    client.disconnect()


def _create_log_record(level: int, msg: str) -> logging.LogRecord:
    """Create a LogRecord that can be handled by a Handler."""
    caller_info = get_caller_info(level=2)

    record = logging.LogRecord(
        name=LOGGER_NAME,
        level=level,
        pathname=caller_info.filename,
        lineno=caller_info.lineno,
        msg=msg,
        args=(),
        exc_info=None,
        func=caller_info.function,
        sinfo=None
    )

    return record


@app.command()
def start_bg():
    """Start the Logger Control Server in the background."""
    proc = SubProcess("log_cs", ["log_cs", "start"])
    proc.execute()


def handle_log_record(record):
    """Send the log record to the file handler and the stream handler."""
    global file_handler, stream_handler, socket_handler

    if record.levelno >= LOG_LEVEL_FILE:
        file_handler.emit(record)

    if record.levelno >= LOG_LEVEL_STREAM:
        stream_handler.handle(record)

    if record.levelno >= LOG_LEVEL_SOCKET:
        socket_handler.handle(record)


def handle_command(command) -> dict:
    """Handle commands that are sent to the commanding socket."""
    global file_handler
    global LOG_LEVEL_FILE

    response = dict(
        timestamp=format_datetime(),
    )
    if command.lower() == 'roll':
        file_handler.doRollover()
        response.update(dict(status="ACK"))
        record = logging.LogRecord(
            name=LOGGER_NAME,
            level=logging.WARNING,
            pathname=__file__,
            lineno=197,
            msg="Logger rolled over.",
            args=(),
            exc_info=None,
            func="roll",
            sinfo=None
        )
        handle_log_record(record)

    elif command.lower() == 'status':
        with RegistryClient() as client:
            service = client.discover_service("LOGGER")
        if service:
            response.update(dict(
                status="ACK",
                logging_port=service['metadata']['receiver_port'],
                commanding_port=service['port'],
                file_logger_level=logging.getLevelName(LOG_LEVEL_FILE),
                stream_logger_level=logging.getLevelName(LOG_LEVEL_STREAM),
                file_logger_location=file_handler.baseFilename,
            ))
        else:
            response.update(
                dict(status="NACK")
            )
    elif command.lower().startswith("set_level"):
        new_level = command.split()[-1]
        LOG_LEVEL_FILE = LOG_NAME_TO_LEVEL[new_level]
        response.update(dict(
            status="ACK",
            file_logger_level=logging.getLevelName(LOG_LEVEL_FILE),
        ))

    return response


@app.command()
def stop():
    """Stop the Logger Control Server."""

    response = send_request("quit")
    if response == "ACK":
        rich.print("Logger successfully terminated.")
    else:
        rich.print(f"[red] ERROR: {response}")


@app.command()
def roll():
    """Roll over the log file of the Logger Control Server."""

    response = send_request("roll")
    if response.get("status") == "ACK":
        rich.print("[green]Logger files successfully rotated.")
    else:
        rich.print(f"[red]ERROR: {response}")


@app.command()
def status():
    """Roll over the log file of the Logger Control Server."""

    response = send_request("status")
    if response.get("status") == "ACK":
        rich.print("Log Manager:")
        rich.print("    Status: [green]active")
        rich.print(f"    Logging port: {response.get('logging_port')}")
        rich.print(f"    Commanding port: {response.get('commanding_port')}")
        rich.print(f"    Level [grey50](file)[black]: {response.get('file_logger_level')}")
        rich.print(f"    Level [grey50](stdout)[black]: {response.get('stream_logger_level')}")
        rich.print(f"    Log file location: {response.get('file_logger_location')}")
    else:
        rich.print("Log Manager Status: [red]not active")


@app.command()
def test():
    # setup_logging() and teardown_logging() is automatic
    # setup_logging()

    logger = logging.getLogger('egse')
    logger.debug("A DEBUG message")
    logger.info("An INFO message")
    logger.warning("A WARNING message")

    # from egse.logger import print_all_handlers
    # print_all_handlers()

    # teardown_logging()


@app.command()
def set_level(level: str):
    """Set the logging level for """
    try:
        level = logging.getLevelName(int(level))
    except ValueError:
        if level not in LOG_NAME_TO_LEVEL:
            rich.print(f"[red]Invalid logging level given '{level}'.")
            rich.print(f"Should be one of: {', '.join(LOG_NAME_TO_LEVEL.keys())}.")
            return

    response = send_request(f"set_level {level}")
    if response.get("status") == "ACK":
        rich.print(f"Log level on the server is now set to {response.get('file_logger_level')}.")
    else:
        rich.print(f"[red]ERROR: {response}")


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    sys.exit(app())
