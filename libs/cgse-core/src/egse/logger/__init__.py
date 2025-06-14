"""
This module defines the level, format and handlers for the root logger and for the special
'egse' logger. The egse_logger will be configured with a special handler which sends all
logging messages to a log control server.

This module is loaded whenever an egse module is loaded, to ensure all log messages are properly
forwarded to the log control server.
"""

__all__ = [
    "LOGGER_ID",
    "LOG_FORMAT_FULL",
    "logger",
    "close_all_zmq_handlers",
    "create_new_zmq_logger",
    "get_log_file_name",
    "print_all_handlers",
    "replace_zmq_handler",
    "send_request",
    "set_all_logger_levels",
    "setup_logging",
    "teardown_logging",
]

import atexit
import logging
import pickle
import traceback

import zmq

from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.system import is_in_ipython

CTRL_SETTINGS = Settings.load("Logging Control Server")

LOG_FORMAT_FULL = (
    "%(asctime)23s:%(processName)20s:%(levelname)8s:%(name)-25s:%(lineno)5d:%(filename)-20s:%(message)s"
)

LOGGER_ID = "LOGGER"
"""The logger id that is also used as service_tpe for service discovery."""

logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT_FULL)

root_logger = logging.getLogger()
egse_logger = logging.getLogger("egse")

logger = logging.getLogger("egse.logger")

_initialised = False  # will be set to True in the setup_logging() function


def get_log_file_name():
    """
    Returns the filename of the log file as defined in the Settings or return the default name 'general.log'.
    """
    return CTRL_SETTINGS.get("FILENAME", "general.log")


class ZeroMQHandler(logging.Handler):
    def __init__(self, uri=None, socket_type=zmq.PUSH, ctx=None):

        super().__init__()
        # logging.Handler.__init__(self)

        if uri is None:
            try:
                with RegistryClient(request_timeout=500) as reg:
                    # We cannot use `get_endpoint` here, because we need a different port
                    service = reg.discover_service(LOGGER_ID)
                    endpoint = (f"{service.get('protocol', 'tcp')}://"
                                f"{service['host']}:"
                                f"{service['metadata']['receiver_port']}")
            except Exception:  # noqa
                logger.warning(f"Couldn't retrieve endpoint for {LOGGER_ID}. Is the log_cs process running?")
            else:
                uri = endpoint

        if uri:
            # print(f"ZeroMQHandler.__init__({uri=}, {socket_type=}, {ctx=})")

            self.setLevel(logging.NOTSET)

            self.ctx = ctx or zmq.Context.instance()
            self.socket = zmq.Socket(self.ctx, socket_type)
            self.socket.setsockopt(zmq.SNDHWM, 0)  # never block on sending msg
            # self.socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1 second
            # self.socket.setsockopt(zmq.SNDTIMEO, 1000)  # 1 second
            self.socket.setsockopt(zmq.LINGER, 100)  # short wait for unsent messages on close()
            self.socket.setsockopt(zmq.IMMEDIATE, 1)  # set immediate mode
            self.socket.connect(uri)

            logger.debug(f"All logging messages will be forwarded to the LOGGER at {endpoint}.")
        else:
            self.ctx = None
            self.socket = None

            logger.warning("No logging messages will be forwarded to the LOGGER")

    def __del__(self):
        self.close()

    def close(self):
        if self.socket:
            self.socket.close(linger=100)
            self.socket = None

    def emit(self, record):
        """
        Emit a record.

        Writes the LogRecord to the queue, preparing it for pickling first.
        """

        # print(f"ZeroMQHandler.emit({record})")

        if not self.socket:
            return

        try:
            if record.exc_info:
                record.exc_text = traceback.format_exc()
                record.exc_info = None  # traceback objects can not be pickled
            if record.processName == "MainProcess" and is_in_ipython():
                record.processName = "IPython"
            data = pickle.dumps(record.__dict__)
            self.socket.send(data, flags=zmq.NOBLOCK)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            logger.error(f"ZeroMQHandler: Exception - {exc}", exc_info=True)
            self.handleError(record)


def print_all_handlers():
    """A debugging function to check which handlers are connected to loggers."""

    print("=" * 80)
    print("Root logger handlers:")
    for i, handler in enumerate(logging.root.handlers):
        print(f"  {i}: {type(handler).__name__} - {handler}")

    print("\nAll loggers with handlers:")
    for name, logger in logging.Logger.manager.loggerDict.items():
        if hasattr(logger, 'handlers') and logger.handlers:
            print(f"  {name}: {[type(h).__name__ for h in logger.handlers]}")

    print("\n" + "=" * 80)


