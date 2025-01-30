"""
This module provides the services to the control servers.

Each control server has a services protocol which provides commands that will
be executed on the control server instead of the device controller. This is
typically used to access control server specific settings like monitoring frequency,
logging levels, or to quit the control server in a controlled way.

"""

import inspect
import logging
from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.decorators import dynamic_interface
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.settings import Settings
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

LOGGER = logging.getLogger(__name__)

HERE = Path(__file__).parent

SERVICE_SETTINGS = Settings.load(location=HERE, filename="services.yaml")


class ServiceCommand(ClientServerCommand):
    pass


class ServiceProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

        self.load_commands(SERVICE_SETTINGS.Commands, ServiceCommand, ServiceProtocol)

    def get_bind_address(self):
        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_service_port())

    def get_status(self):
        return super().get_status()

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
        delay = self.control_server.set_delay(1.0 / freq)

        LOGGER.debug(f"Set monitoring frequency to {freq}Hz, ± every {delay:.0f}ms.")

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
        delay = self.control_server.set_hk_delay(1.0 / freq)

        LOGGER.debug(f"Set housekeeping frequency to {freq}Hz, ± every {delay:.0f}ms.")

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
            name = kwargs['name']
            level = int(kwargs['level'])

        if name == 'all':
            for logger in [logging.getLogger(logger_name)
                           for logger_name in logging.root.manager.loggerDict
                           if logger_name.startswith('egse')]:
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
        LOGGER.info(f"Sending interrupt to {self.control_server.__class__.__name__}.")
        self.control_server.quit()
        self.send(f"Sent interrupt to {self.control_server.__class__.__name__}.")

    def handle_get_process_status(self):
        LOGGER.debug(f"Asking for process status of {self.control_server.__class__.__name__}.")
        self.send(self.get_status())

    def handle_get_cs_module(self):
        """
        Returns the module in which the control server has been implemented.
        """
        LOGGER.debug(f"Asking for module of {self.control_server.__class__.__name__}.")
        self.send(inspect.getmodule(self.control_server).__spec__.name)

    def handle_get_average_execution_times(self):
        LOGGER.debug(f"Asking for average execution times of {self.control_server.__class__.__name__} functions.")
        self.send(self.control_server.get_average_execution_times())

    def handle_get_storage_mnemonic(self):
        LOGGER.debug(f"Asking for the storage menmonic of {self.control_server.__class__.__name__}.")
        self.send(self.control_server.get_storage_mnemonic())

class ServiceInterface:
    @dynamic_interface
    def set_monitoring_frequency(self, freq: float):
        ...
    @dynamic_interface
    def set_hk_frequency(self, freq: float):
        ...
    @dynamic_interface
    def set_logging_level(self, name: str, level: int):
        ...
    @dynamic_interface
    def quit_server(self):
        ...
    @dynamic_interface
    def get_process_status(self):
        ...
    @dynamic_interface
    def get_cs_module(self):
        ...
    @dynamic_interface
    def get_average_execution_times(self):
        ...
    @dynamic_interface
    def get_storage_mnemonic(self):
        ...

class ServiceProxy(Proxy, ServiceInterface):
    """
    A ServiceProxy is a simple class that forwards service commands to a control server.
    """

    def __init__(self, ctrl_settings=None, *, protocol=None, hostname=None, port=None):
        """
        A ServiceProxy can be configured from the specific control server settings, or additional
        arguments `protocol`, `hostname` and `port` can be passed.

        The additional arguments always overwrite the values loaded from ctrl_settings. Either ctrl_settings or
        hostname and port must be provided, protocol is optional and defaults to 'tcp'.

        Args:
            ctrl_settings: an AttributeDict with HOSTNAME, PORT and PROTOCOL attributes
            protocol: the transport protocol [default: tcp]
            hostname: the IP addrress of the control server
            port: the port on which the control server is listening for service commands
        """
        _protocol = _hostname = _port = None
        if ctrl_settings:
            _protocol = ctrl_settings.PROTOCOL
            _hostname = ctrl_settings.HOSTNAME
            _port = ctrl_settings.SERVICE_PORT

        # the protocol argument is overwriting the standard crtl_settings

        if protocol:
            _protocol = protocol

        # if still _protocol is not set, neither by ctrl_settings, nor by the protocol argument, use a default

        if _protocol is None:
            _protocol = 'tcp'

        if hostname:
            _hostname = hostname
        if port:
            _port = port

        if _hostname is None or _port is None:
            raise ValueError("Expected ctrl-settings or hostname and port as arguments")

        super().__init__(connect_address(_protocol, _hostname, _port))
