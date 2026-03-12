from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent

DEVICE_SETTINGS = Settings.load("KIKUSUI PMX")
CMD_DELAY = DEVICE_SETTINGS["CMD_DELAY"]

PROXY_TIMEOUT = 10
