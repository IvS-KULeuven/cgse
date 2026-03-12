from enum import IntEnum
from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent

# General information about the LabJack T7 Control Server

DEVICE_SETTINGS = Settings.load("LabJack T7")
CS_SETTINGS = Settings.load("LabJack T7 Control Server")
PROTOCOL = CS_SETTINGS.get("PROTOCOL", "tcp")  # Communication protocol

PROXY_TIMEOUT = 10