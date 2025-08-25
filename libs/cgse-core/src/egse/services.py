"""
This module provides the services to the control servers.

Each control server has a services protocol which provides commands that will
be executed on the control server instead of the device controller. This is
typically used to access control server specific settings like monitoring frequency,
logging levels, or to quit the control server in a controlled way.

"""

import inspect
import logging
import textwrap
from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.decorators import dynamic_interface
from egse.log import logger
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.proxy import REQUEST_TIMEOUT
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

HERE = Path(__file__).parent

SERVICE_SETTINGS = Settings.load(location=HERE, filename="services.yaml")


class ServiceCommand(ClientServerCommand):
    pass


class ServiceProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__(control_server)

        self.load_commands(SERVICE_SETTINGS.Commands, ServiceCommand, ServiceProtocol)

    def get_bind_address(self):
        """
        Returns a string with the bind address, the endpoint, for accepting connections
        and bind a socket to. The port to connect to is the service port in this case,
        not the commanding port.

        Returns:
            a string with the protocol and port to bind a socket to.
        """
        return bind_address(
            self._control_server.get_communication_protocol(),
            self._control_server.get_service_port(),
        )

    def handle_set_monitoring_frequency(self, freq: float):
        """
        Sets the monitoring frequency (Hz) to the given freq value. This is only approximate since the frequency is
        converted into a delay time and the actual execution of the status function is subject to the load on the
        server and the overhead of the timing.

        Args:
            freq: frequency of execution (Hz)

        Returns:
            Sends back the selected delay time in milliseconds.
        """
        delay = self.get_control_server().set_mon_delay(1.0 / freq)

        logger.debug(f"Set monitoring frequency to {freq}Hz, ± every {delay:.0f}ms.")

        self.send(delay)

    def handle_set_hk_frequency(self, freq: float):
        """
        Sets the housekeeping frequency (Hz) to the given freq value. This is only approximate since the frequency is
        converted into a delay time and the actual execution of the `housekeeping` function is subject to the load on
        the server and the overhead of the timing.

        Args:
            freq: frequency of execution (Hz)

        Returns:
            Sends back the selected delay time in milliseconds.
        """
        delay = self.get_control_server().set_hk_delay(1.0 / freq)

        logger.debug(f"Set housekeeping frequency to {freq}Hz, ± every {delay:.0f}ms.")

        self.send(delay)

    def handle_set_logging_level(self, *args, **kwargs):
        """
        Set the logging level for the logger with the given name.

        When 'all' is given for the name of the logger, the level of all loggers for which the name
        starts with 'egse' will be changed to `level`.

        Args:
            name (str): the name of an existing Logger
            level (int): the logging level

        Returns:
            Sends back an info message on what level was set.
        """
        if args:
            name = args[0]
            level = int(args[1])
        else:
            name = kwargs["name"]
            level = int(kwargs["level"])

        if name == "all":
            for logger in [
                logging.getLogger(logger_name)
                for logger_name in logging.root.manager.loggerDict
                if logger_name.startswith("egse")
            ]:
                logger.setLevel(level)
            msg = f"Logging level set to {level} for ALL 'egse' loggers"
        elif name in logging.root.manager.loggerDict:
            logger = logging.getLogger(name)
            logger.setLevel(level)
            msg = f"Logging level for {name} set to {level}."
        else:
            msg = f"Logger with name '{name}' doesn't exist at the server side."

        # self.control_server.set_logging_level(level)
        logging.debug(msg)
        self.send(msg)

    def handle_quit(self):
        logger.info(f"Sending interrupt to {self.control_server.__class__.__name__}.")
        self.control_server.quit()
        self.send(f"Sent interrupt to {self.control_server.__class__.__name__}.")

    def handle_get_process_status(self):
        logger.debug(f"Asking for process status of {self.control_server.__class__.__name__}.")
        self.send(self.get_status())

    def handle_get_cs_module(self):
        """
        Returns the module in which the control server has been implemented.
        """
        logger.debug(f"Asking for module of {self.control_server.__class__.__name__}.")
        self.send(inspect.getmodule(self.control_server).__spec__.name)

    def handle_get_average_execution_times(self):
        logger.debug(f"Asking for average execution times of {self.control_server.__class__.__name__} functions.")
        self.send(self.control_server.get_average_execution_times())

    def handle_get_storage_mnemonic(self):
        logger.debug(f"Asking for the storage menmonic of {self.control_server.__class__.__name__}.")
        self.send(self.control_server.get_storage_mnemonic())

    def handle_add_listener(self, listener: dict):
        logger.debug(f"Add listener to {self.control_server.__class__.__name__}: {listener}")
        try:
            self.control_server.listeners.add_listener(listener)
            logger.info(f"Registered listener: {listener['name']} with proxy {listener['proxy']}")
            self.send(("ACK",))
        except ValueError as exc:
            self.send(("NACK", exc))  # Why not send back a failure object?

    def handle_remove_listener(self, listener: dict):
        logger.debug(f"Remove listener from {self.control_server.__class__.__name__}: {listener}")
        try:
            self.control_server.listeners.remove_listener(listener)
            logger.info(f"Removed listener: {listener['name']}")
            self.send(("ACK",))
        except ValueError as exc:
            self.send(("NACK", exc))  # Why not send back a failure object?

    def handle_get_listener_names(self):
        logger.debug(f"Get names of registered listener from {self.control_server.__class__.__name__}")
        try:
            names = self.control_server.listeners.get_listener_names()
            self.send((names,))
        except ValueError as exc:
            self.send(("", exc))  # Why not sent back a Failure object?

    def handle_register_to_storage(self):
        logger.debug("(re-)registering to the storage manager")
        try:
            self.control_server.register_to_storage_manager()
            self.send(("ACK",))
        except Exception as exc:
            self.send(("NACK", exc))  # Why not send back a failure object?


