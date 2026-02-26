from enum import Enum
from pathlib import Path

import numpy as np

from egse.settings import Settings

HERE = Path(__file__).parent

DEVICE_SETTINGS = Settings.load("Aim-TTi TGF4000")
CMD_DELAY = DEVICE_SETTINGS["CMD_DELAY"]

PROXY_TIMEOUT = 10

CS_SETTINGS = Settings.load("Aim-TTi TGF4000 Control Server")
PROTOCOL = CS_SETTINGS.get("PROTOCOL", "tcp")  # Communication protocol


class Version(float):
    """Version float of XX.xx format."""

    def __str__(self):
        return "{0:05.2f}".format(float(self))


class ArbDataFile(str, Enum):
    """Enumeration for the files with the ARB data (for the AWG).

    The files are located in the /arbdata folder.
    """

    # Original Evoleo files to configure Clk_ccdread with short pulses of 200 ms

    N_CCD_READ_25 = ("ccdRead25.arb",)  # CCD readout for N-CAM (image cycle time: 25s)
    N_CCD_READ_31_25 = ("ccdRead31_25.arb",)  # CCD readout for N-CAM (image cycle time: 31.25s)
    N_CCD_READ_37_50 = ("ccdRead37_50.arb",)  # CCD readout for N-CAM (image cycle time: 37.50s)
    N_CCD_READ_43_75 = ("ccdRead43_75.arb",)  # CCD readout for N-CAM (image cycle time: 43.75s)
    N_CCD_READ_50 = ("ccdRead50.arb",)  # CCD readout for N-CAM (image cycle time: 50s)

    F_CCD_READ = ("FccdRead.arb",)  # CCD readout for F-CAM (fixed image cycle time)
    F_CCD_READ_MIN_POINTS = "FccdRead_min_points.arb"  # Taken from PTO-EST-SC-TN-1563 (v1.0)

    # Files modified by KUL to configure Clk_ccdread with short pulses of 150ms

    N_CCD_READ_25_150MS = ("ccdRead25_150ms.arb",)  # CCD readout for N-CAM (image cycle time: 25s)
    N_CCD_READ_31_25_150MS = ("ccdRead31_25_150ms.arb",)  # CCD readout for N-CAM (image cycle time: 31.25s)
    N_CCD_READ_37_50_150MS = ("ccdRead37_50_150ms.arb",)  # CCD readout for N-CAM (image cycle time: 37.50s)
    N_CCD_READ_43_75_150MS = ("ccdRead43_75_150ms.arb",)  # CCD readout for N-CAM (image cycle time: 43.75s)
    N_CCD_READ_50_150MS = ("ccdRead50_150ms.arb",)  # CCD readout for N-CAM (image cycle time: 50s)

    # Original Evoleo files to configure Clk_heater

    SVM_SYNC_CCD_READ_25 = ("HeaterSync_ccdRead25.arb",)  # SVM/TCS sync signal (image cycle time: 25s)
    SVM_SYNC_CCD_READ_31_25 = ("HeaterSync_ccdRead31_25.arb",)  # SVM/TCS sync signal (image cycle time: 31.25s)
    SVM_SYNC_CCD_READ_37_50 = ("HeaterSync_ccdRead37_50.arb",)  # SVM/TCS sync signal (image cycle time: 37.50s)
    SVM_SYNC_CCD_READ_43_75 = ("HeaterSync_ccdRead43_75.arb",)  # SVM/TCS sync signal (image cycle time: 43.75s)
    SVM_SYNC_CCD_READ_50 = "HeaterSync_ccdRead50.arb"  # SVM/TCS sync signal (image cycle time: 50s)

    SVM_SYNC_F_CAM = "HeaterSync_FccdRead.arb"  # SVM/TCS sync signal (fixed image cycle time)
    SVM_SYNC_F_CAM_MIN_POINTS = "Heater_FccdRead_min_points.arb"  # Taken from PTO-EST-SC-TN-1563 (v1.0)


