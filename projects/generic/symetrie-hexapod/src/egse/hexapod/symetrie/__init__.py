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
import os

from egse.device import DeviceFactoryInterface
from egse.settings import Settings, SettingsError

PUNA_SETTINGS = Settings.load("PMAC Controller")


def get_hexapod_controller_pars(setup: 'Setup' = None) -> (str, int, str, str, str):
    """
    Returns the hostname (str), port number (int), hexapod id (str), hexapod name (str),
    and type (str) for the hexapod controller as defined in the Setup and Settings.

    Note the returned values are for the device hardware controller, not the control server.

    If no setup argument is provided, the Setup will be loaded from the GlobalState.
    """

    from egse.setup import SetupError, load_setup

    setup = setup or load_setup()

    try:
        try:
            hexapod_id = setup.gse.hexapod.device_args.device_id
            hexapod_name: str = setup.gse.hexapod.device_args.device_name
        except AttributeError:
            # Handle older Setups where no device_args existed for the PUNA hexapod
            hexapod_id = setup.gse.hexapod.ID
            hexapod_name: str = setup.gse.hexapod.device_name
    except AttributeError as exc:

        # Before quitting, try to load from environment variables

        hexapod_id = os.environ.get("SYMETRIE_HEXAPOD_ID")
        hexapod_name = os.environ.get("SYMETRIE_HEXAPOD_NAME")

        if hexapod_id is None or hexapod_name is None:
            raise SetupError("The Setup doesn't contain proper controller parameters for the Hexapod.") from exc

    hexapod_id = f"H_{hexapod_id}"

    try:
        hostname: str = PUNA_SETTINGS[hexapod_id]["HOSTNAME"]
        port: int = int(PUNA_SETTINGS[hexapod_id]["PORT"])
        controller_type: str = PUNA_SETTINGS[hexapod_id]["TYPE"]
    except (KeyError, AttributeError) as exc:
        raise SettingsError("The Settings do not contain proper controller parameters for the Hexapod.") from exc

    return hostname, port, hexapod_id, hexapod_name, controller_type


class ProxyFactory(DeviceFactoryInterface):
    """
    A factory class that will create the Proxy that matches the given device name and identifier.

    The device name is matched against the string 'puna' or 'zonda'. If the device name doesn't contain
    one of these names, a ValueError will be raised.
    """

    def create(self, device_name: str, *, device_id: str = None, **_ignored):

        if "puna" in device_name.lower():
            if not device_id.startswith("H_"):
                device_id = f"H_{device_id}"

            controller_type = PUNA_SETTINGS[device_id]["TYPE"]
            if controller_type == "ALPHA":
                from egse.hexapod.symetrie.puna import PunaProxy
                return PunaProxy()
            elif controller_type == "ALPHA_PLUS":
                from egse.hexapod.symetrie.punaplus import PunaPlusProxy
                return PunaPlusProxy()
            else:
                raise ValueError(f"Unknown controller_type ({controller_type}) for {device_name} – {device_id}")

        elif "zonda" in device_name.lower():
            from egse.hexapod.symetrie.zonda import ZondaProxy
            return ZondaProxy()

        elif "joran" in device_name.lower():
            from egse.hexapod.symetrie.joran import JoranProxy
            return JoranProxy()

        else:
            raise ValueError(f"Unknown device name: {device_name}")


class ControllerFactory(DeviceFactoryInterface):
    """
    A factory class that will create the Controller that matches the given device name and identifier.

    The device name is matched against the string 'puna', 'zonda', or 'joran'. If the device name doesn't contain
    one of these names, a ValueError will be raised.
    """
    def create(self, device_name: str, *, device_id: str = None, **_ignored):

        if "puna" in device_name.lower():
            from egse.hexapod.symetrie.puna import PunaController
            from egse.hexapod.symetrie.punaplus import PunaPlusController

            if not device_id.startswith("H_"):
                device_id = f"H_{device_id}"

            hostname = PUNA_SETTINGS[device_id]["HOSTNAME"]
            port = PUNA_SETTINGS[device_id]["PORT"]
            controller_type = PUNA_SETTINGS[device_id]["TYPE"]
            if controller_type == "ALPHA":
                return PunaController(hostname=hostname, port=port)
            elif controller_type == "ALPHA_PLUS":
                return PunaPlusController(hostname=hostname, port=port)
            else:
                raise ValueError(f"Unknown controller_type ({controller_type}) for {device_name} – {device_id}")

        elif "zonda" in device_name.lower():
            from egse.hexapod.symetrie.zonda import ZondaController
            return ZondaController()

        elif "joran" in device_name.lower():
            from egse.hexapod.symetrie.joran import JoranController
            return JoranController()

        else:
            raise ValueError(f"Unknown device name: {device_name}")
