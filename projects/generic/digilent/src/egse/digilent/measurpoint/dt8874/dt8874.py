"""Digilent MEASURPOINT DT8874 commanding."""

import logging

from egse.digilent.digilent import DigilentController, DigilentInterface
from egse.digilent.measurpoint.dt8874 import COMMANDING_PORT, PROTOCOL, HOSTNAME, SERVICE_TYPE, PROXY_TIMEOUT
from egse.digilent.measurpoint.dt8874.dt8874_devif import Dt8874EthernetInterface
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address

LOGGER = logging.getLogger("egse.digilent.measurpoint.dt8874")


class Dt8874Interface(DigilentInterface):
    """Base class for Digilent MEASURpoint DT8874 instruments."""


class Dt8874Controller(DigilentController, Dt8874Interface):
    def __init__(self):
        """Initialisation of an Ariel TCU controller."""

        super().__init__()

        self.transport = self.dt8874 = Dt8874EthernetInterface()


class Dt8874Simulator(Dt8874Interface):
    def __init__(self):
        """Initialisation of a Digilent MEASURpoint DT8874 simulator."""

        super().__init__()

        self._is_pwd_protected_cmds_enabled = True

    def enable_pwd_protected_cmds(self, password: str):
        self._is_pwd_protected_cmds_enabled = True

    def disable_pwd_protected_cmds(self, password: str):
        self._is_pwd_protected_cmds_enabled = False


class Dt8874Proxy(DynamicProxy, Dt8874Interface):
    """
    The Dt8874Proxy class is used to connect to the Digilent MEASURpoint DT8874 Control Server and send commands to
    the Digilent MEASURpoint DT8874 Hardware Controller remotely.
    """

    def __init__(self):
        """Initialisation of a Digilent MEASURpoint DT8874 proxy."""

        # Fixed ports -> Use information from settings

        if COMMANDING_PORT != 0:
            super().__init__(connect_address(PROTOCOL, HOSTNAME, COMMANDING_PORT))

        # Dynamic port allocation -> Use Registry Client

        else:
            with RegistryClient() as reg:
                service = reg.discover_service(SERVICE_TYPE)

                if service:
                    protocol = service.get("protocol", "tcp")
                    hostname = service["host"]
                    port = service["port"]

                    super().__init__(connect_address(protocol, hostname, port), timeout=PROXY_TIMEOUT)

                else:
                    raise RuntimeError(f"No service registered as {SERVICE_TYPE}")
