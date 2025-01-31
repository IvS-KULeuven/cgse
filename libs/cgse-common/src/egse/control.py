"""
This module defines the abstract class for any Control Server and some convenience functions.
"""

import abc
import logging
import pickle
import threading
from typing import Union

import zmq

from egse.system import time_in_ms

try:
    from egse.logger import close_all_zmq_handlers
except ImportError:
    def close_all_zmq_handlers():  # noqa
        pass

from egse.process import ProcessStatus
from egse.settings import Settings
from egse.system import do_every
from egse.system import get_average_execution_time
from egse.system import get_average_execution_times
from egse.system import get_full_classname
from egse.system import get_host_ip
from egse.system import save_average_execution_time

MODULE_LOGGER = logging.getLogger(__name__)
PROCESS_SETTINGS = Settings.load("PROCESS")


def is_control_server_active(endpoint: str = None, timeout: float = 0.5) -> bool:
    """ Checks if the Control Server is running.

    This function sends a *Ping* message to the Control Server and expects a *Pong* answer back within the timeout
    period.

    Args:
        endpoint (str): Endpoint to connect to, i.e. <protocol>://<address>:<port>
        timeout (float): Timeout when waiting for a reply [s, default=0.5]

    Returns: True if the Control Server is running and replied with the expected answer; False otherwise.
    """

    ctx = zmq.Context.instance()

    return_code = False

    try:
        socket = ctx.socket(zmq.REQ)
        socket.connect(endpoint)
        data = pickle.dumps("Ping")
        socket.send(data)
        rlist, _, _ = zmq.select([socket], [], [], timeout=timeout)

        if socket in rlist:
            data = socket.recv()
            response = pickle.loads(data)
            return_code = response == "Pong"
        socket.close(linger=0)
    except Exception as exc:
        MODULE_LOGGER.warning(f"Caught an exception while pinging a control server at {endpoint}: {exc}.")

    return return_code


