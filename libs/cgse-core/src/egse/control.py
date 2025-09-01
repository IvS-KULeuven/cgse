"""
This module defines the abstract class for any Control Server and some convenience functions.
"""

from __future__ import annotations

import abc
import datetime
import logging
import os
import pickle
import textwrap
import threading
from functools import partial
from typing import Callable
from typing import Type
from typing import Union

import zmq
from urllib3.exceptions import NewConnectionError

from egse.decorators import retry
from egse.decorators import retry_with_exponential_backoff
from egse.listener import Listeners
from egse.log import logger
from egse.logger import close_all_zmq_handlers
from egse.metrics import get_metrics_repo
from egse.notifyhub.services import EventSubscriber
from egse.process import ProcessStatus
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.settings import get_site_id
from egse.signal import FileBasedSignaling
from egse.system import SignalCatcher
from egse.system import Timer
from egse.system import camel_to_kebab
from egse.system import camel_to_snake
from egse.system import do_every
from egse.system import get_average_execution_time
from egse.system import get_average_execution_times
from egse.system import get_full_classname
from egse.system import get_host_ip
from egse.system import save_average_execution_time
from egse.system import str_to_datetime
from egse.system import time_in_ms
from egse.system import type_name
from egse.zmq_ser import get_port_number

PROCESS_SETTINGS = Settings.load("PROCESS")
SITE_ID = get_site_id()


def is_control_server_active(endpoint: str = None, timeout: float = 0.5) -> bool:
    """Checks if the Control Server is running.

    This function sends a *Ping* message to the Control Server and expects a *Pong* answer back within the timeout
    period.

    Args:
        endpoint (str): Endpoint to connect to, i.e. <protocol>://<address>:<port>
        timeout (float): Timeout when waiting for a reply [s, default=0.5]

    Returns: True if the Control Server is running and replied with the expected answer; False otherwise.
    """

    if endpoint is None:
        raise ValueError(
            "endpoint argument not provided, please provide a string with this format: '<protocol>://<address>:<port>'"
        )

    logger.debug(f"Checking if {endpoint} is active {timeout=}s.")

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
        logger.warning(f"Caught an exception while pinging a control server at {endpoint}: {exc}.")

    return return_code


