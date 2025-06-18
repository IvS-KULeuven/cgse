import pytest

from egse.device import DeviceConnectionObservable
from egse.device import DeviceConnectionObserver
from egse.device import DeviceConnectionState
from egse.device import DeviceError


def test_device_error():
    # DeviceError expects two positional arguments: 'device_name' and 'message'

    with pytest.raises(TypeError):
        raise DeviceError()


def test_device_error_with_args():
    with pytest.raises(DeviceError) as exc:
        raise DeviceError("DAQ6510", "A generic device error")

    assert isinstance(exc.value, DeviceError)
    assert any("generic" in arg for arg in exc.value.args)
    assert any("DAQ" in arg for arg in exc.value.args)
    assert str(exc.value) == "DAQ6510: A generic device error"


def test_device_connection_observable():
    class MyDevice(DeviceConnectionObservable): ...

    class MyDeviceViewer(DeviceConnectionObserver): ...

    my_device = MyDevice()

    my_viewer = MyDeviceViewer()

    my_device.add_observer(my_viewer)

    assert my_device.get_observers().count(my_viewer) == 1

    assert my_viewer.state == DeviceConnectionState.DEVICE_NOT_CONNECTED

    my_device.notify_observers(DeviceConnectionState.DEVICE_CONNECTED)

    assert my_viewer.state == DeviceConnectionState.DEVICE_CONNECTED

    my_device.delete_observer(my_viewer)

    assert my_device.get_observers().count(my_viewer) == 0
