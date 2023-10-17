"""
The Proxy module provides the base class for the Proxy objects for each device
controller.

The module also provides the connection state interface and classes for
maintaining the state of the Proxy connection to the control server.
"""
import logging
import pickle
import types
from types import MethodType

import zmq

from egse.decorators import dynamic_interface
from egse.mixin import DynamicClientCommandMixin
from egse.system import AttributeDict
from egse.zmq_ser import split_address


def set_docstring(func, cmd):
    """Decorator to set the docstring of the command on the dynamic method / function."""

    def wrap_func(*args, **kwargs):
        return func(*args, **kwargs)

    wrap_func.__doc__ = cmd.__doc__
    wrap_func.__name__ = f"{cmd.get_name()}"
    return wrap_func


REQUEST_TIMEOUT = 30 * 1000  # timeout in millisecond
REQUEST_RETRIES = 0


class ControlServerConnectionInterface:
    """This interface defines the connection commands for control servers.

    This interface shall be implemented by the Proxy class and guarantees that connection commands
    do not interfere with the commands defined in the `DeviceConnectionInterface` (which will be
    loaded from the control server).
    """

    def __enter__(self):
        self.connect_cs()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect_cs()

    @dynamic_interface
    def connect_cs(self):
        """Connect to the control server.

        Raises:
            ConnectionError: when the connection can not be established.
        """
        raise NotImplementedError

    @dynamic_interface
    def reconnect_cs(self):
        """Reconnect the control server after it has been disconnected.

        Raises:
            ConnectionError: when the connection can not be established.
        """
        raise NotImplementedError

    @dynamic_interface
    def disconnect_cs(self):
        """Disconnect from the control server.

        Raises:
            ConnectionError: when the connection can not be closed.
        """
        raise NotImplementedError

    @dynamic_interface
    def reset_cs_connection(self):
        """Resets the connection to the control server."""
        raise NotImplementedError

    @dynamic_interface
    def is_cs_connected(self) -> bool:
        """Check if the control server is connected.

        Returns:
            True if the device is connected and responds to a command, False otherwise.
        """
        raise NotImplementedError


class BaseProxy(ControlServerConnectionInterface):
    def __init__(self, endpoint, timeout: int = REQUEST_TIMEOUT):
        """
        The `timeout` argument specifies the number of milliseconds to wait for a reply from the
        control server.
        """

        self._logger = logging.getLogger(self.__class__.__name__)

        self._ctx = zmq.Context.instance()
        self._poller = zmq.Poller()
        self._socket = None
        self._endpoint = endpoint
        self._timeout = timeout

        self.connect_cs()

    def __enter__(self):
        if not self.ping():
            raise ConnectionError(f"Proxy is not connected to endpoint ({self._endpoint}) when entering the context.")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._socket.closed:
            self.disconnect_cs()

    def connect_cs(self):
        self._logger.log(0, f"Trying to connect {self.__class__.__name__} to {self._endpoint}")

        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(self._endpoint)
        self._poller.register(self._socket, zmq.POLLIN)

    def disconnect_cs(self):
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.close()
        self._poller.unregister(self._socket)

    def reconnect_cs(self):
        self._logger.log(20, f"Trying to reconnect {self.__class__.__name__} to {self._endpoint}")

        if not self._socket.closed:
            self._socket.close(linger=0)

        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(self._endpoint)
        self._poller.register(self._socket, zmq.POLLIN)

    def reset_cs_connection(self):
        self._logger.log(
            10, f"Trying to reset the connection from {self.__class__.__name__} to {self._endpoint}"
        )

        self.disconnect_cs()
        self.connect_cs()

    def is_cs_connected(self) -> bool:
        return self.ping()

    def send(self, data, retries: int = REQUEST_RETRIES, timeout: int = None):
        """
        Sends a command to the control server and waits for a response.

        When not connected to the control server or when a timeout occurs, the
        ``send()`` command retries a number of times to send the command.

        The number of retries is hardcoded and currently set to '2', the request
        timeout is set to 2.5 seconds.

        The command data will be pickled before sending. Make sure the ``data``
        argument can be dumped by pickle.

        Args:
            data (str): the command that is sent to the control server, usually a
                string, but that is not enforced.
            timeout (int): the time to wait for a reply [in milliseconds]
            retries (int): the number of time we should retry to send the message

        Returns:
            response: the response from the control server or ``None`` when there was
                a problem or a timeout.
        """
        timeout = timeout or self._timeout

        pickle_string = pickle.dumps(data)

        retries_left = retries

        # When we enter this method, we assume the Proxy has been connected. It
        # might be the server is not responding, but that is handled by the
        # algorithm below where we have a number of retries to receive the response
        # of the sent command. Remember that we are using ZeroMQ where the connect
        # method returns gracefully even when no server is available.

        if self._socket.closed:
            self.reconnect_cs()

        self._logger.log(0, f"Sending '{data}'")
        self._socket.send(pickle_string)

        while True:
            socks = dict(self._poller.poll(timeout))

            if self._socket in socks and socks[self._socket] == zmq.POLLIN:
                pickle_string = self._socket.recv()
                if not pickle_string:
                    break
                response = pickle.loads(pickle_string)
                self._logger.log(0, f"Receiving response: {response}")
                return response
            else:
                # timeout - server unavailable

                # We should disconnect here because socket is possibly confused.
                # Close the socket and remove from the poller.

                self.disconnect_cs()

                if retries_left == 0:
                    self._logger.critical("Control Server seems to be off-line, abandoning")
                    return None
                retries_left -= 1

                self._logger.log(logging.CRITICAL, f"Reconnecting {self.__class__.__name__}, {retries_left=}")

                self.reconnect_cs()

                # Now try to send the request again

                self._socket.send(pickle_string)

    def ping(self):
        return_code = self.send("Ping", retries=0, timeout=1000)
        self._logger.log(0, f"Check if control server is available: Ping - {return_code}")
        return return_code == "Pong"

    def get_endpoint(self):
        """ Returns the endpoint."""
        return self._endpoint

    def get_monitoring_port(self) -> int:
        """ Returns the monitoring port. """
        return self.send("get_monitoring_port")

    def get_commanding_port(self) -> int:
        """ Returns the commanding port."""
        return self.send("get_commanding_port")

    def get_service_port(self) -> int:
        """ Returns the service port. """
        return self.send("get_service_port")

    def get_ip_address(self) -> int:
        """ Returns the hostname of the control server."""
        return self.send("get_ip_address")

    def get_service_proxy(self):
        """Return a ServiceProxy for the control server of this proxy object."""
        from egse.services import ServiceProxy  # prevent circular import problem

        transport, address, _ = split_address(self._endpoint)

        port = self.send("get_service_port")

        return ServiceProxy(
            AttributeDict({"PROTOCOL": transport, "HOSTNAME": address, "SERVICE_PORT": port})
        )


