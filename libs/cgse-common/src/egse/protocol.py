"""
CommandProtocol is a base class for communicating commands with the hardware or
the control server. This class implements methods to send command messages and
receive responses.

The protocol also knows how to load the commands from the YAML file that contains
command definitions.

"""
from __future__ import annotations

import abc
import inspect
import logging
import pickle

from prometheus_client import Counter
from prometheus_client import Summary

from egse.command import Command
from egse.command import CommandExecution
from egse.control import ControlServer
from egse.response import Failure
from egse.device import DeviceConnectionObserver
from egse.system import format_datetime
from egse.zmq_ser import bind_address

logger = logging.getLogger(__name__)

COMMAND_REQUESTS = Counter("cs_command_requests_count", "Count the number of commands", ["target"])
EXECUTION_TIME = Summary("cs_command_execution_time_seconds", "Time spent executing a command")


def get_method(parent_obj, method_name: str):
    """
    Returns a bound method from a given class instance.

    Args:
        parent_obj: the class instance that provides the method
        method_name: name of the method that is requested

    Returns:
        the method [type: method].

    .. note::
        The method returned is an bound class instance method and therefore
        this method *does not* expects as its first argument the class
        instance, i.e. self, when you call this as a function.

    """
    if method_name is None or method_name == "None":
        return None

    if hasattr(parent_obj, method_name):
        method = getattr(parent_obj, method_name)
        if inspect.ismethod(method) or hasattr(method, "__method_wrapper"):
            return method
        logger.warning(f"{method_name} is not a method, type={type(method)}")
    else:
        logger.warning(f"{parent_obj!r} has no method called {method_name}")

    return None


def get_function(parent_class, method_name: str):
    """
    Returns a function (unbound method) from a given class.

    Args:
        parent_class: the class that provides the method
        method_name: name of the method that is requested

    Returns:
        the method [type: function].

    .. note::
        The function returned is an unbound class instance method and
        therefore this function expects as its first argument the class
        instance, i.e. self, when you call it as a function.

    """
    if method_name is None or method_name == "None":
        return None

    if hasattr(parent_class, method_name):
        func = getattr(parent_class, method_name)
        if inspect.isfunction(func):
            return func
        logger.warning(f"{method_name} is not a function, type={type(func)}")
    else:
        logger.warning(
            f"{parent_class.__module__}.{parent_class.__name__} has no method called {method_name}"
        )

    return None