def close_all_zmq_handlers():
    """
    Close all the ZeroMQHandlers that are connected to a logger.

    This function is automatically called upon termination of the control servers. For your own
    applications, call this function before exiting the App.
    """

    loggers = logging.Logger.manager.loggerDict

    for name, logger in loggers.items():
        if isinstance(logger, logging.PlaceHolder):
            continue
        for handler in logger.handlers:
            if isinstance(handler, ZeroMQHandler):
                root_logger.debug(f"Closing ZeroMQHandler for logger {name}")
                handler.close()


def setup_logging(uri: str = None):
    # Initialize logging as we want it for the Common-EGSE
    #
    # * The ZeroMQHandler to send all logging messages, i.e. level=DEBUG to the Logging Server
    # * The (local) StreamingHandlers to print only INFO messages and higher

    global root_logger, egse_logger, _initialised

    if _initialised:
        return

    logging.disable(logging.NOTSET)
    for handler in root_logger.handlers:
        handler.setLevel(logging.INFO)

    egse_logger.setLevel(logging.DEBUG)

    # Add the ZeroMQHandler to the egse_logger

    zmq_handler = ZeroMQHandler(uri)
    zmq_handler.setLevel(logging.NOTSET)
    egse_logger.addHandler(zmq_handler)

    _initialised = True


def teardown_logging():
    close_all_zmq_handlers()


setup_logging()
atexit.register(teardown_logging)


def replace_zmq_handler():
    """
    This function will replace the current ZeroMQ Handler with a new instance. Use this function
    in the run() method of a multiprocessing.Process:

        >>> import egse.logger
        >>> egse.logger.replace_zmq_handler()

    Don't use this function in the __init__() method as only the run() method will execute in
    the new Process and replace the handler in the proper environment. The reason for this is
    that the ZeroMQ socket is not thread/Process safe, so a new ZeroMQ socket needs to be created
    in the correct process environment.
    """
    global egse_logger

    this_handler = None
    for handler in egse_logger.handlers:
        if isinstance(handler, ZeroMQHandler):
            this_handler = handler
    if this_handler is not None:
        egse_logger.removeHandler(this_handler)
    egse_logger.addHandler(ZeroMQHandler())


def create_new_zmq_logger(name: str) -> logging.Logger:
    """
    Create a new logger with the given name and add a ZeroMQ Handler to this logger.

    If the logger already has a ZeroMQ handler attached, don't add a second ZeroMQ handler,
    just return the Logger object.

    Args:
        name: the requested name for the logger

    Returns:
        A Logger for the given name with a ZeroMQ handler attached.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # If the ZeroMQ handler already exists for this logger, don't add a second handler

    for handler in logger.handlers:
        if isinstance(handler, ZeroMQHandler):
            return logger

    zmq_handler = ZeroMQHandler()
    zmq_handler.setLevel(logging.NOTSET)

    logger.addHandler(zmq_handler)
    logger.setLevel(logging.DEBUG)

    return logger


def set_all_logger_levels(level: int):
    global root_logger, egse_logger

    root_logger.level = level
    egse_logger.level = level

    for handler in root_logger.handlers:
        handler.setLevel(level)

    # We don't want to restrict egse_logger levels

    # for handler in egse_logger.handlers:
    #     handler.setLevel(level)


TIMEOUT_RECV = 1.0  # seconds


def send_request(command_request: str):
    """Sends a request to the Logger Control Server and waits for a response."""
    ctx = zmq.Context.instance()

    with RegistryClient() as client:
        endpoint = client.get_endpoint(LOGGER_ID)

    if endpoint is None:
        return {"error": "The log_cs has not been registered as a service."}

    socket = ctx.socket(zmq.REQ)
    socket.connect(endpoint)

    socket.send(pickle.dumps(command_request))
    rlist, _, _ = zmq.select([socket], [], [], timeout=TIMEOUT_RECV)
    if socket in rlist:
        response = socket.recv()
        response = pickle.loads(response)
    else:
        response = {"error": "The ZeroMQ socket timed out for the Logger Control Server."}
    socket.close(linger=0)

    return response
