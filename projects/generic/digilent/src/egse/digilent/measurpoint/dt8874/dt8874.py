"""Digilent MEASURPOINT DT8874 commanding."""

import logging

from egse.device import DeviceInterface
from egse.digilent.digilent import DigilentInterface
from egse.digilent.measurpoint.dt8874 import COMMANDING_PORT, PROTOCOL, HOSTNAME, SERVICE_TYPE, PROXY_TIMEOUT
from egse.mixin import dynamic_command, CommandType, DynamicCommandMixin, add_lf
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address

LOGGER = logging.getLogger("egse.digilent.measurpoint.dt8874")




class Dt8874Controller(DigilentInterface, DynamicCommandMixin):
    def __init__(self):
        """Initialisation of an Ariel TCU controller."""

        super().__init__()
        self.transport = self.dt8874 = Dt8874DeviceInterface()


    # noinspection PyMethodMayBeStatic
    def is_simulator(self):
        return False

    def is_connected(self):
        """Checks whether the connection to the Digilent MEASURpoint DT8874 is open.

        Returns:
            True if the serial port to the Digilent MEASURpoint DT8874 is open; False otherwise.
        """

        return self.dt8874.is_connected()

    def connect(self):
        """Opens the connection to the Digilent MEASURpoint DT8874.

        Raises:
            Dt8874Error: When the connection could not be opened.
        """

        self.dt8874.connect()

    def disconnect(self):
        """Closes the connection to the Digilent MEASURpoint DT8874.

        Raises:
            Dt8874Error: When the connection could not be closed.
        """

        self.dt8874.disconnect()

    def reconnect(self):
        """Re-connects to the Digilent MEASURpoint DT8874."""

        self.transport.reconnect()


class Dt8874Simulator(DigilentInterface):
    def __init__(self):
        """Initialisation of a Digilent MEASURpoint DT8874 simulator."""

        super().__init__()

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


class Dt8874Proxy(DynamicProxy, DigilentInterface):
    """
    The TDt8874Proxy class is used to connect to the Digilent MEASURpoint DT8874 Control Server and send commands to
    the Digilent MEASURpoint DT8874 Hardware Controller remotely.
    """

    def __init__(self):
        """Initialisation of a Dt8874Proxy."""

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
