from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent

DEVICE_SETTINGS = Settings.load("RS-PRO RS-D3000")
CS_SETTINGS = Settings.load("RS-PRO RS-D3000 Control Server")
PROTOCOL = CS_SETTINGS.get("PROTOCOL", "tcp")  # Communication protocol

PROXY_TIMEOUT = 10