class ArbData:
    """This code is based on the code of ARB_DATA.py, developed by EVOLEO."""

    def __init__(self):
        """Initialisation of ARB data that can be sent to or be received from the AWG."""

        self.array = []
        self.filename = None

    # def init_from_file(self, filename: ArbDataFile):
    #     """Read the ARB data from the given file.
    #
    #     This consists of the following steps:
    #
    #         - Look for the file with the given name in the /arbdata folder;
    #         - Read the data from this file;
    #         - Convert the data to an array.
    #
    #     Args:
    #         - filename: Filename as in the /arbdata folder.
    #     """
    #
    #     self.filename = get_resource(f":/aeudata/{filename}")
    #
    #     self.parse_from_file()

    def init_from_bytestring(self, bytestring: bytes):
        """Read the ARB data from the given bytestring.

        Args:
            - bytestring: Bytestring.
        """

        bytestring = bytestring.decode(encoding="latin1", errors="ignore")

        len_num_bytes = int(bytestring[1])
        data = bytestring[2 + len_num_bytes :]

        self.array_from_bytes(data)

    def parse_from_file(self):
        """Construct an array from the content of the file.

        The first line of the file indicates what the format is (currently, all files start with "HEX").
        """

        with open(self.filename, "r") as arb_data_file:
            # Check what the data format is

            header = arb_data_file.readline()
            args = header.strip().split("\t")
            data_format = args[0]

            # Data itself (which should be turned into an array)

            data = arb_data_file.read()

            if data_format == "HEX":
                self.array_from_hex_string(data)

            else:
                from egse.arbitrary_wave_generator.aim_tti.tgf4000 import Tgf4000Error
                raise Tgf4000Error("The first line in the ARB data file should be: HEX")

    def array_from_hex_string(self, hex_string):
        """Build an array from the given hex string.

        Examples:
            - hex_string: "0001 0002 0003" -> array: [1, 2, 3]
            - hex_string: "7FFF FFFF 0000 0001 8001" -> array: [32767, -1, 0, 1, -32767]
            - hex_string: "000100020003" -> array: [1, 2, 3]

        Args:
            - hex_string: Hex string to create an array from.
        """

        self.array = []

        # Strip off the blanks

        hex_string = hex_string.replace(" ", "").strip()

        # Each number is represented by 4 characters

        num_hex_numbers = len(hex_string) // 4

        # Loop over all hex numbers in the input string

        for index in range(num_hex_numbers):
            index *= 4
            hex_number = hex_string[index : index + 4]

            # print(f"Hex number: {hex_number} -> {int(np.int16(int(hex_number, 16)))}")

            # Folding
            # E.g. FFFF is folded to -1 (int returns 65535)

            self.array.append(int(np.int16(int(hex_number, 16))))

    @property
    def string(self):
        """Convert the content of the file to the ARB data as it should be sent to the AWG.

        The returned string is a concatenation of:

            - The #-symbol;
            - The number of ASCII characters that will define the length of the binary data [bytes];
            - The length of the binary data [bytes];
            - The binary data itself.

        Returns: Content of the file as the ARB data as it should be sent to the AWG.
        """

        # Convert the array to a byte string ("latin1": https://stackoverflow.com/questions/42795042)

        byte_array = self.array_as_bytes().decode(encoding="latin1", errors="ignore")

        # Number of ASCII characters that define the length of the binary data [bytes]

        num_bytes = len(byte_array)

        # Length of the binary data [bytes]

        str_num_bytes = str(num_bytes)

        # Binary data itself

        len_num_bytes = len(str_num_bytes)

        header = f"#{len_num_bytes:1d}{str_num_bytes}"

        # return header.encode() + byte_array
        return rf"#{len_num_bytes:1d}{str_num_bytes}{byte_array}"

        # return rf"#{len_num_bytes:1d}{str_num_bytes}{byte_array.hex()}"

    def array_as_bytes(self):
        """Return the current array as a byte array.

        Returns: Current array as a byte array
        """

        byte_string = bytes()

        for number in self.array:
            byte_string += number.to_bytes(length=2, byteorder="big", signed=True)

        return byte_string

    def array_from_bytes(self, data: str):
        """Parse array value from the given string.

        Args:
            - data: Data string.
        """

        num_array = []

        if isinstance(data, str):
            bytestring = data.encode(encoding="latin1")

        num_numbers = len(bytestring) // 2

        for index in range(num_numbers):
            index *= 2
            number = bytestring[index : index + 2]

            num_array.append(int.from_bytes(number, byteorder="big", signed=True))

        self.array = num_array


