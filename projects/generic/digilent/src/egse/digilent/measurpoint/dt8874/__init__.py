from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent
settings = Settings.load("Digilent MEASURpoint DT8874 Control Server")

# General information about the Digilent MEASURpoint DT8874 Control Server

PROCESS_NAME = settings.get("PROCESS_NAME", "dt8874_cs")  # Name under which it is registered in the service registry
SERVICE_TYPE = settings.get(
    "SERVICE_TYPE", "dt8874_cs"
)  # Service type under which it is registered in the service registry
PROTOCOL = settings.get("PROTOCOL", "tcp")  # Communication protocol
HOSTNAME = settings.get("HOSTNAME", "localhost")  # Hostname
COMMANDING_PORT = settings.get("COMMANDING_PORT", 0)  # Commanding port (as per settings or dynamically assigned)
SERVICE_PORT = settings.get("SERVICE_PORT", 0)  # Service port (as per settings or dynamically assigned)
MONITORING_PORT = settings.get("MONITORING_PORT", 0)  # Monitoring port (as per settings or dynamically assigned)
STORAGE_MNEMONIC = settings.get("STORAGE_MNEMONIC", "DT8874")  # Storage mnemonic (used in the HK filenames)

PROXY_TIMEOUT = 10
