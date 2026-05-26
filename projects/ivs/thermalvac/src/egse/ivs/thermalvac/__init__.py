from pathlib import Path
from egse.settings import Settings

HERE = Path(__file__).parent

DEVICE_SETTINGS = Settings.load("ThermalVac")
SETPOINT_TEMP_MIN = DEVICE_SETTINGS.get("SETPOINT_TEMP_MIN", None)
SETPOINT_TEMP_MAX = DEVICE_SETTINGS.get("SETPOINT_TEMP_MAX", None)

CS_SETTINGS = Settings.load("ThermalVac Control Server")
PROTOCOL = CS_SETTINGS.get("PROTOCOL", "tcp")  # Communication protocol
STORAGE_MNEMONIC = CS_SETTINGS.get("STORAGE_MNEMONIC", "TVAC")
SERVICE_TYPE = CS_SETTINGS.get("SERVICE_TYPE", "TVAC")
SERVICE_NAME = CS_SETTINGS.get("SERVICE_NAME", "TVAC")
SAMPLE_INTERVAL = CS_SETTINGS.get("SAMPLE_INTERVAL", 5.0)  # Sample interval [s]

PROXY_TIMEOUT = 10  # Timeout for proxy connections [s]


def tvac_state_to_string(state: int) -> str:
    """String representation of the TVAC state.

    Args:
        state (int): Integer representation of the TVAC state.

    Returns:
        String representation of the TVAC state.
    """

    state_dict = {
        0: "Unknown",
        1: "Idle",
        2: "Pumping fore vacuum",
        3: "Waiting for pressure to stabilize",
        4: "Pumping at high vacuum",
        5: "Starting turbo pump",
        6: "Stopping pumps",
        7: "Turbo pump decelerating",
        8: "Cooling",
        9: "Heating",
        10: "Pressure rising (too high for turbo)",
    }

    return state_dict.get(state, "Invalid state")
