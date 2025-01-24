"""
This module defines the abstract class for any control server and some convenience functions.
"""
import abc
import logging
import pickle
import threading

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
    """
    Check if the control server is running. This function sends a *Ping* message to the
    control server and expects a *Pong* answer back within the timeout period.

    Args:
        endpoint (str): the endpoint to connect to, i.e. <protocol>://<address>:<port>
        timeout (float): timeout when waiting for a reply [seconds, default=0.5]
    Returns:
        True if the Control Server is running and replied with the expected answer.
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
    """
    The base class for all device control servers and for the Storage Manager and Configuration
    Manager. A Control Server reads commands from a ZeroMQ socket and executes these commands by
    calling the `execute()` method of the commanding protocol class.

    The sub-class shall define the following:

    * Define the device protocol class -> `self.device_protocol`
    * Bind the command socket to the device protocol -> `self.dev_ctrl_cmd_sock`
    * Register the command socket in the poll set -> `self.poller`

    """

    def __init__(self):
        from egse.monitoring import MonitoringProtocol
        from egse.services import ServiceProtocol

        self._process_status = ProcessStatus()

        self._timer_thread = threading.Thread(
            target=do_every, args=(PROCESS_SETTINGS.METRICS_INTERVAL, self._process_status.update))
        self._timer_thread.daemon = True
        self._timer_thread.start()

        # The logger will be overwritten by the sub-class, if not, then we use this logger
        # with the name of the sub-class. That will help us to identify which sub-class did not
        # overwrite the logger attribute.

        self.logger = logging.getLogger(get_full_classname(self))

        self.interrupted = False
        self.delay = 1000  # delay between publish status information [milliseconds]
        self.hk_delay = 1000  # delay between saving housekeeping information [milliseconds]

        self.zcontext = zmq.Context.instance()
        self.poller = zmq.Poller()

        self.device_protocol = None  # This will be set in the sub-class
        self.service_protocol = ServiceProtocol(self)
        self.monitoring_protocol = MonitoringProtocol(self)

        # Setup the control server waiting for service requests

        self.dev_ctrl_service_sock = self.zcontext.socket(zmq.REP)
        self.service_protocol.bind(self.dev_ctrl_service_sock)

        # Setup the control server for sending monitoring info

        self.dev_ctrl_mon_sock = self.zcontext.socket(zmq.PUB)
        self.monitoring_protocol.bind(self.dev_ctrl_mon_sock)

        # Setup the control server waiting for device commands.
        # The device protocol shall bind the socket in the sub-class

        self.dev_ctrl_cmd_sock = self.zcontext.socket(zmq.REP)

        # Initialize the poll set

        self.poller.register(self.dev_ctrl_service_sock, zmq.POLLIN)
        self.poller.register(self.dev_ctrl_mon_sock, zmq.POLLIN)

    @abc.abstractmethod
    def get_communication_protocol(self):
        pass

    @abc.abstractmethod
    def get_commanding_port(self):
        pass

    @abc.abstractmethod
    def get_service_port(self):
        pass

    @abc.abstractmethod
    def get_monitoring_port(self):
        pass

    def get_ip_address(self):
        return get_host_ip()

    def get_storage_mnemonic(self):
        return self.__class__.__name__

    def get_process_status(self):
        return self._process_status.as_dict()

    def get_average_execution_times(self):
        return get_average_execution_times()

    def set_delay(self, seconds: float) -> float:
        """
        Sets the delay time for monitoring. The delay time is the time between two successive executions of the
        `get_status()` function of the device protocol.

        It might happen that the delay time that is set is longer than what you requested. That is the case when
        the execution of the `get_status()` function takes longer than the requested delay time. That should
        prevent the server from blocking when a too short delay time is requested.

        Args:
            seconds: the number of seconds between the monitoring calls.
        Returns:
            The delay that was set in milliseconds.
        """
        execution_time = get_average_execution_time(self.device_protocol.get_status)
        self.delay = max(seconds * 1000, (execution_time + 0.2) * 1000)
        return self.delay

    def set_hk_delay(self, seconds) -> float:
        """
        Sets the delay time for housekeeping. The delay time is the time between two successive executions of the
        `get_housekeeping()` function of the device protocol.

        It might happen that the delay time that is set is longer than what you requested. That is the case when
        the execution of the `get_housekeeping()` function takes longer than the requested delay time. That should
        prevent the server from blocking when a too short delay time is requested.

        Args:
            seconds: the number of seconds between the housekeeping calls.
        Returns:
            The delay that was set in milliseconds.
        """
        execution_time = get_average_execution_time(self.device_protocol.get_housekeeping)
        self.hk_delay = max(seconds * 1000, (execution_time + 0.2) * 1000)
        return self.hk_delay

    def set_logging_level(self, level):
        self.logger.setLevel(level=level)

    def quit(self):
        self.interrupted = True

    def before_serve(self):
        pass

    def after_serve(self):
        pass

    def is_storage_manager_active(self):
        """
        This method needs to be implemented by the subclass if you need to store information.

        Note: you might want to set a specific timeout when checking for the Storage Manager.

        Note: If this method returns True, the following methods shall also be implemented by the subclass:

        * register_to_storage_manager()
        * unregister_from_storage_manager()
        * store_housekeeping_information()

        """
        return False

    def serve(self):

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
                    "The ControlServer can not be interrupted with CTRL-C, "
                    "send a quit command to the server."
                )
                continue

            if self.dev_ctrl_cmd_sock in socks:
                self.device_protocol.execute()

            if self.dev_ctrl_service_sock in socks:
                self.service_protocol.execute()

            # Now handle the periodic sending out of status information. A dictionary with the
            # status or HK info is sent out periodically based on the DELAY time that is in the
            # YAML config file.

            if time_in_ms() - last_time >= self.delay:
                last_time = time_in_ms()
                # self.logger.debug("Sending status to monitoring processes.")
                self.monitoring_protocol.send_status(
                    save_average_execution_time(self.device_protocol.get_status)
                )

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

            # Some device protocol subclasses might start a number of threads or processes to
            # support the commanding. Check if these threads/processes are still alive and
            # terminate gracefully if they are not.

            if not self.device_protocol.is_alive():
                self.logger.error(
                    "Some Thread or sub-process that was started by Protocol has "
                    "died, terminating..."
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

    def store_housekeeping_information(self, data: dict):
        """
        Send housekeeping information to the Storage manager.

        Subclasses need to overwrite this method if they want the device housekeeping information to be saved.

        Args:
            data (dict): a dictionary containing parameter name and value of all device housekeeping. There is also
            a timestamp that represents the date/time when the HK was received from the device.
        """
        pass

    def register_to_storage_manager(self):
        """
        Register this ControlServer to the Storage Manager so the housekeeping information of the device can be saved.

        Subclasses need to overwrite this method if they have housekeeping information to be stored. The following
        information is required for the registration:

        * origin: can be retrieved from `self.get_storage_mnemonic()`
        * persistence_class: one of the TYPES in egse.storage.persistence
        * prep: depending on the type of the persistence class (see respective documentation)

        The `egse.storage` module provides a convenience method that can be called from the method in the subclass:

            >>> from egse.storage import register_to_storage_manager  # noqa

        Note: the `egse.storage` module might not be available, it is provided by the `cgse-core` package.
        """
        pass

    def unregister_from_storage_manager(self):
        """
        Unregister this ControlServer from the Storage manager.

        Subclasses need to overwrite this method. The following information is required for the registration:

        * origin: can be retrieved from `self.get_storage_mnemonic()`

        The `egse.storage` module provides a convenience method that can be called from the method in the subclass:

            >>> from egse.storage import unregister_from_storage_manager  # noqa

        Note: the `egse.storage` module might not be available, it is provided by the `cgse-core` package.
        """
        pass