class ControlServer(metaclass=abc.ABCMeta):
    """Base class for all device control servers and for the Storage Manager and Configuration Manager.

    A Control Server reads commands from a ZeroMQ socket and executes these commands by calling the `execute()` method
    of the commanding protocol class.

    The subclass shall define the following:

    - Define the device protocol class -> `self.device_protocol`
    - Bind the command socket to the device protocol -> `self.dev_ctrl_cmd_sock`
    - Register the command socket in the poll set -> `self.poller`

    """

    def __init__(self, device_id: str = None):
        """Initialisation of a new Control Server."""

        from egse.monitoring import MonitoringProtocol
        from egse.services import ServiceProtocol

        self.device_id = device_id
        self._process_status = ProcessStatus()

        self._timer_thread = threading.Thread(
            target=do_every, args=(PROCESS_SETTINGS.METRICS_INTERVAL, self._process_status.update)
        )
        self._timer_thread.daemon = True
        self._timer_thread.start()

        # The logger will be overwritten by the subclass, if not, we use this logger with the name of the subclass.
        # That will help us to identify which subclass did not overwrite the logger attribute.

        self.logger = logging.getLogger(get_full_classname(self))

        self.listeners = Listeners()
        self.scheduled_tasks = []

        self.registry = RegistryClient()
        self.registry.connect()

        self.service_id = None

        # These instance variables will probably be overwritten by the subclass __init__
        self.service_type = camel_to_kebab(type(self).__name__)
        self.service_name = camel_to_snake(type(self).__name__)

        self.signaling: FileBasedSignaling | None = None

        self.interrupted = False
        self.mon_delay = 1000  # Delay between publish status information [ms]
        self.hk_delay = 1000  # Delay between saving housekeeping information [ms]
        self.scheduled_task_delay = 10  # delay time between successive executions of scheduled tasks [seconds]

        self.zcontext = zmq.Context.instance()
        self.poller = zmq.Poller()

        self.device_protocol = None  # This will be set in the subclass
        self.service_protocol = ServiceProtocol(self)
        self.monitoring_protocol = MonitoringProtocol(self)

        # Set up the Control Server waiting for service requests

        self.dev_ctrl_service_sock = self.zcontext.socket(zmq.REP)
        self.service_protocol.bind(self.dev_ctrl_service_sock)

        # Set up the Control Server for sending monitoring info

        self.dev_ctrl_mon_sock = self.zcontext.socket(zmq.PUB)
        self.monitoring_protocol.bind(self.dev_ctrl_mon_sock)

        # Set up the Control Server waiting for device commands.
        # The device protocol shall bind the socket in the subclass

        self.dev_ctrl_cmd_sock = self.zcontext.socket(zmq.REP)

        # Set up the event subscription

        self.event_subscription = EventSubscriber(subscriptions=self.get_event_subscriptions())
        self.event_subscription.connect()

        # Initialise the poll set

        self.poller.register(self.dev_ctrl_service_sock, zmq.POLLIN)
        self.poller.register(self.dev_ctrl_mon_sock, zmq.POLLIN)  # FIXME: I think this should not be registered
        self.poller.register(self.event_subscription.socket, zmq.POLLIN)

        token = os.getenv("INFLUXDB3_AUTH_TOKEN")
        project = os.getenv("PROJECT")

        if project and token:
            self.metrics_client = get_metrics_repo(
                "influxdb", {"host": "http://localhost:8181", "database": project, "token": token}
            )
            # self.metrics_client = get_metrics_repo("duckdb", {"db_path": "duckdb_metrics.db", "table_name": "cs_timeseries"})
            self.metrics_client.connect()
        else:
            self.metrics_client = None
            logger.warning(
                "INFLUXDB3_AUTH_TOKEN and/or PROJECT environment variable is not set. "
                "Metrics will not be propagated to InfluxDB."
            )

    def get_event_subscriptions(self) -> list[str]:
        """Override this in the subclass to actually subscribe to events."""
        return []

    def get_event_handlers(self) -> dict[str, Callable]:
        """Override this in the subclass to provide methods to handle each of the subscriptions."""
        return {}

    @abc.abstractmethod
    def get_communication_protocol(self) -> str:
        """Returns the communication protocol used by the Control Server.

        Returns:
            Communication protocol used by the Control Server, as specified in the settings.
        """

        pass

    @abc.abstractmethod
    def get_commanding_port(self) -> int:
        """Returns the commanding port used by the Control Server.

        Returns:
            Commanding port used by the Control Server, as specified in the settings.
        """

        pass

    @abc.abstractmethod
    def get_service_port(self) -> int:
        """Returns the service port used by the Control Server.

        Returns:
            Service port used by the Control Server, as specified in the settings.
        """

        pass

    @abc.abstractmethod
    def get_monitoring_port(self) -> int:
        """Returns the monitoring port used by the Control Server.

        Returns:
            Monitoring port used by the Control Server, as specified in the settings.
        """

        pass

    def get_ip_address(self) -> str:
        """Returns the IP address of the current host."""
        return get_host_ip()

    def get_storage_mnemonic(self) -> str:
        """Returns the storage mnemonics used by the Control Server.

        This is a string that will appear in the filename with the housekeeping information of the device, as a way of
        identifying the device.  If this is not implemented in the subclass, then the class name will be used.

        Returns:
            Storage mnemonics used by the Control Server, as specified in the settings.
        """

        return self.__class__.__name__

    def get_process_status(self) -> dict:
        """Returns the process status of the Control Server.

        Returns:
            Dictionary with the process status of the Control Server.
        """

        return self._process_status.as_dict()

    def get_average_execution_times(self) -> dict:
        """Returns the average execution times of all functions that have been monitored by this process.

        Returns:
            Dictionary with the average execution times of all functions that have been monitored by this process.
                The dictionary keys are the function names, and the values are the average execution times in ms.
        """

        return get_average_execution_times()

    def set_mon_delay(self, seconds: float) -> float:
        """Sets the delay time for monitoring.

        The delay time is the time between two successive executions of the `get_status()` function of the device
        protocol.

        It might happen that the delay time that is set is longer than what you requested. That is the case when the
        execution of the `get_status()` function takes longer than the requested delay time. That should prevent the
        server from blocking when a too short delay time is requested.

        Args:
            seconds (float): Number of seconds between the monitoring calls

        Returns:
            Delay that was set [ms].
        """

        execution_time = get_average_execution_time(self.device_protocol.get_status)
        self.mon_delay = max(seconds * 1000, (execution_time + 0.2) * 1000)

        return self.mon_delay

    def set_hk_delay(self, seconds: float) -> float:
        """Sets the delay time for housekeeping.

        The delay time is the time between two successive executions of the `get_housekeeping()` function of the device
        protocol.

        It might happen that the delay time that is set is longer than what you requested. That is the case when the
        execution of the `get_housekeeping()` function takes longer than the requested delay time. That should prevent
        the server from blocking when a too short delay time is requested.

        Args:
            seconds (float): Number of seconds between the housekeeping calls

        Returns:
            Delay that was set [ms].
        """

        execution_time = get_average_execution_time(self.device_protocol.get_housekeeping)
        self.hk_delay = max(seconds * 1000, (execution_time + 0.2) * 1000)

        return self.hk_delay

    def set_scheduled_task_delay(self, seconds: float):
        """
        Sets the delay time between successive executions of scheduled tasks.

        Args:
            seconds: the time interval between two successive executions [seconds]

        """
        self.scheduled_task_delay = seconds

    def set_logging_level(self, level: Union[int, str]) -> None:
        """Sets the logging level to the given level.

        Allowed logging levels are:

        - "CRITICAL" or "FATAL" or 50
        - "ERROR" or 40
        - "WARNING" or "WARN" or 30
        - "INFO" or 20
        - "DEBUG" or 10
        - "NOTSET" or 0

        Args:
            level (int | str): Logging level to use, specified as either a string or an integer
        """

        self.logger.setLevel(level=level)

    def quit(self) -> None:
        """Interrupts the Control Server."""

        self.interrupted = True

    def before_serve(self) -> None:
        """
        This method needs to be overridden by the subclass if certain actions need to be executed before the control
        server is activated.
        """

        pass

    def after_serve(self) -> None:
        """
        This method needs to be overridden by the subclass if certain actions need to be executed after the control
        server has been deactivated.
        """

        pass

    def is_storage_manager_active(self) -> bool:
        """Checks if the Storage Manager is active.

        This method has to be implemented by the subclass if you need to store information.

        Note: You might want to set a specific timeout when checking for the Storage Manager.

        Note: If this method returns True, the following methods shall also be implemented by the subclass:

        - register_to_storage_manager()
        - unregister_from_storage_manager()
        - store_housekeeping_information()

        Returns:
            True if the Storage Manager is active; False otherwise.
        """

        return False

    def handle_scheduled_tasks(self):
        """
        Executes or reschedules tasks in the `serve()` event loop.
        """
        self.scheduled_tasks.reverse()
        rescheduled_tasks = []
        while self.scheduled_tasks:
            task_info = self.scheduled_tasks.pop()
            task = task_info["task"]
            task_name = task_info.get("name")

            at = task_info.get("after")
            if at and at > datetime.datetime.now(tz=datetime.timezone.utc):
                # logger.debug(f"Task {task_name} rescheduled, not time yet....")
                rescheduled_tasks.append(task_info)
                continue

            condition = task_info.get("when")
            if condition and not condition():
                logger.debug(f"Task {task_name} rescheduled in {self.scheduled_task_delay}s, condition not met....")
                self.logger.info(f"Task {task_name} rescheduled in {self.scheduled_task_delay}s")
                current_time = datetime.datetime.now(tz=datetime.timezone.utc)
                scheduled_time = current_time + datetime.timedelta(seconds=self.scheduled_task_delay)
                task_info["after"] = scheduled_time
                rescheduled_tasks.append(task_info)
                continue

            self.logger.debug(f"Running scheduled task: {task_name}")
            try:
                task()
            except Exception as exc:
                # self.logger.exception(exc, exc_info=True, stack_info=True)
                self.logger.error(f"Task {task_name} has failed: {exc!r}")
                self.logger.info(f"Task {task_name} rescheduled in {self.scheduled_task_delay}s")
                current_time = datetime.datetime.now(tz=datetime.timezone.utc)
                scheduled_time = current_time + datetime.timedelta(seconds=self.scheduled_task_delay)
                task_info["after"] = scheduled_time
                rescheduled_tasks.append(task_info)
            else:
                self.logger.debug(f"Scheduled task finished: {task_name}")

        if self.scheduled_tasks:
            self.logger.warning(f"There are still {len(self.scheduled_tasks)} scheduled tasks.")

        if rescheduled_tasks:
            self.scheduled_tasks.append(*rescheduled_tasks)

    def schedule_task(self, callback: Callable, after: float = 0.0, when: Callable = None):
        """
        Schedules a task to run in the control server event loop.

        The `callback` function will be executed as soon as possible in the `serve()` event loop.

        Some simple scheduling options are available:

        * after: the task will only execute 'x' seconds after the time of scheduling. I.e.
          the task will be rescheduled until time > scheduled time + 'x' seconds.
        * when: the task will only execute when the condition is True.

        The `after` and the `when` arguments can be combined.

        Note:
            * This function is intended to be used in order to prevent a deadlock.
            * Since the `callback` function is executed in the `serve()` event loop, it shall not block!

        """
        try:
            name = callback.func.__name__ if isinstance(callback, partial) else callback.__name__
        except AttributeError:
            name = "unknown"

        current_time = datetime.datetime.now(tz=datetime.timezone.utc)
        scheduled_time = current_time + datetime.timedelta(seconds=after)

        self.logger.info(f"Task {name} scheduled")

        self.scheduled_tasks.append({"task": callback, "name": name, "after": scheduled_time, "when": when})

    def setup_event_subscription(self):
        for event_type, handler in self.get_event_handlers().items():
            self.logger.info(f"Registering handler {type_name(handler)} for {event_type}")
            self.event_subscription.register_handler(event_type, handler)

    def serve(self) -> None:
        """Activation of the Control Server.

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

        self.setup_signaling()

        self.before_serve()

        self.setup_event_subscription()

        # check if Storage Manager is available

        storage_manager = self.is_storage_manager_active()

        storage_manager and self.register_to_storage_manager()

        # This approach is very simplistic and not time efficient
        # We probably want to use a Timer that executes the monitoring and saving actions at
        # dedicated times in the background.

        # FIXME: we shall use the time.perf_counter() here!

        last_time = time_in_ms()
        last_time_hk = time_in_ms()

        killer = SignalCatcher()

        while True:
            self.signaling.process_pending_commands()
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

            if self.event_subscription.socket in socks:
                with Timer("Handling notification event"):
                    self.event_subscription.handle_event()

            # Handle sending out monitoring information periodically, based on the MON_DELAY time that is specified in
            # the YAML configuration file for the device

            if time_in_ms() - last_time >= self.mon_delay:
                last_time = time_in_ms()
                # self.logger.debug("Sending status to monitoring processes.")
                try:
                    self.monitoring_protocol.send_status(save_average_execution_time(self.device_protocol.get_status))
                except Exception as exc:
                    logger.error(
                        textwrap.dedent(
                            f"""\
                            An Exception occurred while collecting status info from the control server \
                             {self.__class__.__name__}.
                            This might be a temporary problem, still needs to be looked into:

                            {exc}
                            """
                        )
                    )

            if time_in_ms() - last_time_hk >= self.hk_delay:
                last_time_hk = time_in_ms()
                # if storage_manager:
                # self.logger.debug("Sending housekeeping information to Storage.")
                try:
                    hk_dict = save_average_execution_time(self.device_protocol.get_housekeeping)

                    self.store_housekeeping_information(hk_dict)
                    self.propagate_metrics(hk_dict)
                except Exception as exc:
                    logger.error(
                        textwrap.dedent(
                            f"""{type_name(exc)}
                            An Exception occurred while collecting housekeeping from the device to be stored in {self.get_storage_mnemonic()}.
                            This might be a temporary problem, still needs to be looked into:
        
                            {exc}
                            """
                        )
                    )

            # Handle scheduled tasks/callback functions

            self.handle_scheduled_tasks()

            if self.interrupted:
                self.logger.info(f"Quit command received, closing down the {self.__class__.__name__}.")
                break

            if killer.term_signal_received:
                self.logger.info(f"TERM Signal received, closing down the {self.__class__.__name__}.")
                break

            # Some device protocol subclasses might start a number of threads or processes to support the commanding.
            # Check if these threads/processes are still alive and terminate gracefully if they are not.

            if not self.device_protocol.is_alive():
                self.logger.error("Some Thread or sub-process that was started by Protocol has died, terminating...")
                break

        storage_manager and self.unregister_from_storage_manager()

        self.after_serve()

        self.registry.disconnect()

        self.device_protocol.quit()

        self.dev_ctrl_mon_sock.close(linger=0)
        self.dev_ctrl_service_sock.close(linger=0)
        self.dev_ctrl_cmd_sock.close(linger=0)

        self.event_subscription.disconnect()

        close_all_zmq_handlers()

        # Since we closed all ZeroMQ handlers, we shall use standard logging from here.
        # logging.info("Terminating the ZeroMQ Context.")

        self.zcontext.term()

    def setup_signaling(self):
        self.signaling = FileBasedSignaling(self.service_name)
        self.signaling.start_monitoring()
        self.signaling.register_handler("reregister", self._reregister_service)

    def _reregister_service(self, force: bool = False):
        self.logger.info(f"Re-registration of service: {self.service_name} ({force=})")

        if self.registry.get_service(self.service_id):
            if force is True:
                self.deregister_service()
            else:
                return

        self.register_service(self.service_type)

    def register_service(self, service_type: str):
        self.logger.info(f"Registering service {self.service_name} as type {service_type}")
        self.service_type = service_type
        self.service_id = self.registry.register(
            name=self.service_name,
            host=get_host_ip() or "127.0.0.1",
            port=get_port_number(self.dev_ctrl_cmd_sock),
            service_type=self.service_type,
            metadata={
                "service_port": get_port_number(self.dev_ctrl_service_sock),
                "monitoring_port": get_port_number(self.dev_ctrl_mon_sock),
            },
        )
        self.registry.start_heartbeat()

    def deregister_service(self):
        if self.registry:
            self.registry.stop_heartbeat()
            self.registry.deregister(self.service_id)

    def store_housekeeping_information(self, data: dict) -> None:
        """Sends housekeeping information to the Storage Manager.

        This method has to be overwritten by the subclasses if they want the device housekeeping information to be
        saved.

        Args:
            data (dict): a dictionary containing parameter name and value of all device housekeeping. There is also
                a timestamp that represents the date/time when the HK was received from the device.
        """
        pass

    def propagate_metrics(self, hk: dict) -> None:
        """
        Propagates the given housekeeping information to the metrics database.

        Nothing will be written to the metrics database if the `hk` dict doesn't
        contain any metrics (except for the timestamp).

        Args:
            hk (dict): Dictionary containing parameter name and value of all device housekeeping. There is also
                       a timestamp that represents the date/time when the HK was received from the device.
        """

        origin = self.get_storage_mnemonic()

        if not [x for x in hk if x != "timestamp"]:
            logger.debug(f"no metrics defined for {origin}")
            return

        try:
            if self.metrics_client:
                point = {
                    "measurement": origin.lower(),
                    "tags": {"site_id": SITE_ID, "origin": origin},
                    "fields": {hk_name.lower(): hk[hk_name] for hk_name in hk if hk_name != "timestamp"},
                    "time": str_to_datetime(hk["timestamp"]),
                }
                self.metrics_client.write(point)
            else:
                logger.warning(
                    f"Could not write {origin} metrics to the time series database (self.metrics_client is None)."
                )
        except NewConnectionError:
            logger.warning(
                f"No connection to the time series database could be established to propagate {origin} metrics.  Check "
                f"whether this service is (still) running."
            )

    def register_to_storage_manager(self) -> None:
        """Registers this Control Server to the Storage Manager.

        By doing so, the housekeeping information of the device will be sent to the Storage Manager, which will store
        the information in a dedicated CSV file.

        This method has to be overwritten by the subclasses if they have housekeeping information that must be stored.

        Subclasses need to overwrite this method if they have housekeeping information to be stored.

        The following   information is required for the registration:

        - origin: Storage mnemonic, which can be retrieved from `self.get_storage_mnemonic()`
        - persistence_class: Persistence layer (one of the TYPES in egse.storage.persistence)
        - prep: depending on the type of the persistence class (see respective documentation)

        The `egse.storage` module provides a convenience method that can be called from the method in the subclass:

            >>> from egse.storage import register_to_storage_manager  # noqa

        Note:
            the `egse.storage` module might not be available, it is provided by the `cgse-core` package.
        """
        pass

    def unregister_from_storage_manager(self) -> None:
        """Unregisters the Control Server from the Storage Manager.

        This method has to be overwritten by the subclasses.

        The following information is required for the registration:

        - origin: Storage mnemonic, which can be retrieved from `self.get_storage_mnemonic()`

        The `egse.storage` module provides a convenience method that can be called from the method in the subclass:

            >>> from egse.storage import unregister_from_storage_manager  # noqa

        Note:
            the `egse.storage` module might not be available, it is provided by the `cgse-core` package.
        """

        pass

    def notify_listeners(self, event_id: int = 0, context: dict = None):
        """
        Notifies registered listeners about an event.

        This function creates an Event object with the provided `event_id` and `context`
        and notifies all registered listeners with the created event.

        Args:
            event_id (int, optional): The identifier for the event. Defaults to 0.
            context (dict, optional): Additional context information associated with the event.
                Defaults to None.

        Note:
            The notification is performed by the `notify_listeners` method of the `listeners` object
            associated with this instance.
            The notification is executed in a daemon thread to avoid blocking the commanding
            chain.

        """
        from egse.listener import Event, EVENT_ID

        self.logger.info(f"Notifying listeners for {EVENT_ID(event_id).name}")

        retry_thread = threading.Thread(
            target=self.listeners.notify_listeners, args=(Event(event_id=event_id, context=context),)
        )
        retry_thread.daemon = True
        retry_thread.start()

    def get_listener_names(self):
        return self.listeners.get_listener_names()

    def register_as_listener(self, proxy: Type, listener: dict):
        """
        Registers a listener with the specified proxy.

        This function attempts to add the provided listener to the specified proxy.
        It employs a retry mechanism to handle potential ConnectionError exceptions,
        making up to 5 attempts to add the listener.

        Args:
            proxy: A callable object representing the proxy to which the listener will be added.
            listener (dict): The listener to be registered. Should be a dictionary containing
                listener details.

        Raises:
            ConnectionError: If the connection to the proxy encounters issues even after
                multiple retry attempts.

        Note:
            The function runs in a separate daemon thread to avoid blocking the main thread.

        """

        @retry_with_exponential_backoff(exceptions=[ConnectionError])
        def _add_listener(proxy, listener):
            try:
                with proxy() as x, x.get_service_proxy() as srv:
                    response = srv.add_listener(listener)
                    logger.info(f"Response from {proxy.__name__} service add_listener: {response}")
            except Exception as exc:
                logger.error(f"Caught {type_name(exc)}: {exc} – listener '{listener['name']}' could not be registered")

        logger.info(f"Registering {self.__class__.__name__} as a listener to {proxy.__name__}")

        retry_thread = threading.Thread(target=_add_listener, args=(proxy, listener))
        retry_thread.daemon = True
        retry_thread.start()

    def unregister_as_listener(self, proxy: Type, listener: dict):
        """
        Removes a registered listener from the specified proxy.

        This function attempts to remove the provided listener from the specified proxy.
        It employs a retry mechanism to handle potential ConnectionError exceptions,
        making up to 5 attempts to add the listener.

        Args:
            proxy: A callable object representing the proxy from which the listener will be removed.
            listener (dict): The listener to be removed. Should be a dictionary containing
                listener details.

        Raises:
            ConnectionError: If the connection to the proxy encounters issues even after
                multiple retry attempts.

        Note:
            The function runs in a separate thread but will block until the de-registration is finished.
            The reason being that this method is usually called in a `after_serve` block so it needs to
            finish before the ZeroMQ context is destroyed.

        """

        @retry(times=5, exceptions=[ConnectionError])
        def _remove_listener(proxy, listener):
            with proxy() as x, x.get_service_proxy() as srv:
                rc = srv.remove_listener(listener)
                logger.debug(f"Response from remove_listener: {rc=}")

        # Since we do not have the endpoint available, we can not check if the CS is active, and to get the endpoint
        # we have to use the proxy anyway. So, let's use the proxy object to check if the CS is available.

        try:
            with proxy():
                pass
        except ConnectionError:
            logger.warning(
                f"The {proxy.__class__.__name__} endpoint is not responding, {listener['name']} not un-registered."
            )
            return

        logger.info(f"Removing {self.__class__.__name__} as a listener from {proxy.__name__}")

        retry_thread = threading.Thread(target=_remove_listener, args=(proxy, listener))
        retry_thread.daemon = False
        retry_thread.start()

        # Block until the listener has been removed. This is needed because this unregister function will usually
        # be called in the `after_server()` method of the control server (which is the listener) and if we do not
        # wait until the thread is finished the ZeroMQ Context will be destroyed before the reply can be sent.
        # Note: we could probably do without the thread, and directly call the `_remove_listener()` function.

        retry_thread.join()
