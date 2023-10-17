"""
The Exception Hierarchy:

Exception
 +-- CommonEGSEException
      +-- Warning
      +-- Error
          +-- InvalidOperationError
          +-- DeviceNotFoundError (should move to subclass of DeviceError)
          +-- InternalStateError
          +-- DeviceError
               +-- DeviceControllerError
               +-- DeviceConnectionError
               +-- DeviceTimeoutError
               +-- DeviceInterfaceError
 +-- Failure
 +-- HexapodError
 +-- PMACError
 +-- OGSEError
 +-- ESLError
 +-- FilterWheelError
 +-- FilterWheel8smc4Error
 +-- ShutterKSC1010Error
 +-- WindowSizeError
 +-- SettingsError
 +-- StagesError

"""


class CommonEGSEException(Exception):
    """The base exception for all errors and warnings in the Common-EGSE."""

    pass


class Error(CommonEGSEException):
    """The base class for all Common-EGSE Errors."""

    pass


class Warning(CommonEGSEException):
    """The base class for all Common-EGSE Warnings."""

    pass


class FileIsEmptyError(Error):
    """Raised when a file is empty and that is unexpected."""
    pass


class InvalidOperationError(Error):
    """
    Raised when a certain operation is not valid in the given state,
    circumstances or environment.
    """

    pass


class InvalidInputError(Error):
    """ Exception raised when the input is invalid after editing."""

    pass


class DeviceNotFoundError(Error):
    """Raised when a device could not be located, or loaded."""

    pass


class InternalStateError(Error):
    """Raised when an object encounters an internal state inconsistency."""

    pass


class InternalError(Error):
    """Raised when an internal inconsistency occurred in a function, method or class."""

    pass


class Abort(RuntimeError):
    """Internal Exception to signal a process to abort."""
