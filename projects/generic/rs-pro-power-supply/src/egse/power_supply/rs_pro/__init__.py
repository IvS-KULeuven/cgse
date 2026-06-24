from enum import IntEnum
from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent

DEVICE_SETTINGS = Settings.load("RS-PRO RS-D3305P")
CS_SETTINGS = Settings.load("RS-PRO RS-D3305P Control Server")
PROTOCOL = CS_SETTINGS.get("PROTOCOL", "tcp")  # Communication protocol

PROXY_TIMEOUT = 10

class OperatingMode(IntEnum):

    INDEPENDENT = 0
    TRACKING_SERIES = 1
    TRACKING_PARALLEL = 2