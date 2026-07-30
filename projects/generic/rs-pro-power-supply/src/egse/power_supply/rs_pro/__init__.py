from enum import IntEnum
from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent

DEVICE_SETTINGS = Settings.load("RS-PRO RS-D3305P Controller")
CS_SETTINGS = Settings.load("RS-PRO RS-D3305P Control Server")
PROTOCOL = CS_SETTINGS.get("PROTOCOL", "tcp")  # Communication protocol


PROXY_TIMEOUT = 10

ENCODING = "ascii"
LINE_ENDING = "\n"
IDENTIFICATION_QUERY = "*IDN?"


class OperatingMode(IntEnum):
    """Enumeration of the operating modes supported by the RS-PRO RS-D3305P power supply."""

    INDEPENDENT = 0
    TRACKING_SERIES = 1
    TRACKING_PARALLEL = 2


def split_result_on_blanks(response: bytes) -> tuple[str, ...]:
    """Splits the given response string on blanks.

    Args:
        response (str): Response to split.

    Returns:
        Tuple of strings split on commas.
    """

    return tuple(to_string(response).split(" "))


def to_string(response: bytes) -> str:
    """Converts the given response to a string.

    Args:
        response (bytes): Response to convert.

    Returns:
        String value converted from the given response.
    """

    return response.decode(ENCODING, errors="ignore").strip("\r\n\x00 ")


def to_float(response: bytes) -> float:
    """Converts the given response string to a float.

    Args:
        response (bytes): Response to convert.

    Returns:
        Float value converted from the given response.
    """

    return float(to_string(response))


def to_int(response: bytes) -> int:
    """Converts the given response string to an integer value.

    Args:
        response (bytes): Response to convert.

    Returns:
        Integer value converted from the given response.
    """

    return int(to_string(response))


def decode_status(response: bytes) -> dict:
    """Decodes the status byte from the given response.

    The response an 8-bit number in the following format:

        - bit 0: 0 when channel 1 is operated in CC mode, 1 when channel 1 is operated in CV mode;
        - bit 1: 0 when channel 2 is operated in CC mode, 1 when channel 2 is operated in CV mode;
        - bits 2 and 3: operating mode (00: independent, 01: tracking series, 10: tracking parallel);
        - bits 4 and 5 -> not mentioned in the documentation;
        - bit 6: 0 if the output of channel 1 is off, 1 if the output of channel 1 is on;
        - bit 7: 0 if the output of channel 2 is off, 1 if the output of channel 2 is on.

    Args:
        response (bytes): Response to decode (status byte).

    Returns:
        Dictionary of decoded status bytes.  The keys in this dictionary are:

            - "ch1_mode": "CC" or "CV" (mode of channel 1);
            - "ch2_mode": "CC" or "CV" (mode of channel 2);
            - "tracking": "Independent", "Series", or "Parallel" (operating mode);
            - "ch1_on": True if the output of channel 1 is on, False otherwise;
            - "ch2_on": True if the output of channel 2 is on, False otherwise.
    """

    status_byte = response[0]

    # - bit 0: 0 when channel 1 is operated in CC mode, 1 when channel 1 is operated in CV mode;
    # - bit 1: 0 when channel 2 is operated in CC mode, 1 when channel 2 is operated in CV mode;
    # - bits 2 and 3: operating mode (00: independent, 01: tracking series, 10: tracking parallel);
    # - bits 4 and 5 -> not mentioned in the documentation;
    # - bit 6: 0 if the output of channel 1 is off, 1 if the output of channel 1 is on;
    # - bit 7: 0 if the output of channel 2 is off, 1 if the output of channel 2 is on.

    ch1_mode = "CV" if (status_byte & 0b00000001) else "CC"  # Bit 0
    ch2_mode = "CV" if (status_byte & 0b00000010) else "CC"  # Bit 1

    tracking_code = (status_byte >> 2) & 0b11  # Bits 2 & 3
    tracking = {0: "Independent", 1: "Series", 2: "Parallel"}.get(tracking_code, f"Unknown({tracking_code})")

    # Bits 4 & 5: Not mentioned in the documentation

    ch1_on = True if (status_byte & 0b01000000) else False  # Bit 6
    ch2_on = True if (status_byte & 0b0100000) else False  # Bit 7

    return {
        "ch1_mode": ch1_mode,
        "ch2_mode": ch2_mode,
        "tracking": tracking,
        "ch1_on": ch1_on,
        "ch2_on": ch2_on,
    }

