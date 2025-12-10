"""General information for the Ariel Telescope Control Unit (TCU).

Reference documents:
    - RD01: TCU User Manual (ARIEL-IEEC-PL-TN-002), v1.2
    - RD02: ARIEL TCU Data Handling (ARIEL-IEEC-PL-TN-007), v1.0
    - RD02: TCU code provided by Vladimiro Noce (priv. comm.)
"""

from enum import IntEnum
from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent
settings = Settings.load("Ariel TCU Control Server")

# General information about the TCU Control Server

PROCESS_NAME = settings.get("PROCESS_NAME", "tcu_cs")  # Name under which it is registered in the service registry
SERVICE_TYPE = settings.get(
    "SERVICE_TYPE", "tcu_cs"
)  # Service type under which it is registered in the service registry
PROTOCOL = settings.get("PROTOCOL", "tcp")  # Communication protocol
HOSTNAME = settings.get("HOSTNAME", "localhost")  # Hostname
COMMANDING_PORT = settings.get("COMMANDING_PORT", 0)  # Commanding port (as per settings or dynamically assigned)
SERVICE_PORT = settings.get("SERVICE_PORT", 0)  # Service port (as per settings or dynamically assigned)
MONITORING_PORT = settings.get("MONITORING_PORT", 0)  # Monitoring port (as per settings or dynamically assigned)
STORAGE_MNEMONIC = settings.get("STORAGE_MNEMONIC", "TCU")  # Storage mnemonic (used in the HK filenames)


NUM_TSM_FRAMES = settings.get("NUM_TSM_FRAMES", 2)
NUM_TSM_PROBES_PER_FRAME = settings.get("NUM_TSM_PROBES_PER_FRAME", 22)
NUM_M2MD_POSITIONS = settings.get("NUM_M2MD_POSITIONS", 18)
NUM_M2MD_AXES = settings.get("NUM_M2MD_AXES", 3)

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


AXIS_VELOCITY = {
    1: 0x5DC0,  # Writing @ 1Hz
    2: 0x2EE0,  # Writing @ 2Hz
    4: 0x1770,  # Writing @ 4Hz
    8: 0x0BB8,  # Writing @ 8Hz
    16: 0x05DC,  # Writing @ 16Hz
    32: 0x02EE,  # Writing @ 32Hz
    64: 0x0177,  # Writing @ 64Hz
    # For testing purposes
    75: 0x0140,  # Writing @ 75Hz
    80: 0x012C,  # Writing @ 80Hz
    96: 0x00FA,  # Writing @ 96Hz
}


# To interpret the error code values
# Taken from RD02 -> Table 3

ERROR_CODES = {
    0x00: "No errors",
    0x01: "Command not executed",
    0x02: "Command error",
    0x03: "Command not allowed",
    0x04: "Destination address error",
    0x05: "Protocol ID error",
    0x06: "Source address error",
    0x07: "Unexpected sequence error",
    0x08: "Address error",
    0x09: "Data length error",
    0x0A: "CRC error",
    0x0B: "Parameter values error",
    0x0C: "Bad mode",
    0x0D: "Timeout",
    0x0E: "Unknown",
    0x0F: "Extended error, see cargo",
}
