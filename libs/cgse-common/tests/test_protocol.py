import pickle
import types
from abc import ABC
from typing import Any

from egse.control import ControlServer
from egse.decorators import dynamic_interface
from egse.protocol import CommandProtocol
from egse.protocol import get_function
from egse.protocol import get_method
from egse.zmq_ser import bind_address


class _T:
    """A test class for the get_method() and get_function() functions."""

    _a = None

    def _m(self): ...

    @dynamic_interface
    def _di(self): ...


def test_get_method():
    assert get_method(_T, "_m") is None  # _m is a function for _T which is a class
    assert get_method(_T(), "") is None
    assert get_method(_T(), "None") is None
    assert get_method(_T(), None) is None

    assert get_method(_T(), "unknown") is None

    assert isinstance(get_method(_T(), "_m"), types.MethodType)
    assert isinstance(get_method(_T(), "_di"), types.MethodType)

    assert isinstance(get_method(_T(), "__getattribute__"), types.MethodWrapperType)


def test_get_function():
    assert get_function(_T, "") is None
    assert get_function(_T, "None") is None
    assert get_function(_T, None) is None

    assert get_function(_T, "unknown") is None
    assert get_function(_T, "_a") is None

    assert isinstance(get_function(_T, "_m"), types.FunctionType)
    assert isinstance(get_function(_T, "_di"), types.FunctionType)


class InternalCommunication:
    def __init__(self):
        self._status = 0
        self._pickle_string: bytes = bytes()

    def send(self, data):
        self._pickle_string = pickle.dumps(data)

    def receive(self) -> Any:
        """
        Returns an object based on the last command that was sent and based on
        the status of the internal communication.
        """
        data = pickle.loads(self._pickle_string)
        return data


class ControlServerMock(ControlServer):
    def __init__(self):
        super().__init__()
        self.mon_delay = 23

    def get_communication_protocol(self) -> str:
        return "tcp"

    def get_commanding_port(self) -> int:
        return 55555

    def get_service_port(self) -> int:
        return 55556

    def get_monitoring_port(self) -> int:
        return 55557


# Why are there only two abstract methods?
# - get_status()
# - get_bind_address()
# Why are the following methods also not abstract?
# - get_housekeeping()
# -
class _TestCommandProtocol(CommandProtocol):
    """A test class to unit test the CommandProtocol."""

    def __init__(self):
        super().__init__(ControlServerMock())
        self._comm = InternalCommunication()

    def get_status(self) -> dict:
        return super().get_status()

    def get_bind_address(self) -> str:
        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def receive(self) -> Any:
        """Overwrites the parent class method"""
        response = self._comm.receive()
        return response

    def send(self, data):
        self._comm.send(data)


def test_command_protocol():
    tcp = _TestCommandProtocol()

    status = tcp.get_status()

    assert "timestamp" in status
    assert "PID" in status
