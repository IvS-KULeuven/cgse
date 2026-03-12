from egse.digilent.measurpoint.digilent_devif import DigilentEthernetInterface
from egse.settings import Settings

DEVICE_SETTINGS = Settings.load("Digilent MEASURpoint DT8874")


class Dt8874EthernetInterface(DigilentEthernetInterface):
    def __init__(self, hostname: str = None, port: int = None):
        hostname = DEVICE_SETTINGS.HOSTNAME if hostname is None else hostname
        port = DEVICE_SETTINGS.PORT if port is None else port
        device_name = DEVICE_SETTINGS.DEVICE_NAME
        timeout = DEVICE_SETTINGS.TIMEOUT

        super().__init__(hostname, port, device_name, timeout)
