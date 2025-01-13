import pytest

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