class DynamicProxy(BaseProxy, DynamicClientCommandMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# TODO (rik): remove all methods from Proxy that are also define in the BaseProxy

class Proxy(BaseProxy, ControlServerConnectionInterface):
    """
    A Proxy object will forward CommandExecutions to the connected control server
    and wait for a response. When the Proxy can not connect to its control server
    during initialization, a ConnectionError will be raised.
    """

    def __init__(self, endpoint, timeout: int = REQUEST_TIMEOUT):
        """
        During initialization, the Proxy will connect to the control server and send a
        handshaking `Ping` command. When that succeeds the Proxy will request and load the
        available commands from the control server. When the connection with the control server
        fails, no commands are loaded and the Proxy is left in a 'disconnected' state. The caller
        can fix the problem with the control server and call `connect_cs()`, followed by a call to
        `load_commands()`.

        The `timeout` argument specifies the number of milliseconds
        """

        super().__init__(endpoint, timeout)

        self._commands = {}

        if self.ping():
            self.load_commands()
        else:
            self._logger.warning(
                f"{self.__class__.__name__} could not connect to its control server at {endpoint}. "
                f"No commands have been loaded."
            )

    def __enter__(self):
        if not self.ping():
            raise ConnectionError("Proxy is not connected when entering the context.")

        # The following check is here because a CS might have come alive between the __init__
        # and __enter__ calls, and while the ping() will reconnect, the Proxy will have no
        # commands loaded.

        if not self.has_commands():
            self.load_commands()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._socket.closed:
            self.disconnect_cs()

    def connect_cs(self):
        self._logger.log(0, f"Trying to connect {self.__class__.__name__} to {self._endpoint}")

        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(self._endpoint)
        self._poller.register(self._socket, zmq.POLLIN)

    def disconnect_cs(self):
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.close()
        self._poller.unregister(self._socket)

    def reconnect_cs(self):
        self._logger.log(20, f"Trying to reconnect {self.__class__.__name__} to {self._endpoint}")

        if not self._socket.closed:
            self._socket.close(linger=0)

        self._socket = self._ctx.socket(zmq.REQ)
        self._socket.connect(self._endpoint)
        self._poller.register(self._socket, zmq.POLLIN)

    def reset_cs_connection(self):
        self._logger.log(
            10, f"Trying to reset the connection from {self.__class__.__name__} to {self._endpoint}"
        )

        self.disconnect_cs()
        self.connect_cs()

    def is_cs_connected(self) -> bool:
        return self.ping()

    def send(self, data, retries: int = REQUEST_RETRIES, timeout: int = None):
        """
        Sends a command to the control server and waits for a response.

        When not connected to the control server or when a timeout occurs, the
        ``send()`` command retries a number of times to send the command.

        The number of retries is hardcoded and currently set to '2', the request
        timeout is set to 2.5 seconds.

        The command data will be pickled before sending. Make sure the ``data``
        argument can be dumped by pickle.

        Args:
            data (str): the command that is sent to the control server, usually a
                string, but that is not enforced.
            timeout (int): the time to wait for a reply [in milliseconds]
            retries (int): the number of time we should retry to send the message

        Returns:
            response: the response from the control server or ``None`` when there was
                a problem or a timeout.
        """
        timeout = timeout or self._timeout

        pickle_string = pickle.dumps(data)

        retries_left = retries

        # When we enter this method, we assume the Proxy has been connected. It
        # might be the server is not responding, but that is handled by the
        # algorithm below where we have a number of retries to receive the response
        # of the sent command. Remember that we are using ZeroMQ where the connect
        # method returns gracefully even when no server is available.

        if self._socket.closed:
            self.reconnect_cs()

        self._logger.log(0, f"Sending '{data}'")
        self._socket.send(pickle_string)

        while True:
            socks = dict(self._poller.poll(timeout))

            if self._socket in socks and socks[self._socket] == zmq.POLLIN:
                pickle_string = self._socket.recv()
                if not pickle_string:
                    break
                response = pickle.loads(pickle_string)
                self._logger.log(0, f"Receiving response: {response}")
                return response
            else:
                # timeout - server unavailable

                # We should disconnect here because socket is possibly confused.
                # Close the socket and remove from the poller.

                self.disconnect_cs()

                if retries_left == 0:
                    self._logger.critical(f"Control Server seems to be off-line, abandoning ({data})")
                    return None
                retries_left -= 1

                self._logger.log(logging.CRITICAL, f"Reconnecting {self.__class__.__name__}, {retries_left=}")

                self.reconnect_cs()

                # Now try to send the request again

                self._socket.send(pickle_string)

    def _request_commands(self):
        self._commands = self.send("send_commands")

    def _add_commands(self):
        for key in self._commands:
            if hasattr(self, key):
                attribute = getattr(self, key)
                if isinstance(attribute, types.MethodType) and not hasattr(
                    attribute, "__dynamic_interface"
                ):
                    self._logger.warning(
                        f"{self.__class__.__name__} already has an attribute '{key}', "
                        f"not overwriting."
                    )
                    continue
            command = self._commands[key]
            new_method = MethodType(command.client_call, self)
            new_method = set_docstring(new_method, command)
            setattr(self, key, new_method)

    def get_service_proxy(self):
        """Return a ServiceProxy for the control server of this proxy object."""
        from egse.services import ServiceProxy  # prevent circular import problem

        transport, address, _ = split_address(self._endpoint)

        port = self.send("get_service_port")

        return ServiceProxy(
            AttributeDict({"PROTOCOL": transport, "HOSTNAME": address, "SERVICE_PORT": port})
        )

    def load_commands(self):
        """
        Requests all available commands from the control server and adds them to
        the Proxy public interface, i.e. each command will become a method for
        this Proxy.

        A warning will be issued when a command will overwrite an existing method
        of the Proxy class. The original method will not be overwritten and the
        behavior of the Proxy command will not be what is expected.
        """
        # bind the client_call method from each Command to this Proxy object
        # TODO(rik): what will happen when the _request_commands() fails?
        if self.is_cs_connected():
            self._request_commands()
            self._add_commands()
            return True
        else:
            self._logger.warning(f"{self.__class__.__name__} is not connected, try to reconnect.")
            return False

    def get_commands(self):
        """
        Returns a list of command names that can be send to the device or the
        control server.

        The commands are defined in the YAML settings file of the device.
        Special commands are available for the ServiceProxy which configure and
        control the control servers.
        """
        return list(self._commands.keys())

    def has_commands(self):
        """Return `True` if commands have been loaded."""
        return bool(self._commands)

    def ping(self):
        return_code = self.send("Ping", retries=0, timeout=1000)
        self._logger.debug(f"Check if control server is available: Ping - {return_code}")
        return return_code == "Pong"

    def get_endpoint(self):
        """ Returns the endpoint.

        Returns:
            - Endpoint.
        """

        return self._endpoint

    def get_monitoring_port(self) -> int:
        """ Returns the monitoring port. """

        return self.send("get_monitoring_port")

    def get_commanding_port(self) -> int:
        """ Returns the commanding port."""

        return self.send("get_commanding_port")

    def get_service_port(self) -> int:
        """ Returns the service port. """

        return self.send("get_service_port")

    def get_ip_address(self) -> int:
        """ Returns the hostname of the control server."""

        return self.send("get_ip_address")
