from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent
settings = Settings.load("Ariel TCU Control Server")

PROCESS_NAME = settings.get("PROCESS_NAME", "tcu_cs")
PROTOCOL = settings.get("PROTOCOL", "tcp")
HOSTNAME = settings.get("HOSTNAME", "localhost")
COMMANDING_PORT = settings.get("COMMANDING_PORT", 0)
SERVICE_PORT = settings.get("SERVICE_PORT", 0)
MONITORING_PORT = settings.get("MONITORING_PORT", 0)
SERVICE_TYPE = settings.get("SERVICE_TYPE", "tcu_cs")
STORAGE_MNEMONIC = settings.get("STORAGE_MNEMONIC", "TCU")

PROXY_TIMEOUT = 10