class BaseCommandProtocol(DeviceConnectionObserver):

    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.__socket = None
        self.__control_server = control_server

    def bind(self, socket):
        """Bind to a socket to listen for commands."""
        self.__socket = socket
        self.__socket.bind(self.get_bind_address())

    def get_bind_address(self):
        """
        Returns a string with the bind address, the endpoint, for accepting connections
        and bind a socket to.

        This method should be implemented by the sub-class since it contains the protocol
        and port number that are specific for the sub-class.

        Returns:
            a string with the protocol and port to bind a socket to.
        """
        return bind_address(
            self.__control_server.get_communication_protocol(),
            self.__control_server.get_commanding_port(),
        )

    def is_alive(self) -> bool:
        """
        This method can be overridden by a sub-class to check whether any Thread or sub-process
        that was started is still alive.
        """
        return True

    def get_control_server(self):
        return self.__control_server

    def get_status(self):
        """
        Returns a dictionary with status information for the control server, enhanced by the
        sub-class with device specific status information.

        This method should be implemented/overridden by the sub-class. The sub-class specific
        method should update the dictionary returned by this super-class method with device
        specific status values.

        The dict returned by this method includes the following keywords:

        * timestamp (str): a string representation of the current datetime
        * PID (int): the Process ID for the control server
        * Up (float): the uptime of the control server [s]
        * UUID (uuid1): a UUID for the control server
        * RSS (int): the 'Resident Set Size', this is the non-swapped physical memory a process
            has used [byte]
        * USS (int): the 'Unique Set Size', this is the memory which is unique to a process [byte]
        * CPU User (float): time spent in user mode [s]
        * CPU System (float): time spent in kernel mode [s]
        * CPU% (float): the process CPU utilization as a percentage [%]

        Check the documentation for `psutil.Process` for more in-depth information about the
        dict keys.

        Returns:
            a dictionary with status information.
        """
        status = {
            "timestamp": format_datetime(),
            "delay": self.__control_server.delay,
        }
        status.update(self.__control_server.get_process_status())
        return status

    def get_housekeeping(self) -> dict:
        """Returns a dictionary with housekeeping information about the device."""
        raise NotImplementedError(
            f"The get_housekeeping() method shall be implemented for {self.__class__.__name__}."
        )

    def get_device(self):
        """Returns the device object for the device that is controlled by this protocol."""
        raise NotImplementedError

    def send(self, data):
        """
        Send a message to the ControlServer. The message shall be fully populated
        and is only serialized before sending over the ZeroMQ socket.

        FIXME: We need to add error handling here, e.g. what if the send() fails? Do we need
               to implement retries as with Proxy?
        """
        pickle_string = pickle.dumps(data)
        self.__socket.send(pickle_string)

    def receive(self):
        """
        Receive a serialized message from the ControlServer. The message will not
        be decoded/de-serialized, but is returned as it was sent. Decoding shall
        be handled by the calling method.
        """
        pickle_string = self.__socket.recv()
        return pickle.loads(pickle_string)

    # FIXME:
    #   We might want to reconsider how commands are send over the ZeroMQ sockets.
    #   it can be very useful to use multipart messages here with the type and
    #   origin etc. to ease the if..else.. constructs.

    @EXECUTION_TIME.time()
    def execute(self):
        cs = self.get_control_server()  # FIXME: 'cs' not used!
        data = self.receive()
        cmd = None
        args = kwargs = None
        if isinstance(data, CommandExecution):
            cmd = data.get_cmd()
            cmd_name = cmd.get_name()
            args = data.get_args()
            kwargs = data.get_kwargs()
        elif isinstance(data, dict):
            cmd_name = data.get("cmd")
            args = data.get("args")
            kwargs = data.get("kwargs")
        elif isinstance(data, str):
            cmd_name = data
        else:
            cmd_name = None

        logger.log(0, f"cmd_name = {cmd_name}")

        # Server availability request - Ping-Pong

        if cmd_name == "Ping":
            COMMAND_REQUESTS.labels(target="ping").inc()
            self.send("Pong")
        elif cmd_name == "send_commands":
            logger.warning("send_commands was commanded for a DynamicCommandProtocol!")
        elif cmd_name == "get_service_port":
            self.send(self.__control_server.get_service_port())
        elif cmd_name == "get_monitoring_port":
            self.send(self.__control_server.get_monitoring_port())
        elif cmd_name == "get_commanding_port":
            self.send(self.__control_server.get_commanding_port())
        elif cmd_name == "get_ip_address":
            self.send(self.__control_server.get_ip_address())
        elif cmd:
            COMMAND_REQUESTS.labels(target="device").inc()
            cmd.server_call(self, *args, **kwargs)
        else:
            COMMAND_REQUESTS.labels(target="invalid").inc()
            logger.warning(f"Invalid command received: {cmd_name}")
            self.send(Failure(f"Invalid command: {cmd_name}"))

    def quit(self):
        """
        This method can be overridden by a sub-class to cleanup and stop threads that it
        started.
        """

        logger.info("quit() method called on Protocol base class.")



class DynamicCommandProtocol(BaseCommandProtocol, metaclass=abc.ABCMeta):
    def __init__(self, control_server: ControlServer):
        super().__init__(control_server)

    def handle_device_method(self, cmd: Command, *args, **kwargs):
        """
        Call the device method with the given arguments.

        Args:
            cmd: the devices command class that knows which device command shall be called
            args: the arguments that will be passed on to the device command
            kwargs: the keyword arguments that will be passed on to the device command
        """
        # The lookup table contains object (bound) methods, so we do not have to
        # provide the 'self' argument anymore.

        method_name = cmd.get_device_method_name()
        method = get_method(self.get_device(), method_name)

        # We treat the get_response function special as it needs to send the ``cmd`` string
        # to the device we need to pass the processed cmd string into the method.

        try:
            if method_name == "get_response":
                device_cmd_string = cmd.get_cmd_string(*args, *kwargs)
                logger.log(5, f"Executing method {method.__name__}({device_cmd_string})")
                response = method(device_cmd_string)
            else:
                logger.log(5, f"Executing method {method.__name__}({args}, {kwargs})")
                response = method(*args, **kwargs)
        except Exception as exc:
            logger.exception(f"Executing {method_name} failed.")
            # Pass the exception on to the client as a Failure message
            response = Failure(f"Executing {method_name} failed: ", exc)

        # Enable the following message only when debugging, because this log message can become
        # very long for data storage commands.
        # logger.debug(f"handle_device_method: {device_name}({args}, {kwargs}) -> {response!s}")

        self.send(response)


# TODO (rik): The CommandProtocol shall also inherit from the BaseCommandProtocol