class ServiceInterface:
    @dynamic_interface
    def set_monitoring_frequency(self, freq: float): ...
    @dynamic_interface
    def set_hk_frequency(self, freq: float): ...
    @dynamic_interface
    def set_logging_level(self, name: str, level: int): ...
    @dynamic_interface
    def quit_server(self): ...
    @dynamic_interface
    def get_process_status(self): ...
    @dynamic_interface
    def get_cs_module(self): ...
    @dynamic_interface
    def get_average_execution_times(self): ...
    @dynamic_interface
    def get_storage_mnemonic(self): ...
    @dynamic_interface
    def add_listener(self, listener: dict): ...
    @dynamic_interface
    def remove_listener(self, listener: dict): ...
    @dynamic_interface
    def get_listener_names(self, listener: dict): ...
    @dynamic_interface
    def register_to_storage(self): ...


class ServiceProxy(Proxy, ServiceInterface):
    """
    A ServiceProxy is a simple class that forwards service commands to a control server.
    """

    def __init__(
        self,
        service_type: str = None,
        protocol: str = "tcp",
        hostname: str = None,
        port: int = None,
        timeout: int = REQUEST_TIMEOUT,
    ):
        """
        The Service Proxy class is used to send service commands to the control server.

        Args:
            service_type: the target service type
            protocol: the transport protocol [default: tcp]
            hostname: the IP address of the control server
            port: the port on which the control server is listening for service commands
            timeout: number of milliseconds before a timeout is triggered
        """

        if hostname is None or port is None:
            if service_type is None:
                raise ValueError(
                    textwrap.dedent(
                        """\
                        No service_type or hostname/port information provided.
                        I need either the service_type or the endpoint information to create a ServiceProxy.
                        """
                    )
                )

            with RegistryClient() as reg:
                service = reg.discover_service(service_type)

                if service:
                    protocol = service.get("protocol", "tcp")
                    hostname = service["host"]
                    port = service["metadata"]["service_port"]

                else:
                    raise RuntimeError(f"No service registered as {service_type}")

        endpoint = connect_address(protocol, hostname, port)
        super().__init__(endpoint, timeout)
