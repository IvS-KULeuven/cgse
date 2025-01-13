from egse.hexapod.symetrie import ControllerFactory
from egse.hexapod.symetrie import ProxyFactory
from egse.hexapod.symetrie import get_hexapod_controller_pars
from egse.hexapod.symetrie.dynalpha import AlphaPlusControllerInterface
from egse.hexapod.symetrie.dynalpha import AlphaPlusTelnetInterface
from egse.mixin import DynamicCommandMixin
from egse.proxy import DynamicProxy
from egse.settings import Settings
from egse.zmq_ser import connect_address

CTRL_SETTINGS = Settings.load("Hexapod PUNA Control Server")


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
    Hexapod PUNA remotely. The devce controller for that PUNA hexapod is an Alpha+ controller.
    """

    def __init__(
        self,
        protocol=CTRL_SETTINGS.PROTOCOL,
        hostname=CTRL_SETTINGS.HOSTNAME,
        port=CTRL_SETTINGS.COMMANDING_PORT,
    ):
        """
        Args:
            protocol: the transport protocol [default is taken from settings file]
            hostname: location of the control server (IP address) [default is taken from settings
            file]
            port: TCP port on which the control server is listening for commands [default is
            taken from settings file]
        """
        super().__init__(connect_address(protocol, hostname, port))


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