class CommandProtocol(DeviceConnectionObserver, metaclass=abc.ABCMeta):
    """
    This class is the glue between the control servers and the hardware
    controllers on one side, and between the control server and the connected
    proxy classes on the other side.

    The connection with the hardware controllers is when the ``execute()`` method
    calls the ``server_call()`` method of the command class.

    The connection with the proxy classes is when the ``client_call()`` method is added to the
    interface of the Proxy subclass (by the ``_add_commands()`` method).

    FIXME: Protocol is not used at the client side, i.e. the Proxy class.
    """

    def __init__(self):
        super().__init__()
        self.__socket = None
        self._commands = {}  # variable is used by sub classes
        self.control_server: ControlServer | None = None  # variable set by the sub-class
        self._method_lookup = {}  # lookup table for device methods

    def bind(self, socket):
        """Bind to a socket to listen for commands."""
        self.__socket = socket

        bind_address = self.get_bind_address()
        logger.info(f"Binding to {bind_address}")

        self.__socket.bind(bind_address)

    # FIXME:
    #   We might want to reconsider how commands are send over the ZeroMQ sockets.
    #   it can be very useful to use multipart messages here with the type and
    #   origin etc. to ease the if..else.. constructs.

    @EXECUTION_TIME.time()
    def execute(self):
        data = self.receive()
        cmd = None
        args = kwargs = None
        if isinstance(data, CommandExecution):
            cmd = data.get_cmd()
            cmd_name = cmd.get_name()
            args = data.get_args()
            kwargs = data.get_kwargs()
        elif isinstance(data, dict):
            cmd_name = data.get("cmd")
            args = data.get("args")
            kwargs = data.get("kwargs")
        elif isinstance(data, str):
            cmd_name = data
        else:
            cmd_name = None

        logger.log(0, f"cmd_name = {cmd_name}")

        # Server availability request - Ping-Pong

        if cmd_name == "Ping":
            COMMAND_REQUESTS.labels(target="ping").inc()
            self.send("Pong")
        elif cmd_name == "send_commands":
            self.send_commands()
        elif cmd_name == "get_service_port":
            self.send(self.control_server.get_service_port())
        elif cmd_name == "get_monitoring_port":
            self.send(self.control_server.get_monitoring_port())
        elif cmd_name == "get_commanding_port":
            self.send(self.control_server.get_commanding_port())
        elif cmd_name == "get_ip_address":
            self.send(self.control_server.get_ip_address())
        elif cmd_name == "get_storage_mnemonic":
            self.send(self.control_server.get_storage_mnemonic())
        elif cmd:
            COMMAND_REQUESTS.labels(target="device").inc()
            cmd.server_call(self, *args, **kwargs)
        else:
            COMMAND_REQUESTS.labels(target="invalid").inc()
            logger.warning(f"Invalid command received: {cmd_name}")
            self.send(Failure(f"Invalid command: {cmd_name}"))

    def quit(self):
        """
        This method can be overridden by a sub-class to cleanup and stop threads that it
        started.
        """

        logger.info("quit() method called on Protocol base class.")

    def is_alive(self) -> bool:
        """
        This method can be overridden by a sub-class to check whether any Thread or sub-process
        that was started is still alive.
        """
        return True

    @abc.abstractmethod
    def get_bind_address(self):
        """
        Returns a string with the bind address, the endpoint, for accepting connections
        and bind a socket to.

        This method should be implemented by the sub-class since it contains the protocol
        and port number that are specific for the sub-class.

        Returns:
            a string with the protocol and port to bind a socket to.
        """
        pass

    @abc.abstractmethod
    def get_status(self):
        """
        Returns a dictionary with status information for the control server, enhanced by the
        sub-class with device specific status information.

        This method should be implemented/overridden by the sub-class. The sub-class specific
        method should update the dictionary returned by this super-class method with device
        specific status values.

        The dict returned by this method includes the following keywords:

        * timestamp (str): a string representation of the current datetime
        * PID (int): the Process ID for the control server
        * Up (float): the uptime of the control server [s]
        * UUID (uuid1): a UUID for the control server
        * RSS (int): the 'Resident Set Size', this is the non-swapped physical memory a process
            has used [byte]
        * USS (int): the 'Unique Set Size', this is the memory which is unique to a process [byte]
        * CPU User (float): time spent in user mode [s]
        * CPU System (float): time spent in kernel mode [s]
        * CPU% (float): the process CPU utilization as a percentage [%]

        Check the documentation for `psutil.Process` for more in-depth information about the
        dict keys.

        Returns:
            a dictionary with status information.
        """
        status = {
            "timestamp": format_datetime(),
            "delay": self.control_server.delay,
        }
        status.update(self.control_server.get_process_status())
        return status

    def get_housekeeping(self) -> dict:
        """Returns a dictionary with housekeeping information about the device."""
        raise NotImplementedError(
            f"The get_housekeeping() method shall be implemented for {self.__class__.__name__}."
        )

    def send(self, data):
        """
        Send a message to the ControlServer. The message shall be fully populated
        and is only serialized before sending over the ZeroMQ socket.

        FIXME: We need to add error handling here, e.g. what if the send() fails? Do we need
               to implement retries as with Proxy?
        """
        pickle_string = pickle.dumps(data)
        self.__socket.send(pickle_string)

    def receive(self):
        """
        Receive a serialized message from the ControlServer. The message will not
        be decoded/de-serialized, but is returned as it was sent. Decoding shall
        be handled by the calling method.
        """
        pickle_string = self.__socket.recv()
        data = pickle.loads(pickle_string)
        return data

    def send_commands(self):
        """
        Send the command definitions that were loaded for the specific device.
        """
        self.send(self._commands)

    def load_commands(self, command_settings, command_class, device_class):
        """
        Loads the command definitions from the given ``command_settings`` and builds an internal
        dictionary containing the command names as keys and the corresponding ``Command`` class
        objects as values.

        The ``command_settings`` is usually loaded from a YAML configuration file containing the
        command definitions for the device.

        Args:
            command_settings: a dictionary containing the command definitions for this device
            command_class: the type of command to create, a subclass of Command
            device_class: the type of the base device class from which the methods are loaded
        """
        for name in command_settings:
            command_settings_name = command_settings[name]
            if "cmd" in command_settings_name:
                cmd = command_settings_name["cmd"]
            else:
                cmd = ""

            if "description" in command_settings_name:
                description = command_settings_name["description"]
            else:
                description = None

            # The response field is the name of a function from the CommandProtocol class or a
            # sub-class. This function shall send a response back to the client (Proxy). That's
            # why this field is called response.
            # By convention we like that this method name would start with `handle_` so the we
            # can make a distinction between response commands and normal methods in Protocol.
            # Remember that response methods should send a reply back to the client (which will
            # be waiting for it..).
            # If no response field is given, then the `handle_device_method` will be called.

            if "response" in command_settings_name:
                response_method = get_function(self.__class__, command_settings_name["response"])
            else:
                response_method = get_function(self.__class__, "handle_device_method")

            # The device_method field is used in the `handle_device_method` to call the method on
            # the device class. That is the class that implements the DeviceInterface and is
            # usually called a Controller or a Simulator.
            #
            # If no device_name field is given, the name from the command_settings is used.

            if "device_method" in command_settings_name:
                device_method_name = command_settings_name["device_method"]
            else:
                device_method_name = name

            # check if the device_method exists in the device base class

            if device_method_name == "None":
                device_method = None
            else:
                device_method = get_function(device_class, device_method_name)

            logger.log(
                0,
                f"Creating {command_class.__module__}.{command_class.__name__}(name='{name}', "
                f"cmd='{cmd}', "
                f"response={response_method}, device_method={device_method})",
            )
            logger.debug(f"Creating {command_class.__name__} command with {name=}, {cmd=}, {device_method=}")

            self._commands[name] = command_class(
                name=name,
                cmd=cmd,
                response=response_method,
                description=description,
                device_method=device_method,
            )

    def build_device_method_lookup_table(self, device_obj):
        """
        Fill the lookup table with device command methods that are bound to the device object.

        Args:
            device_obj: instance of a device command class
        """
        for cmd in self._commands.values():
            method_name = cmd.get_device_method_name()
            method = get_method(device_obj, method_name)
            if method is not None:
                self._method_lookup[method_name] = method

    def handle_device_method(self, cmd: Command, *args, **kwargs):
        """
        Call the device method with the given arguments.

        Args:
            cmd: the devices command class that knows which device command shall be called
            args: the arguments that will be passed on to the device command
            kwargs: the keyword arguments that will be passed on to the device command
        """
        # The lookup table contains object (bound) methods, so we do not have to
        # provide the 'self' argument anymore.

        device_name = cmd.get_device_method_name()
        method = self._method_lookup[device_name]

        # We treat the get_response function special as it needs to send the ``cmd`` string
        # to the device we need to pass the processed cmd string into the method.

        try:
            if device_name == "get_response":
                device_cmd_string = cmd.get_cmd_string(*args, *kwargs)
                logger.log(5, f"Executing method {method.__name__}({device_cmd_string})")
                response = method(device_cmd_string)
            else:
                logger.log(5, f"Executing method {method.__name__}({args}, {kwargs})")
                response = method(*args, **kwargs)
        except Exception as exc:
            logger.exception(f"Executing {device_name} failed.")
            # Pass the exception on to the client as a Failure message
            response = Failure(f"Executing {device_name} failed: ", exc)

        # Enable the following message only when debugging, because this log message can become
        # very long for data storage commands.
        # logger.debug(f"handle_device_method: {device_name}({args}, {kwargs}) -> {response!s}")

        self.send(response)