class Waveform(str, Enum):
    """Enumeration of the waveform types.

    Possible values are:
        - SINE: Sinusoidal waveform,
        - SQUARE: Square waveform,
        - RAMP
        - RAMP_UP/RAMPUP
        - RAMP_DOWN/RAMPDOWN
        - TRIANGULAR: Triangular waveform,
        - PULSE
        - NOISE
        - PRBSPN7
        - PRBSPN9
        - PRBSPN11
        - PRBSPN15
        - PRBSPN20
        - PRBSPN23
        - PRBSPN29
        - PRBSPN31
        - ARBITRARY/ARB: Arbitrary waveform.
    """

    SINE = "SINE"  # Sinusoidal waveform
    SQUARE = "SQUARE"  # Square waveform
    RAMP = "RAMP"
    RAMPUP = RAMP_UP = "RAMPUP"
    RAMPDOWN = RAMP_DOWN = "RAMPDOWN"
    TRIANGULAR = "TRIANG"  # Triangular waveform
    PULSE = "PULSE"
    NOISE = "NOISE"  # Gaussian white noise waveform
    PRBSPN7 = "PRBSPN7"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 7 bits)
    PRBSPN9 = "PRBSPN9"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 9 bits)
    PRBSPN11 = "PRBSPN11"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 11 bits)
    PRBSPN15 = "PRBSPN15"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 15 bits)
    PRBSPN20 = "PRBSPN20"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 20 bits)
    PRBSPN23 = "PRBSPN23"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 23 bits)
    PRBSPN29 = "PRBSPN29"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 29 bits)
    PRBSPN31 = "PRBSPN31"  # Pseudo-Random Binary Sequence (PRBS) waveform (LFSR length: 31 bits)
    ARBITRARY = ARB = "ARB"  # Arbitrary waveform


class AmplitudeRange(str, Enum):
    AUTO = "AUTO"
    HOLD = "HOLD"


class OutputWaveformType(str, Enum):
    """Enumeration of the output waveform types.

    Possible values are:

        - DC,
        - SINC,
        - HAVERSINE,
        - EXP_RISE/EXPRISE,
        - LOG_RISE/LOGRISE
        - EXP_FALL/EXPFALL,
        - LOG_FALL/LOGFALL,
        - GAUSSIAN/GAUSS,
        - LORENTZ,
        - D_LORENTZ/DLORENTZ,
        - TRIANGULAR/TRIANG/TRIANGLE,
        - ARB1,
        - ARB2,
        - ARB3,
        - ARB4.
    """

    DC = "DC"
    SINC = "SINC"
    HAVERSINE = "HAVERSINE"
    CARDIAC = "CARDIAC"
    EXP_RISE = EXPRISE = "EXPRISE"  # Exponential rise
    LOG_RISE = LOGRISE = "LOGRISE"  # Logarithmic rise
    EXP_FALL = EXPFALL = "EXPFALL"  # Exponential fall
    LOG_FALL = LOGFALL = "LOGFALL"  # Logarithmic fall
    GAUSSIAN = GAUSS = "GAUSSIAN"
    LORENTZ = "LORENTZ"
    D_LORENTZ = DLORENTZ = "DLORENTZ"
    TRIANGULAR = TRIANG = TRIANGLE = "TRIANG"
    ARB1 = "ARB1"  # Arbitrary waveform specified and stored by the user in memory under "ARB1"
    ARB2 = "ARB2"  # Arbitrary waveform specified and stored by the user in memory under "ARB2"
    ARB3 = "ARB3"  # Arbitrary waveform specified and stored by the user in memory under "ARB3"
    ARB4 = "ARB4"  # Arbitrary waveform specified and stored by the user in memory under "ARB4"


class Modulation(str, Enum):
    """Enumeration of the modulation types."""

    OFF = "OFF"
    AM = "AM"  # Amplitude Modulation
    AMSC = AM_SC = "AMSC"  # Amplitude Modulation - Suppressed Carrier
    FM = "FM"  # Frequency Modulation
    PM = "PM"  # Phase Modulation
    ASK = "ASK"  # Amplitude Shift Keying
    FSK = "FSK"  # Frequency Shift Keying
    SUM = "SUM"  # Carrier + Modulating signal
    BPSK = "BPSK"  # Binary Phase Shift Keying
    PWM = "PWM"  # Pulse Width Modulation


class Output(str, Enum):
    """Enumeration of output states:

    Possible values are:

        - ON,
        - OFF,
        - NORMAL,
        - INVERT.
    """

    ON = "ON"
    OFF = "OFF"
    NORMAL = "NORMAL"
    INVERT = "INVERT"


