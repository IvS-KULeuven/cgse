class LakeShore336Proxy(Proxy, Lakeshore336Interface):
class LakeShore336Interface(DeviceInterface):

    def __init__(self, device_id: str):
        """ Initialisation of a LakeShore336 interface.

        Args:
            device_id (str): Device identifier
        """

        super().__init__()

        self.device_id = device_id

class LakeShore336Controller(LakeShore336Interface):

    def __init__(self, device_id: str):
        super().__init__(device_id)

        self.lakeshore = self.transport = LakeShore336EthernetInterface(device_id)

    def is_simulator(self) -> bool:

        return False

    def is_connected(self) -> bool:

        return self.lakeshore.is_connected()

    def connect(self):

        self.lakeshore.connect()

    def disconnect(self):

        self.lakeshore.disconnect()

    def reconnect(self):

        self.lakeshore.reconnect()
    """ Proxy to connect to a LakeShore 336 Control Server """

    def __init__(self, device_id: str):
        """ Proxy to connect to the LakeShore 336 with the given device identifier

        Args:
            device_id (str): Device identifier
        """

        protocol = CTRL_SETTINGS.PROTOCOL
        hostname = CTRL_SETTINGS.HOSTNAME
        port = CTRL_SETTINGS[device_id]["COMMANDING_PORT"]      # TODO: Use port number from registry service

        super().__init__(endpoint=connect_address(protocol, hostname, port))
