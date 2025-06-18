"""
Device control for the Symétrie Hexapod PUNA, ZONDA, and JORAN.

This package contains the modules and classes to work with the Hexapod PUNA, the Hexapod ZONDA, and the Hexapod JORAN
from [Symétrie](www.symetrie.fr).

The main entry point for the user of this package is through the terminal commands to start the
control servers for the PUNA, ZONDA, and JORAN Hexapod, and the GUIs that are provided to interact with
the hexapods. The following commands start the control servers for the PUNA, ZONDA, and JORAN
in the background.

    $ puna_cs start-bg
    $ zonda_cs start-bg
    $ joran_cs start-bg

The GUIs can be started with the following commands:

    $ puna_ui
    $ zonda_ui
    $ joran_ui

For developers, the `PunaProxy`, `ZondaProxy`, and `JoranProxy` classes are the main interface to command the
hardware.

For the PUNA:
    >>> from egse.hexapod.symetrie.puna import PunaProxy
    >>> puna = PunaProxy()

For the ZONDA:

    >>> from egse.hexapod.symetrie.zonda import ZondaProxy
    >>> zonda = ZondaProxy()

For the JORAN:

    >>> from egse.hexapod.symetrie.joran import JoranProxy
    >>> joran = JoranProxy()

These classes will connect to their control servers and provide all commands to
control the hexapod and monitor its positions and status.


"""

import logging
from typing import NamedTuple

from egse.device import DeviceFactoryInterface
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.settings import SettingsError

logger = logging.getLogger("egse.hexapod.symetrie")

HEXAPOD_SETTINGS = Settings.load("Hexapod Controller")

HexapodInfo = NamedTuple(
    "HexapodInfo",
    [
        ("hostname", str),
        ("port", int),
        ("device_id", str),
        ("device_name", str),
        ("device_type", str),
        ("controller_type", str),
    ],
)


def get_hexapod_controller_pars(device_id: str) -> HexapodInfo:
    """
    Returns a NamedTuple HexapodInfo with the hostname (str), port number (int),
    device id (str), device name (str), device_type (str) and controller type (str)
    for the hexapod controller as defined in the Settings.

    Note the returned values are for the device hardware controller, not the control server.

    All values are derived from the Settings.
    """

    logger.debug(f"Getting parameters for {device_id} controller...")

    try:
        hostname: str = HEXAPOD_SETTINGS[device_id]["HOSTNAME"]
        port: int = int(HEXAPOD_SETTINGS[device_id]["PORT"])
        controller_type: str = HEXAPOD_SETTINGS[device_id]["CONTROLLER_TYPE"]
        device_name: str = HEXAPOD_SETTINGS[device_id]["DEVICE_NAME"]
        device_type: str = HEXAPOD_SETTINGS[device_id]["DEVICE_TYPE"]
    except (KeyError, AttributeError) as exc:
        raise SettingsError("The Settings do not contain proper controller parameters for the Hexapod.") from exc

    logger.debug(f"{hostname=}, {port=}, {device_id=}, {device_name=}, {device_type=}, {controller_type=}")
    return HexapodInfo(hostname, port, device_id, device_name, device_type, controller_type)


class ProxyFactory(DeviceFactoryInterface):
    """
    A factory class that will create the Proxy that matches the given device name and identifier.

    The device name is matched against the string 'puna' or 'zonda'. If the device name doesn't contain
    one of these names, a ValueError will be raised.
    """

    def create(self, device_type: str, *, device_id: str = None, **_ignored):
        with RegistryClient() as reg:
            service = reg.discover_service(device_id)

            if service:
                protocol = service.get("protocol", "tcp")
                hostname = service["host"]
                port = service["port"]

            else:
                raise RuntimeError(f"No service registered as {device_id}")

        if "puna" in device_type.lower():
            controller_type = HEXAPOD_SETTINGS[device_id]["CONTROLLER_TYPE"]
            if controller_type.lower() == "alpha":
                from egse.hexapod.symetrie.puna import PunaProxy

                return PunaProxy(protocol, hostname, port)
            elif controller_type == "alpha_plus":
                from egse.hexapod.symetrie.punaplus import PunaPlusProxy

                return PunaPlusProxy(protocol, hostname, port)
            else:
                raise ValueError(f"Unknown controller_type ({controller_type}) for {device_type} – {device_id}")

        elif "zonda" in device_type.lower():
            from egse.hexapod.symetrie.zonda import ZondaProxy

            return ZondaProxy(protocol, hostname, port)

        elif "joran" in device_type.lower():
            from egse.hexapod.symetrie.joran import JoranProxy

            return JoranProxy(protocol, hostname, port)

        else:
            raise ValueError(f"Unknown device type: {device_type}")


class ControllerFactory(DeviceFactoryInterface):
    """
    A factory class that will create the Controller that matches the given device name and identifier.

    The device name is matched against the string 'puna', 'zonda', or 'joran'. If the device name doesn't contain
    one of these names, a ValueError will be raised.
    """

    def create(self, device_type: str, *, device_id: str = None, **_ignored):
        if "puna" in device_type.lower():
            from egse.hexapod.symetrie.puna import PunaController
            from egse.hexapod.symetrie.punaplus import PunaPlusController

            hostname = HEXAPOD_SETTINGS[device_id]["HOSTNAME"]
            port = HEXAPOD_SETTINGS[device_id]["PORT"]
            controller_type = HEXAPOD_SETTINGS[device_id]["CONTROLLER_TYPE"]
            if controller_type.lower() == "alpha":
                return PunaController(hostname=hostname, port=port)
            elif controller_type.lower() == "alpha_plus":
                return PunaPlusController(hostname=hostname, port=port)
            else:
                raise ValueError(f"Unknown controller_type ({controller_type}) for {device_type} – {device_id}")

        elif "zonda" in device_type.lower():
            from egse.hexapod.symetrie.zonda import ZondaController

            hostname = HEXAPOD_SETTINGS[device_id]["HOSTNAME"]
            port = HEXAPOD_SETTINGS[device_id]["PORT"]

            return ZondaController(hostname=hostname, port=port)

        elif "joran" in device_type.lower():
            from egse.hexapod.symetrie.joran import JoranController

            return JoranController()

        else:
            raise ValueError(f"Unknown device name: {device_type}")
