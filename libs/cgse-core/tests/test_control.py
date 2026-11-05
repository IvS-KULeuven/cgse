from types import SimpleNamespace

from egse.control import ControlServer


def test_device_status_for_monitoring():
    """The sync control server adds the device status to every monitoring message; an error doesn't stop them."""
    server = SimpleNamespace(get_device_status=lambda: {"connected": True, "sim_mode": None})
    assert ControlServer.get_device_status_for_monitoring(server) == {"connected": True, "sim_mode": None}

    def broken():
        raise RuntimeError("no device")

    server = SimpleNamespace(get_device_status=broken)
    assert ControlServer.get_device_status_for_monitoring(server) == {"error": "RuntimeError: no device"}
