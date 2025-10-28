from enum import IntEnum
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


class TcuMode(IntEnum):
    """Ariel TCU operating modes.

    The different TCU modes are:
    - IDLE: Waiting for commands, minimum power consumption,
    - BASE: HK + TSM circuitry on,
    - CALIBRATION: HK + TSM + M2MD circuitry on.
    """

    # Adopted from Vladimiro's code

    IDLE = 0x0000  # Waiting for commands, minimum power consumption
    BASE = 0x0001  # HK + TSM circuitry on
    CALIBRATION = 0x0003  # HK + TSM + M2MD circuitry on


class MotorState(IntEnum):
    """State of the M2MD motors.

    The different motor states are:
    - STANDBY: No motion,
    - OPERATION: Motor moving.
    """

    # Adopted from Vladimiro's code
    # RD01 -> Sect. 5.1

    STANDBY = 0x0001  # No motion
    OPERATION = 0x0010  # Motor moving
