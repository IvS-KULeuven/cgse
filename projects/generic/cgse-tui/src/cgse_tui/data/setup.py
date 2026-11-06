"""The device drivers of the project, from the Setup that the Configuration Manager has loaded.

A node in the Setup describes a device driver when it has a `cgse_object`: the `cgse <object>` command that starts,
stops and shows the status of its control server. It can have a `device_name`, shown as the name, and a `device_id`
when there are several devices of the same type, e.g.

    gse:
        DAQ6510:
            device_name: Keithley DAQ6510
            cgse_object: daq6510
            ...
        hexapod:
            device_name: PUNA Hexapod
            cgse_object: puna
            device_id: PUNA_01

The TUI shows every device driver of the Setup: a running one as the service in the registry, one that isn't
running as a row that can be started.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SETUP_PREFIX = "setup:"
"""The key of a device of the Setup that isn't running starts with this prefix; it has no service type yet."""


@dataclass(frozen=True)
class SetupDevice:
    """A device driver in the Setup."""

    cgse_object: str
    device_id: str | None
    name: str
    path: str
    """Where the device is in the Setup, e.g. "gse.DAQ6510"."""

    @property
    def key(self) -> str:
        """The key of the row of the device while it isn't running, e.g. "setup:puna:PUNA_01"."""
        return f"{SETUP_PREFIX}{self.cgse_object}:{self.device_id or ''}"


def setup_devices(setup: Mapping[str, Any], path: str = "") -> list[SetupDevice]:
    """Returns the device drivers in the Setup: the nodes with a `cgse_object`, in the order of the Setup.

    A device node is not searched further, its sub-nodes are its configuration.
    """
    devices = []
    for key, node in setup.items():
        if not isinstance(node, Mapping):
            continue
        node_path = f"{path}.{key}" if path else str(key)
        cgse_object = node.get("cgse_object")
        if isinstance(cgse_object, str) and cgse_object:
            device_id = node.get("device_id")
            devices.append(
                SetupDevice(
                    cgse_object=cgse_object,
                    device_id=None if device_id is None else str(device_id),
                    name=str(node.get("device_name") or key),
                    path=node_path,
                )
            )
        else:
            devices.extend(setup_devices(node, node_path))
    return devices


def matches(device: SetupDevice, cgse_object: str | None, device_id: str | None) -> bool:
    """True when a service with this `cgse_object` and `device_id` is the device of the Setup.

    A device without `device_id` in the Setup matches every service of its `cgse_object`.
    """
    if cgse_object != device.cgse_object:
        return False
    return device.device_id is None or str(device_id) == device.device_id
