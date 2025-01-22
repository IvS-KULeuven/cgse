"""
The Log Server receives all log messages and events from control servers and client applications
and saves those messages in a log file at a given location. The log messages are retrieved over
a ZeroMQ message channel.
"""
import datetime
import logging
import multiprocessing
import pickle
from logging import StreamHandler
from logging.handlers import SocketHandler
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional
from typing import Union

import click
import rich
import zmq
from prometheus_client import Counter
from prometheus_client import start_http_server

from egse.env import get_log_file_location

from egse.logger import get_log_file_name
from egse.logger import send_request
from egse.process import SubProcess
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

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
    "caller=%(name)s:%(lineno)s msg=\"%(message)s\""
)

LOG_FORMAT_DATE = "%Y-%m-%dT%H:%M:%S,%f"

# The format for the console output.
# The line that is printed on the console shall be concise.

LOG_FORMAT_STREAM = "%(asctime)s:%(levelname)s:%(name)s:%(message)s"

LOG_RECORDS = Counter(
    "log_records_count", "Count the number of log records processed", ["source", "name"]
)

LOG_LEVEL_FILE = logging.DEBUG
LOG_LEVEL_STREAM = logging.ERROR
LOG_LEVEL_SOCKET = 1  # ALL records shall go to the socket handler

LOGGER_NAME = "egse.logger.log_cs"

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


@click.group()
def cli():
    pass


@cli.command()
def start():
    """Start the Logger Control Server."""

    global file_handler, stream_handler, socket_handler

    multiprocessing.current_process().name = "log_cs"

    start_http_server(CTRL_SETTINGS.METRICS_PORT)

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

    context = zmq.Context()

    endpoint = bind_address(CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.LOGGING_PORT)
    receiver = context.socket(zmq.PULL)
    receiver.bind(endpoint)

    endpoint = bind_address(CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.COMMANDING_PORT)
    commander = context.socket(zmq.REP)
    commander.bind(endpoint)

    poller = zmq.Poller()
    poller.register(receiver, zmq.POLLIN)
    poller.register(commander, zmq.POLLIN)

    while True:
        try:
            socks = dict(poller.poll())

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
            click.echo("KeyboardInterrupt caught!")
            break

    record = logging.LogRecord(
        name=LOGGER_NAME,
        level=logging.WARNING,
        pathname=__file__,
        lineno=137,
        msg="Logger terminated.",
        args=(),
        exc_info=None,
        func="start",
        sinfo=None
    )
    handle_log_record(record)

    file_handler.close()
    stream_handler.close()
    commander.close(linger=0)
    receiver.close(linger=0)


@cli.command()
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

    LOG_RECORDS.labels(source="all", name="all").inc()
    LOG_RECORDS.labels(source="logger", name=record.name).inc()
    LOG_RECORDS.labels(source="process", name=record.processName).inc()


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
        response.update(dict(
            status="ACK",
            file_logger_level=logging.getLevelName(LOG_LEVEL_FILE),
            stream_logger_level=logging.getLevelName(LOG_LEVEL_STREAM),
            file_logger_location=file_handler.baseFilename,
        ))
    elif command.lower().startswith("set_level"):
        new_level = command.split()[-1]
        LOG_LEVEL_FILE = LOG_NAME_TO_LEVEL[new_level]
        response.update(dict(
            status="ACK",
            file_logger_level=logging.getLevelName(LOG_LEVEL_FILE),
        ))

    return response


@cli.command()
def stop():
    """Stop the Logger Control Server."""

    response = send_request("quit")
    if response == "ACK":
        rich.print("Logger successfully terminated.")
    else:
        rich.print(f"[red] ERROR: {response}")


@cli.command()
def roll():
    """Roll over the log file of the Logger Control Server."""

    response = send_request("roll")
    if response.get("status") == "ACK":
        rich.print("[green]Logger files successfully rotated.")
    else:
        rich.print(f"[red]ERROR: {response}")


@cli.command()
def status():
    """Roll over the log file of the Logger Control Server."""

    response = send_request("status")
    if response.get("status") == "ACK":
        rich.print("Log Manager:")
        rich.print("    Status: [green]active")
        rich.print(f"    Level [grey50](file)[black]: {response.get('file_logger_level')}")
        rich.print(f"    Level [grey50](stdout)[black]: {response.get('stream_logger_level')}")
        rich.print(f"    Log file location: {response.get('file_logger_location')}")
    else:
        rich.print("Log Manager Status: [red]not active")


@cli.command()
@click.argument('level')
def set_level(level: Union[int, str]):
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
    cli()