class SyncOutput(str, Enum):
    """Enumeration of synchronisation output states.

    Possible values are:

        - OFF,
        - ON.
    """

    OFF = "OFF"
    ON = "ON"


class SyncType(str, Enum):
    """Enumeration of synchronisation types.

    Possible values are:

        - AUTO,
        - NORMAL,
        - CARRIER,
        - TRIGGER,
        - OFF.
    """

    AUTO = "AUTO"
    NORMAL = "NORMAL"
    CARRIER = "CARRIER"
    TRIGGER = "TRIGGER"
    OFF = "OFF"


class Channel2Config(str, Enum):
    """Enumeration of configurations for channel 2.

    Possible values are:

        - MAINOUT,
        - SYNCOUT.
    """

    MAINOUT = "MAINOUT"
    SYNCOUT = "SYNCOUT"


class WaveformSource(str, Enum):
    """Enumeration of waveform sources."""

    INT = INTERNAL = "INT"
    EXT = EXTERNAL = "EXT"


class Slope(str, Enum):
    """Enumeration of slopes."""

    POS = POSITIVE = "POS"
    NEG = NEGATIVE = "NEG"


class SweepType(str, Enum):
    """Enumeration of sweep types."""

    LINUP = "LINUP"
    LINDN = "LINDN"
    LOGUP = "LOGUP"
    LOGDN = "LOGDN"


class SweepMode(str, Enum):
    CONT = CONTINUOUS = "CONT"
    TRIG = TRIGGER = "TRIG"


class TriggerSource(str, Enum):
    INT = INTERNAL = "INT"
    EXT = EXTERNAL = "EXT"
    MAN = MANUAL = "MAN"


class Sweep(str, Enum):
    """Enumeration of synchronisation sweep states.

    Possible values are:

        - OFF,
        - ON.
    """

    OFF = "OFF"
    ON = "ON"


class Burst(str, Enum):
    OFF = "OFF"
    NCYC = "NCYC"
    GATED = "GATED"
    INFINITE = "INFINITE"


class ClockSource(str, Enum):
    """Enumeration of clock sources."""

    INT = INTERNAL = "INT"
    EXT = EXTERNAL = "EXT"


class ChannelMode(str, Enum):
    """Enumeration of manual trigger operations."""

    SINGLE = "SINGLE"
    DUAL = "DUAL"


class AmplitudeCoupling(str, Enum):
    """Enumeration of amplitude coupling."""

    ON = "ON"
    OFF = "OFF"


class OutputCoupling(str, Enum):
    """Enumeration of output coupling."""

    ON = "ON"
    OFF = "OFF"


class FrequencyCoupling(str, Enum):
    """Enumeration of frequency coupling."""

    ON = "ON"
    OFF = "OFF"


class ChannelTracking(str, Enum):
    """Enumeration of channel tracking."""

    OFF = "OFF"
    EQUAL = "EQUAL"
    INVERT = "INVERT"


class BeepMode(str, Enum):
    """Enumeration of beep modes."""

    ON = "ON"
    OFF = "OFF"
    WARN = WARNING = "WARN"
    ERROR = "ERROR"


class NetworkConfig(str, Enum):
    """Enumeration of network configurations."""

    DHCP = "DHCP"
    AUTO = "AUTO"
    STATIC = "STATIC"


class FilterShape(str, Enum):
    """Enumeration of arbitrary filter shapes"""

    NORMAL = "NORMAL"
    STEP = "STEP"


class CounterSource(str, Enum):
    """Enumeration of the input counter source.

    Possible values are:

        - AC: AC-coupled (Alternating Current);
        - DC: DC-coupled (Direct Current).
    """

    AC = "AC"  # AC-coupled (Alternating Current)
    DC = "DC"  # DC-coupled (Direct Current)


class CounterType(str, Enum):
    """Enumeration of the counter type.

    Possible values are:

        - FREQUENCY: Measure the frequency of the signal;
        - PERIOD: Measure the period of the signal;
        - WIDTH: Measure the positive width of the signal;
        - NWIDTH: Measure the negative width of the signal;
        - DUTY: Measure the duty cycle of the signal.
    """

    FREQUENCY = "FREQUENCY"  # Measure the frequency of the signal
    PERIOD = "PERIOD"  # Measure the period of the signal
    WIDTH = "WIDTH"  # Measure the positive width of the signal
    NWIDTH = "NWIDTH"  # Measure the negative width of the signal
    DUTY = "DUTY"  # Measure the duty cycle of the signal
