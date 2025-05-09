class LakeShore336Proxy(Proxy, Lakeshore336Interface):
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
