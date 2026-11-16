"""The device drivers of the project, from the Setup that the Configuration Manager has loaded.

A node in the Setup describes a device driver when it has a `cgse_object`, see `egse.setup.find_cgse_devices()`.

The TUI shows every device driver of the Setup: a running one as the service in the registry, one that isn't
running as a row that can be started.
"""

from __future__ import annotations

from egse.setup import SetupDevice

SETUP_PREFIX = "setup:"
"""The key of a device of the Setup that isn't running starts with this prefix; it has no service type yet."""


def setup_key(device: SetupDevice) -> str:
    """The key of the row of the device while it isn't running, e.g. "setup:puna:PUNA_01"."""
    return f"{SETUP_PREFIX}{device.cgse_object}:{device.device_id or ''}"
