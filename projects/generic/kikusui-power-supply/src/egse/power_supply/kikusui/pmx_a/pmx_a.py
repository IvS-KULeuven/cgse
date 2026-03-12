from egse.mixin import DynamicCommandMixin
from egse.power_supply.kikusui import PROXY_TIMEOUT
from egse.power_supply.kikusui.pmx import PmxInterface
from egse.power_supply.kikusui.pmx_a import CS_SETTINGS
from egse.power_supply.kikusui.pmx_devif import PmxEthernetInterface
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address


class PmxAInterface(PmxInterface):
    """Base class for KIKUSUI PMX-A power supply units."""

    def __init__(self, device_id: str):
        """Initialisation of a KIKUSUI PMX-A interface.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)


class PmxAController(PmxAInterface, DynamicCommandMixin):
    def __init__(self, device_id: str):
        """Initialisation of a controller for the KIKUSUI PMX-A device with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

        self.transport = self.pmx_a = PmxEthernetInterface(device_id=device_id)

    # noinspection PyMethodMayBeStatic
    def is_simulator(self):
        return False

    def is_connected(self):
        """Checks whether the connection to the KIKUSUI PMX-A is open.

        Returns:
            True if the connection to the KIKUSUI PMX-A is open; False otherwise.
        """

        return self.transport.is_connected()

    def connect(self):
        """Opens the connection to the KIKUSUI PMX-A.

        Raises:
            PmxAError: When the connection could not be opened.
        """

        self.transport.connect()

    def disconnect(self):
        """Closes the connection to the KIKUSUI PMX-A.

        Raises:
            Dt8874Error: When the connection could not be closed.
        """

        self.transport.disconnect()

    def reconnect(self):
        """Re-connects to the KIKUSUI PMX-A."""

        self.transport.reconnect()


class PmxASimulator(PmxAInterface):
    def __init__(self, device_id: str):
        """Initialisation of a simulator for the KIKUSUI PMX-A device with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

        self._is_connected = True

    # noinspection PyMethodMayBeStatic
    def is_simulator(self):
        return True

    # noinspection PyMethodMayBeStatic
    def is_connected(self):
        return self._is_connected

    def connect(self):
        self._is_connected = True

    def disconnect(self):
        self._is_connected = False

    def reconnect(self):
        self._is_connected = True


class PmxAProxy(DynamicProxy, PmxAInterface):
    def __init__(self, device_id: str):
        """Initialisation of proxy for the KIKUSUI PMX-A device with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        # super().__init__(device_id)

        hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")
        protocol = CS_SETTINGS[device_id].get("PROTOCOL", "tcp")
        commanding_port = CS_SETTINGS[device_id].get("COMMANDING_PORT", 0)
        service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "pmx_a_cs")

        # Fixed ports -> Use information from settings

        if commanding_port != 0:
            super().__init__(connect_address(protocol, hostname, commanding_port))

        # Dynamic port allocation -> Use Registry Client

        else:
            with RegistryClient() as reg:
                service = reg.discover_service(service_type)

                if service:
                    protocol = service.get("protocol", "tcp")
                    hostname = service["host"]
                    port = service["port"]

                    super().__init__(connect_address(protocol, hostname, port), timeout=PROXY_TIMEOUT)

                else:
                    raise RuntimeError(f"No service registered as {service_type}")

        self.device_id = device_id