class ControlServer(metaclass=abc.ABCMeta):
    """ Base class for all device control servers and for the Storage Manager and Configuration Manager.

    A Control Server reads commands from a ZeroMQ socket and executes these commands by calling the `execute()` method
    of the commanding protocol class.

    The sub-class shall define the following:

        - Define the device protocol class -> `self.device_protocol`
        - Bind the command socket to the device protocol -> `self.dev_ctrl_cmd_sock`
        - Register the command socket in the poll set -> `self.poller`

    """

    def __init__(self):
        """ Initialisation of a new Control Server."""

        from egse.monitoring import MonitoringProtocol
        from egse.services import ServiceProtocol

        self._process_status = ProcessStatus()

        self._timer_thread = threading.Thread(
            target=do_every, args=(PROCESS_SETTINGS.METRICS_INTERVAL, self._process_status.update))
        self._timer_thread.daemon = True
        self._timer_thread.start()

        # The logger will be overwritten by the sub-class, if not, we use this logger with the name of the sub-class.
        # That will help us to identify which sub-class did not overwrite the logger attribute.

        self.logger = logging.getLogger(get_full_classname(self))

        self.interrupted = False
        self.mon_delay = 1000   # Delay between publish status information [ms]
        self.hk_delay = 1000    # Delay between saving housekeeping information [ms]

        self.zcontext = zmq.Context.instance()
        self.poller = zmq.Poller()

        self.device_protocol = None  # This will be set in the sub-class
        self.service_protocol = ServiceProtocol(self)
        self.monitoring_protocol = MonitoringProtocol(self)

        # Set up the Control Server waiting for service requests

        self.dev_ctrl_service_sock = self.zcontext.socket(zmq.REP)
        self.service_protocol.bind(self.dev_ctrl_service_sock)

        # Set up the Control Server for sending monitoring info

        self.dev_ctrl_mon_sock = self.zcontext.socket(zmq.PUB)
        self.monitoring_protocol.bind(self.dev_ctrl_mon_sock)

        # Set up the Control Server waiting for device commands.
        # The device protocol shall bind the socket in the sub-class

        self.dev_ctrl_cmd_sock = self.zcontext.socket(zmq.REP)

        # Initialise the poll set

        self.poller.register(self.dev_ctrl_service_sock, zmq.POLLIN)
        self.poller.register(self.dev_ctrl_mon_sock, zmq.POLLIN)

    @abc.abstractmethod
    def get_communication_protocol(self) -> str:
        """ Returns the communication protocol used by the Control Server.

        Returns: Communication protocol used by the Control Server, as specified in the settings.
        """

        pass

    @abc.abstractmethod
    def get_commanding_port(self) -> int:
        """ Returns the commanding port used by the Control Server.

        Returns: Commanding port used by the Control Server, as specified in the settings.
        """

        pass

    @abc.abstractmethod
    def get_service_port(self) -> int:
        """ Returns the service port used by the Control Server.

        Returns: Service port used by the Control Server, as specified in the settings.
        """

        pass

    @abc.abstractmethod
    def get_monitoring_port(self) -> int:
        """ Returns the monitoring port used by the Control Server.

        Returns: Monitoring port used by the Control Server, as specified in the settings.
        """

        pass

    def get_ip_address(self) -> str:

        return get_host_ip()

    def get_storage_mnemonic(self) -> str:
        """ Returns the storage mnemonics used by the Control Server.

        This is a string that will appear in the filename with the housekeeping information of the device, as a way of
        identifying the device.  If this is not implemented in the sub-class, then the class name will be used.

        Returns: Storage mnemonics used by the Control Server, as specified in the settings.
        """

        return self.__class__.__name__

    def get_process_status(self) -> dict:
        """ Returns the process status of the Control Server.

        Returns: Dictionary with the process status of the Control Server.
        """

        return self._process_status.as_dict()

    def get_average_execution_times(self) -> dict:
        """ Returns the average execution times of all functions that have been monitored by this process.

        Returns: Dictionary with the average execution times of all functions that have been monitored by this process.
                 The dictionary keys are the function names, and the values are the average execution times in ms.
        """

        return get_average_execution_times()

    def set_mon_delay(self, seconds: float) -> float:
        """ Sets the delay time for monitoring.

        The delay time is the time between two successive executions of the `get_status()` function of the device
        protocol.

        It might happen that the delay time that is set is longer than what you requested. That is the case when the
        execution of the `get_status()` function takes longer than the requested delay time. That should prevent the
        server from blocking when a too short delay time is requested.

        Args:
            seconds (float): Number of seconds between the monitoring calls

        Returns: Delay that was set [ms].
        """

        execution_time = get_average_execution_time(self.device_protocol.get_status)
        self.mon_delay = max(seconds * 1000, (execution_time + 0.2) * 1000)

        return self.mon_delay

    def set_hk_delay(self, seconds: float) -> float:
        """ Sets the delay time for housekeeping.

        The delay time is the time between two successive executions of the `get_housekeeping()` function of the device
        protocol.

        It might happen that the delay time that is set is longer than what you requested. That is the case when the
        execution of the `get_housekeeping()` function takes longer than the requested delay time. That should prevent
        the server from blocking when a too short delay time is requested.

        Args:
            seconds (float): Number of seconds between the housekeeping calls

        Returns: Delay that was set [ms].
        """

        execution_time = get_average_execution_time(self.device_protocol.get_housekeeping)
        self.hk_delay = max(seconds * 1000, (execution_time + 0.2) * 1000)

        return self.hk_delay

    def set_logging_level(self, level: Union[int, str]) -> None:
        """ Sets the logging level to the given level.

        Allowed logging levels are:
            - "CRITICAL" or 50
            - "FATAL" or CRITICAL
            - "ERROR" or 40
            - "WARNING" or 30
            - "WARN" or WARNING
            - "INFO" or 20
            - "DEBUG" or 10
            - "NOTSET" or 0

        Args:
            level (int | str): Logging level to use, specified as either a string or an integer
        """

        self.logger.setLevel(level=level)

    def quit(self) -> None:
        """ Interrupts the Control Server."""

        self.interrupted = True

    def before_serve(self) -> None:
        """ Steps to take before the Control Server is activated."""

        pass

    def after_serve(self) -> None:
        """ Steps to take after the Control Server has been deactivated."""

        pass

    def is_storage_manager_active(self) -> bool:
        """ Checks if the Storage Manager is active.

        This method has to be implemented by the sub-class if you need to store information.

        Note: You might want to set a specific timeout when checking for the Storage Manager.

        Note: If this method returns True, the following methods shall also be implemented by the sub-class:

            - register_to_storage_manager()
            - unregister_from_storage_manager()
            - store_housekeeping_information()

        Returns: True if the Storage Manager is active; False otherwise.
        """

        return False

    def serve(self) -> None:
        """ Activation of the Control Server.

        This comprises the following steps:

            - Executing the `before_serve` method;
            - Checking if the Storage Manager is active and registering the Control Server to it;
            - Start listening  for keyboard interrupts;
            - Start accepting (listening to) commands;
            - Start sending out monitoring information;
            - Start sending out housekeeping information;
            - Start listening for quit commands;
            - After a quit command has been received:
                - Unregister from the Storage Manager;
                - Execute the `after_serve` method;
                - Close all sockets;
                - Clean up all threads.
        """

        self.before_serve()

        # check if Storage Manager is available

        storage_manager = self.is_storage_manager_active()

        storage_manager and self.register_to_storage_manager()

        # This approach is very simplistic and not time efficient
        # We probably want to use a Timer that executes the monitoring and saving actions at
        # dedicated times in the background.

        # FIXME; we shall use the time.perf_counter() here!

        last_time = time_in_ms()
        last_time_hk = time_in_ms()

        while True:
            try:
                socks = dict(self.poller.poll(50))  # timeout in milliseconds, do not block
            except KeyboardInterrupt:
                self.logger.warning("Keyboard interrupt caught!")
                self.logger.warning(
                    "The ControlServer can not be interrupted with CTRL-C, send a quit command to the server instead."
                )
                continue

            if self.dev_ctrl_cmd_sock in socks:
                self.device_protocol.execute()

            if self.dev_ctrl_service_sock in socks:
                self.service_protocol.execute()

            # Handle sending out monitoring information periodically, based on the MON_DELAY time that is specified in
            # the YAML configuration file for the device

            if time_in_ms() - last_time >= self.mon_delay:
                last_time = time_in_ms()
                # self.logger.debug("Sending status to monitoring processes.")
                self.monitoring_protocol.send_status(
                    save_average_execution_time(self.device_protocol.get_status)
                )

            # Handle sending out housekeeping information periodically, based on the HK_DELAY time that is specified in
            # the YAML configuration file for the device

            if time_in_ms() - last_time_hk >= self.hk_delay:
                last_time_hk = time_in_ms()
                if storage_manager:
                    # self.logger.debug("Sending housekeeping information to Storage.")
                    self.store_housekeeping_information(
                        save_average_execution_time(self.device_protocol.get_housekeeping)
                    )

            if self.interrupted:
                self.logger.info(
                    f"Quit command received, closing down the {self.__class__.__name__}."
                )
                break

            # Some device protocol sub-classes might start a number of threads or processes to support the commanding.
            # Check if these threads/processes are still alive and terminate gracefully if they are not.

            if not self.device_protocol.is_alive():
                self.logger.error(
                    "Some Thread or sub-process that was started by Protocol has died, terminating..."
                )
                break

        storage_manager and self.unregister_from_storage_manager()

        self.after_serve()

        self.device_protocol.quit()

        self.dev_ctrl_mon_sock.close()
        self.dev_ctrl_service_sock.close()
        self.dev_ctrl_cmd_sock.close()

        close_all_zmq_handlers()

        self.zcontext.term()

    def store_housekeeping_information(self, data: dict) -> None:
        """ Sends housekeeping information to the Storage Manager.

        This method has to be overwritten by the sub-classes if they want the device housekeeping information to be
        saved.

        Args:
            data (dict): a dictionary containing parameter name and value of all device housekeeping. There is also
            a timestamp that represents the date/time when the HK was received from the device.
        """
        pass

    def register_to_storage_manager(self) -> None:
        """ Registers this Control Server to the Storage Manager.

        By doing so, the housekeeping information of the device will be sent to the Storage Manager, which will store
        the information in a dedicated CSV file.

        This method has to be overwritten by the sub-classes if they have housekeeping information that must be stored.

        Subclasses need to overwrite this method if they have housekeeping information to be stored.

        The following   information is required for the registration:

            - origin: Storage mnemonic, which can be retrieved from `self.get_storage_mnemonic()`
            - persistence_class: Persistence layer (one of the TYPES in egse.storage.persistence)
            - prep: depending on the type of the persistence class (see respective documentation)

        The `egse.storage` module provides a convenience method that can be called from the method in the subclass:

            >>> from egse.storage import register_to_storage_manager  # noqa

        Note: the `egse.storage` module might not be available, it is provided by the `cgse-core` package.
        """
        pass

    def unregister_from_storage_manager(self) -> None:
        """ Unregisters the Control Server from the Storage Manager.

        This method has to be overwritten by the sub-classes.

        The following information is required for the registration:

            - origin: Storage mnemonic, which can be retrieved from `self.get_storage_mnemonic()`

        The `egse.storage` module provides a convenience method that can be called from the method in the sub-class:

            >>> from egse.storage import unregister_from_storage_manager  # noqa

        Note: the `egse.storage` module might not be available, it is provided by the `cgse-core` package.
        """

        pass
