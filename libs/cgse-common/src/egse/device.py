"""
This module defines the generic interfaces to connect devices.
"""
from enum import IntEnum
from typing import List

from egse.decorators import dynamic_interface
from egse.exceptions import Error


class DeviceConnectionState(IntEnum):
    """Defines connection states for device connections."""

    # We do not use zero '0' as the connected state to prevent a state to be set
    # to connected by default without it explicitly being set. Therefore, 0 will
    # be the state where the connection is not explicitly set.

    DEVICE_CONNECTION_NOT_SET = 0
    DEVICE_CONNECTED = 1
    DEVICE_NOT_CONNECTED = 2


class DeviceError(Error):
    """Generic device error.

    Args:
        device_name (str): The name of the device
        message (str): a clear and brief description of the problem
    """

    def __init__(self, device_name: str, message: str):
        self.device_name = device_name
        self.message = message

    def __str__(self):
        return f"{self.device_name}: {self.message}"


class DeviceControllerError(DeviceError):
    """Any error that is returned by the device controller.

    When the device controller is connected through an e.g. Ethernet interface, it will usually
    return error codes as part of the response to a command. When such an error is returned,
    raise this `DeviceControllerError` instead of passing the return code (response) to the caller.

    Args:
        device_name (str): The name of the device
        message (str): a clear and brief description of the problem
    """
    def __init__(self, device_name: str, message: str):
        super().__init__(device_name, message)


class DeviceConnectionError(DeviceError):
    """A generic error for all connection type of problems.

    Args:
        device_name (str): The name of the device
        message (str): a clear and brief description of the problem
    """
    def __init__(self, device_name: str, message: str):
        super().__init__(device_name, message)


class DeviceTimeoutError(DeviceError):
    """A timeout on a device that we could not handle.

    Args:
        device_name (str): The name of the device
        message (str): a clear and brief description of the problem
    """
    def __init__(self, device_name: str, message: str):
        super().__init__(device_name, message)


class DeviceInterfaceError(DeviceError):
    """Any error that is returned or raised by the higher level interface to the device.

    Args:
        device_name (str): The name of the device
        message (str): a clear and brief description of the problem
    """
    def __init__(self, device_name: str, message: str):
        super().__init__(device_name, message)


class DeviceConnectionObserver:
    """
    An observer for the connection state of a device. Add the subclass of this class to
    the class that inherits from DeviceConnectionObservable. The observable will notify an
    update of its state by calling the `update_connection_state()` method.
    """
    def __init__(self):
        self._state = DeviceConnectionState.DEVICE_NOT_CONNECTED

    def update_connection_state(self, state: DeviceConnectionState):
        """Updates the connection state with the given state."""
        self._state = state

    @property
    def state(self):
        """Returns the current connection state of the device."""
        return self._state


class DeviceConnectionObservable:
    """
    An observable for the connection state of a device. An observer can be added with the
    `add_observer()` method. Whenever the connection state of the device changes, the subclass
    is responsible for notifying the observers by calling the `notify_observers()` method
    with the correct state.
    """
    def __init__(self):
        self._observers: List[DeviceConnectionObserver] = []

    def add_observer(self, observer: DeviceConnectionObserver):
        """Add an observer."""
        if observer not in self._observers:
            self._observers.append(observer)

    def notify_observers(self, state: DeviceConnectionState):
        """Notify the observers of a possible state change."""
        for observer in self._observers:
            observer.update_connection_state(state)


class DeviceConnectionInterface(DeviceConnectionObservable):
    """Generic connection interface for all Device classes and Controllers.

    This interface shall be implemented in the Controllers that directly connect to the
    hardware, but also in the simulators to guarantee an identical interface as the controllers.

    This interface will be implemented in the Proxy classes through the
    YAML definitions. Therefore, the YAML files shall define at least
    the following commands: `connect`, `disconnect`, `reconnect`, `is_connected`.
    """

    def __init__(self):
        super().__init__()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    @dynamic_interface
    def connect(self):
        """Connect to the device controller.

        Raises:
            ConnectionError: when the connection can not be opened.
        """
        raise NotImplementedError

    @dynamic_interface
    def disconnect(self):
        """Disconnect from the device controller.

        Raises:
            ConnectionError: when the connection can not be closed.
        """
        raise NotImplementedError

    @dynamic_interface
    def reconnect(self):
        """Reconnect the device controller.

        Raises:
            ConnectionError: when the device can not  be reconnected for some reason.
        """
        raise NotImplementedError

    @dynamic_interface
    def is_connected(self) -> bool:
        """Check if the device is connected.

        Returns:
            True if the device is connected and responds to a command, False otherwise.
        """
        raise NotImplementedError


class DeviceInterface(DeviceConnectionInterface):
    """Generic interface for all device classes."""

    @dynamic_interface
    def is_simulator(self) -> bool:
        """Ask if the device class is a Simulator instead of the real Controller.

        This can be useful for testing purposes or when doing actual movement simulations.

        Returns:
            True if the Device is a Simulator, False if the Device is connected to real hardware.
        """
        raise NotImplementedError


class DeviceTransport:
    """
    Base class for the device transport layer.
    """

    def write(self, command: str):
        """
        Sends a complete command to the device, handle line termination, and write timeouts.

        Args:
            command: the command to be sent to the instrument.
        """

        raise NotImplementedError()

    def read(self) -> bytes:
        """
        Reads a string back from the instrument.
        """

        raise NotImplementedError

    def trans(self, command: str) -> bytes:
        """
        Send a single command to the device controller and block until a response from the
        controller.

        Args:
            command: is the command to be sent to the instrument

        Returns:
            Either a string returned by the controller (on success), or an error message (on
            failure).

        Raises:
            DeviceConnectionError when there was an I/O problem during communication with the
            controller.

            DeviceTimeoutError when there was a timeout in either sending the command or
            receiving the response.
        """

        raise NotImplementedError

    def query(self, command: str) -> bytes:
        """
        Send a query to the device and wait for the response.

        This `query` method is an alias for the `trans` command. For some commands it might be
        more intuitive to use the `query` instead of the `trans`action. No need to override this
        method as it delegates to `trans`.

        Args:
            command (str): the query command.

        Returns:
            The response to the query.
        """
        return self.trans(command)


class DeviceFactoryInterface:
    """
    Base class for creating a device factory class to access devices.

    This interface defines one interface method that shall be implemented by the Factory:

        create(device_name: str, *, device_id: str, **_ignored)
    """

    def create(self, device_name: str, *, device_id: str, **_ignored):
        ...
