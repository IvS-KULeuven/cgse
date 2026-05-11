from egse.hexapod.symetrie import ControllerFactory
from egse.hexapod.symetrie import ProxyFactory
from egse.hexapod.symetrie import get_hexapod_controller_pars
from egse.hexapod.symetrie import logger
from egse.hexapod.symetrie.dynalpha import AlphaPlusControllerInterface
from egse.hexapod.symetrie.dynalpha import AlphaPlusTelnetInterface
from egse.mixin import DynamicCommandMixin
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address

PROXY_TIMEOUT = 10.0  # don't wait longer than 10s by default


class PunaPlusInterface(AlphaPlusControllerInterface):
    """
    Interface definition for the PunaPlusController and the PunaPlusProxy.
    """


class PunaPlusController(PunaPlusInterface, DynamicCommandMixin):
    def __init__(self, hostname: str = "127.0.0.1", port: int = 23):
        self.transport = self.device = AlphaPlusTelnetInterface(hostname, port)
        self.hostname = hostname
        self.port = port

        super().__init__()

    def get_controller_type(self):
        return "ALPHA+"

    def is_simulator(self):
        return False

    def is_connected(self):
        return self.device.is_connected()

    def connect(self):
        self.device.connect()

    def disconnect(self):
        self.device.disconnect()

    def reconnect(self):
        if self.is_connected():
            self.disconnect()
        self.connect()


class PunaPlusProxy(DynamicProxy, PunaPlusInterface):
    """
    The PunaPlusProxy class is used to connect to the control server and send commands to the
    Hexapod PUNA remotely. The device controller for that PUNA hexapod is an Alpha+ controller.

    The control server is discovered from the service registry using ``device_id`` as the
    service type key, which is the same identifier used when the control server was started.

    Args:
        device_id: identifier of the hexapod control server as registered in the service registry
        timeout: how long to wait for a response from the control server before giving up
    """

    def __init__(self, device_id: str, *, timeout: float = PROXY_TIMEOUT):
        self._device_id = device_id
        super().__init__("", timeout=timeout, connect=False)

    def connect_cs(self):
        with RegistryClient() as reg:
            service = reg.discover_service(self._device_id)

        if not service:
            raise ConnectionError(f"No control server registered as '{self._device_id}'.")

        protocol = service.get("protocol", "tcp")
        hostname = service["host"]
        port = service["port"]

        self._endpoint = connect_address(protocol, hostname, port)
        logger.info(f"PunaPlusProxy connecting to {self._device_id!r} at {self._endpoint}")

        super().connect_cs()


if __name__ == "__main__":
    from egse.hexapod.symetrie.puna import PunaProxy

    # The following imports are needed for the isinstance() to work
    from egse.hexapod.symetrie.punaplus import PunaPlusProxy
    from egse.hexapod.symetrie.punaplus import PunaPlusController

    print()

    *_, device_id, device_name, _ = get_hexapod_controller_pars()
    print(f"{device_name = }, {device_id = }")

    factory = ProxyFactory()
    proxy = factory.create(device_name, device_id="1A")
    assert isinstance(proxy, PunaProxy)

    proxy = factory.create(device_name, device_id="2B")
    assert isinstance(proxy, PunaPlusProxy)

    print(proxy.info())

    factory = ControllerFactory()

    device = factory.create("PUNA", device_id="H_2B")
    device.connect()
    assert isinstance(device, PunaPlusController)

    print(device.info())

    device = factory.create("ZONDA")
    device.connect()

    print(device.info())

    device.disconnect()
