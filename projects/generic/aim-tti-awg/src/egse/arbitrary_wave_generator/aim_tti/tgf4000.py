from egse.arbitrary_wave_generator.aim_tti import (
    Version,
    Waveform,
    Output,
    CounterSource,
    CounterType,
    PROXY_TIMEOUT,
    CS_SETTINGS,
    ArbDataFile,
    ArbData,
    AmplitudeRange,
    SyncOutput,
    SyncType,
    Channel2Config,
    FilterShape,
    OutputWaveformType,
    Modulation,
    WaveformSource,
    Slope,
    SweepType,
    SweepMode,
    Sweep,
    TriggerSource,
    Burst,
    ClockSource,
    ChannelMode,
    AmplitudeCoupling,
    OutputCoupling,
    FrequencyCoupling,
    ChannelTracking,
    BeepMode,
    NetworkConfig,
)
from egse.arbitrary_wave_generator.aim_tti.tgf4000_devif import Tgf4000EthernetInterface
from egse.device import DeviceInterface
from egse.mixin import dynamic_command, add_lf, DynamicCommandMixin, CommandType
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address


class Tgf4000Error(Exception):
    """An Aim-TTi TGF4000-specific error."""

    pass


def unpack_response(response: bytes) -> None | list:
    """Unpack the comma-separated strings from the given bytestring.

    The unpacking consists of the following steps:

        - Decode the bytestring to a string;
        - Remove the terminator(s);
        - Split the coma-separated strings into a list of strings.

    Args:
        response (bytes): Bytestring representing the response from an AEU device.

    Returns:
        List of strings, returned by an Aim-TTi TGF4000 device.
    """

    if len(response) == 0:
        return None

    else:
        return response.decode(encoding="latin1", errors="ignore").replace("\r", "").replace("\n", "").split(", ")
        # return response.decode().replace("\r\n", "").split(", ")


def parse_ints(response: bytes) -> tuple | int:
    """Parse the given AEU device response to a list of integers.

    Args:
        - response: Bytestring representing the response from an AEU device.

    Returns: List of integers.
    """

    response = unpack_response(response)

    for index, item in enumerate(response):
        response[index] = int(item)

    if len(response) == 1:
        return response[0]

    else:
        return tuple(response)


def parse_floats(response: bytes) -> tuple | float:
    """Parse the given AEU device response to a list of floats.

    Args:
        - response: Bytestring representing the response from an AEU device.

    Returns: List of floats.
    """

    response = unpack_response(response)

    for index, item in enumerate(response):
        response[index] = float(item)

    if len(response) == 1:
        return response[0]

    else:
        return tuple(response)


def parse_strings(response: bytes) -> tuple | str:
    """Parse the given AEU device response to a list of floats.

    Args:
        - response: Bytestring representing the response from an AEU device.

    Returns: List of floats.
    """

    response = unpack_response(response)

    if len(response) == 1:
        return response[0]

    else:
        return tuple(response)


def parse_awg_instrument_id(response: bytes) -> tuple[str, str, str, float, float, float]:
    """Parse the given AEU device response to AWG instrument identification.

    Args:
        - response: Bytestring representing the response from an AEU device.

    Returns:
        - Manufacturer.
        - Model.
        - Serial number.
        - Revision of the main firmware (XX.xx).
        - Revision of the remote interface firmware (YY.yy).
        - Revision of the USB flash drive firmware (ZZ.zz).
    """

    response = unpack_response(response)

    versions = response[3].split("-")

    versions[0] = Version(versions[0])
    versions[1] = Version(versions[1])
    versions[2] = Version(versions[2])

    return (response[0], response[1]) + tuple(versions)


def parse_arb_data(cmd_string: str):
    """Parse the data from the given file into a string that can be used as ARB data.

    The command string is of the format: ARB[1:4] filename.  The file with the given name must be read and the content
    must be converted to a string that can be sent to the AWG with the ARB[1:4] command.

    Args:
        - cmd_string: Command string of the format: ARB[1:4] filename.
    """

    cmd, filename = cmd_string.split(" ")

    arb_data = ArbData()
    arb_data.init_from_file(filename)
    # arb_data = arb_data.string

    # logger.info(f"{cmd} {arb_data.string}")

    return f"{cmd} {arb_data.string}"


def parse_arb_def(response: bytes) -> tuple[str, str, int] | None:
    """Parse the given AEU device response to PSU error info.

    Args:
        - response: Bytestring representing the response from an AEU device.

    Returns:
        - Waveform name.
        - Waveform point interpolation state.
        - Waveform length.
    """

    if len(response) == 0:
        return None

    else:
        response = (
            response.decode(encoding="latin1", errors="ignore")
            .replace(" ", "")
            .replace("\r", "")
            .replace("\n", "")
            .split(",")
        )

        return response[0], response[1], int(response[2])


def parse_arb_data_response(response: bytes) -> str:
    """Parse the given AEU device response to ARB data.

    Args:
        - response: Bytestring representing the response from an AEU device.

    Returns: String representing the ARB data.
    """

    # TODO For some reason, the result is still returned as a bytestring, in despite of the decoding.  Not sure what
    # the problem is here.

    arb_data = ArbData()
    arb_data.init_from_bytestring(response)
    arb_data = arb_data.string

    return arb_data.decode(encoding="latin1", errors="ignore")


class Tgf4000Interface(DeviceInterface):
    """Base class for the Aim-TTi TGF4000 series."""

    def __init__(self, device_id: str):
        """Initialisation of an Aim-TTi TGF4000 interface.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__()

        self.device_id = device_id

        self.ethernet_interface = Tgf4000EthernetInterface(device_id=device_id)

    # Channel selection

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="CHN ${channel}", process_cmd_string=add_lf)
    def set_channel(self, channel: int) -> None:
        """Selects the given channel as the destination for subsequent commands.

        Args:
            channel (int): Destination channel (should be 1 or 2).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="CHN?", process_cmd_string=add_lf, process_response=parse_ints
    )
    def get_channel(self) -> int:
        """Returns the currently selected channel number.

        Returns:
            Currently selected channel number (1 or 2).
        """

        raise NotImplementedError

    # Continuous carrier wave commands

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="WAVE ${waveform_type}", process_cmd_string=add_lf)
    def set_waveform_type(self, waveform_type: Waveform) -> None:
        """Sets the output waveform type.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Args:
            waveform_type: Waveform type.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="WAVE?", process_cmd_string=add_lf, process_response=parse_ints
    )
    def get_waveform_type(self) -> Waveform:
        """Returns the output waveform type.

        Returns:
            Waveform type.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="FREQ ${frequency}", process_cmd_string=add_lf)
    def set_frequency(self, frequency: float) -> None:
        """Sets the waveform frequency.

        Args:
            frequency (float): Waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="FREQ?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_frequency(self) -> float:
        """Returns the waveform frequency.

        Returns:
            Waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PER ${period}", process_cmd_string=add_lf)
    def set_period(self, period: float) -> None:
        """Sets the waveform period.

        Args:
            period (float): Waveform period [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="PER?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_period(self) -> float:
        """Returns the waveform period.

        Returns:
            Waveform period [s].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="AMPLRNG ${amplitude_range}", process_cmd_string=add_lf)
    def set_amplitude_range(self, amplitude_range: AmplitudeRange) -> None:
        """Sets the amplitude range.

        Possible values are:

            - AmplitudeRange.AUTO or "AUTO"
            - AmplitudeRange.HOLD or "HOLD"

        Args:
            amplitude_range (AmplitudeRange): Amplitude range.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="AMPLRNG?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_amplitude_range(self) -> AmplitudeRange:
        """Returns the amplitude range.

        Returns:
            Amplitude range.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="AMPL ${amplitude}", process_cmd_string=add_lf)
    def set_amplitude(self, amplitude: float) -> None:
        """Sets the amplitude to the given value.

        Args:
            amplitude (float): Amplitude [Vpp].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="AMPL?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_amplitude(self) -> float:
        """Return the amplitude.

        Returns:
            Amplitude [Vpp].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="HILVL ${high_level}", process_cmd_string=add_lf)
    def set_amplitude_high_level(self, high_level: float) -> None:
        """Sets the amplitude high-level to the given value.

        Args:
            high_level (float): Amplitude high-level [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="HILVL?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_amplitude_high_level(self) -> float:
        """Return the amplitude high-level.

        Returns:
            Amplitude high-level [V].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="LOLVL ${low_level}", process_cmd_string=add_lf)
    def set_amplitude_low_level(self, low_level: float) -> None:
        """Sets the amplitude low-level to the given value.

        Args:
            low_level (float): Amplitude low-level [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="LOLVL?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_amplitude_low_level(self) -> float:
        """Return the amplitude low-level.

        Returns:
            Amplitude low-level [V].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="DCOFFS ${offset}", process_cmd_string=add_lf)
    def set_dc_offset(self, offset: float) -> None:
        """Sets the DC offset to the given value.

        Args:
            offset (float): DC offset [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="DCOFFS?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_dc_offset(self) -> float:
        """Returns the DC offset.

        Returns:
            DC offset [V].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OUTPUT ${output_status}", process_cmd_string=add_lf)
    def set_output_status(self, output_status: Output) -> None:
        """Sets the output.

        Possible values are:

            - Output.ON or "ON",
            - Output.OFF or "OFF",
            - Output.NORMAL or "NORMAL",
            - Output.INVERT or "INVERT".


        Args:
            output_status (Output): Output status
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="OUTPUT?", process_cmd_string=add_lf, process_response=parse_ints
    )
    def get_output_status(self) -> Output:
        """Returns the output status and type.

        Returns:
             Whether the output has been enabled (Output.ON or Output.OFF).
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ZLOAD ${load}", process_cmd_string=add_lf)
    def set_output_load(self, load: float | str) -> None:
        """Sets the output load, which the generator is to assume for amplitude and DC offset entries.


        Args:
            load (float | str): Output load, ranging from 1 to 100000 Ohm, or "OPEN"
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ZLOAD?",
        process_cmd_string=add_lf,  # , process_response=parse_floats
    )
    def get_output_load(self) -> float | str:
        """Returns the output load.

        Returns:
            Output load, ranging from 1 to 100000 Ohm, or "OPEN"
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="SQRSYMM ${duty_cycle}", process_cmd_string=add_lf)
    def set_square_waveform_symmetry(self, duty_cycle: float):
        """Sets the square waveform symmetry.

        Args:
            duty_cycle (float): Duty cycle [%] used for square waveforms.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string="SQRSYMM?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_square_waveform_symmetry(self) -> float:
        """Returns the square waveform symmetry.

        Returns:
            Square waveform symmetry, as duty cycle [%].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="RMPSYMM ${duty_cycle}", process_cmd_string=add_lf)
    def set_ramp_waveform_symmetry(self, duty_cycle: float):
        """Sets the square waveform symmetry.

        Args:
            duty_cycle (float): Duty cycle [%] used for ramp waveforms.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string="RMPSYMM?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_ramp_waveform_symmetry(self) -> float:
        """Returns the square waveform symmetry.

        Returns:
            Ramp waveform symmetry, as duty cycle [%].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="SYNCOUT ${sync_output}", process_cmd_string=add_lf)
    def set_sync_output(self, sync_output: SyncOutput):
        """Sets the synchronisation output state.

        Args:
            sync_output (SyncOutput): Synchronisation output state.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string="SYNCOUT?", process_cmd_string=add_lf, process_response=parse_strings
    )
    def get_sync_output(self) -> SyncOutput:
        """Returns the synchronisation output state.

        Returns:
            Synchronisation output state.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="SYNCTYPE ${sync_output}", process_cmd_string=add_lf)
    def set_sync_type(self, sync_type: SyncType):
        """Sets the synchronisation type.

        Args:
            sync_type (SyncType): Synchronisation type.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string="SYNCTYPE?", process_cmd_string=add_lf, process_response=parse_strings
    )
    def get_sync_type(self) -> SyncType:
        """Returns the synchronisation type.

        Returns:
            Synchronisation type.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="CHN2CONFIG ${config}", process_cmd_string=add_lf)
    def set_channel2_config(self, config: Channel2Config):
        """Sets the configuration for channel 2.

        Args:
            config (Channel2Config): Configuration for channel 2.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string="CHN2CONFIG?", process_cmd_string=add_lf, process_response=parse_strings
    )
    def get_channel2_config(self) -> Channel2Config:
        """Returns the configuration for channel 2.

        Returns:
            Configuration for channel 2.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PHASE ${phase}", process_cmd_string=add_lf)
    def set_phase(self, phase: float) -> None:
        """Sets the waveform phase offset.

        Args:
            phase (float): Waveform phase offset [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="PHASE?", process_cmd_string=add_lf, process_response=parse_floats
    )
    def get_phase(self) -> float:
        """Returns the waveform phase offset.

        Returns:
            Waveform phase offset [°].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ALIGN", process_cmd_string=add_lf)
    def align(self) -> None:
        """Sends signal to align the zero phase reference of both channels."""

        raise NotImplementedError

    # Pulse generator commands

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSFREQ ${frequency}", process_cmd_string=add_lf)
    def set_pulse_frequency(self, frequency: float) -> None:
        """Sets the pulse waveform frequency.

        Args:
            frequency (float): Pulse waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_frequency(self) -> float:
        """Returns the pulse waveform frequency.

        Returns:
            Pulse waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSPER ${period}", process_cmd_string=add_lf)
    def set_pulse_period(self, period: float) -> None:
        """Sets the pulse waveform period.

        Args:
            period (float): Pulse waveform period [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSPER?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_period(self) -> float:
        """Returns the pulse waveform period.

        Returns:
            Pulse waveform period [s].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSWID ${width}", process_cmd_string=add_lf)
    def set_pulse_period(self, width: float) -> None:
        """Sets the pulse waveform width.

        Args:
            width (float): Pulse waveform width [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSWID?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_period(self) -> float:
        """Returns the pulse waveform width.

        Returns:
            Pulse waveform width [s].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSSYMM ${symmetry}", process_cmd_string=add_lf)
    def set_pulse_symmetry(self, symmetry: float) -> None:
        """Sets the pulse waveform symmetry.

        Args:
            symmetry (float): Pulse waveform symmetry [%].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSSYMM?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_symmetry(self) -> float:
        """Returns the pulse waveform symmetry.

        Returns:
            Pulse waveform symmetry [%].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSEDGE ${edges}", process_cmd_string=add_lf)
    def set_pulse_edges(self, edges: float) -> None:
        """Sets the pulse waveform edges (positive/negative).

        Args:
            edges (float): Pulse waveform edges (positive/negative) [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSEDGE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_edges(self) -> float:
        """Returns the pulse waveform edges (positive/negative).

        Returns:
            Pulse waveform edges (positive/negative) [s].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSRISE ${rise}", process_cmd_string=add_lf)
    def set_pulse_rise(self, rise: float) -> None:
        """Sets the pulse waveform positive edge.

        Args:
            rise (float): Pulse waveform positive edge [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSRISE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_rise(self) -> float:
        """Returns the pulse waveform positive edge.

        Returns:
            Pulse waveform positive edge [s].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSFALL ${fall}", process_cmd_string=add_lf)
    def set_pulse_fall(self, fall: float) -> None:
        """Sets the pulse waveform negative edge.

        Args:
            fall (float): Pulse waveform negative edge [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSFALL?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_fall(self) -> float:
        """Returns the pulse waveform negative edge.

        Returns:
            Pulse waveform negative edge [s].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PULSDLY ${delay}", process_cmd_string=add_lf)
    def set_pulse_delay(self, delay: float) -> None:
        """Sets the pulse waveform delay.

        Args:
            delay (float): Pulse waveform delay [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PULSDLY?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pulse_delay(self) -> float:
        """Returns the pulse waveform delay.

        Returns:
            Pulse waveform delay [s].
        """

        raise NotImplementedError

    # PRBS generator commands

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="PRBSBITRATE ${bitrate}", process_cmd_string=add_lf)
    def set_prbs_bitrate(self, bitrate: float) -> None:
        """Sets the PRBS waveform bitrate.

        Args:
            bitrate (float): PRBS waveform bitrate [bits/s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="PRBSBITRATE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_prbs_bitrate(self) -> float:
        """Returns the PRBS waveform bitrate.

        Returns:
            PRBS waveform bitrate [bits/s].
        """

        raise NotImplementedError

    # Arbitrary waveform commands

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARBDCOFFS ${dc_offset}", process_cmd_string=add_lf)
    def set_arb_dc_offset(self, dc_offset: float) -> None:
        """Sets the arbitrary DC waveform offset.

        Args:
            dc_offset (float): Arbitrary DC waveform offset [V].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARBDCOFFS?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_arb_dc_offset(self) -> float:
        """Returns the arbitrary DC waveform offset.

        Returns:
            Arbitrary DC waveform offset [V].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARBFILTER ${filter_shape}", process_cmd_string=add_lf)
    def set_arb_filter(self, filter_shape: FilterShape) -> None:
        """Sets the arbitrary waveform filter shape.

        Possible values are:

            - FilterShape.NORMAL or "NORMAL",
            - FilterShape.STEP or "STEP ".

        Args:
            filter_shape (FilterShape): Arbitrary waveform filter shape.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARBFILTER?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_arb_filter(self) -> FilterShape:
        """Returns the arbitrary waveform filter shape.

        Returns:
            Arbitrary DC waveform offset [V].
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARBLOAD ${output_type}", process_cmd_string=add_lf)
    def set_arb_waveform(self, output_type: OutputWaveformType):
        """Sets the given arbitrary output waveform type.

        Possible values are:

            - OutputWaveformType.DC or "DC",
            - OutputWaveformType.SINC or "SINC",
            - OutputWaveformType.HAVERSINE or "HAVESINE",
            - OutputWaveformType.CARDIAC or "CARDIAC",
            - OutputWaveformType.EXP_RISE, OutputWaveformType.EXPRISE, or "EXPRISE",
            - OutputWaveformType.LOG_RISE, OutputWaveformType.LOGRISE, or "LOGRISE",
            - OutputWaveformType.EXP_FALL, OutputWaveformType.EXPFALL, or "EXPFALL",
            - OutputWaveformType.LOG_FALL, OutputWaveformType.LOGFALL, "LOGFALL",
            - OutputWaveformType.GAUSSIAN, OutputWaveformType.GAUSS, or "GAUSSIAN",
            - OutputWaveformType.LORENTZ or "LORENTZ",
            - OutputWaveformType.D_LORENTZ, OutputWaveformType.DLORENTZ, or "LORENTZ",
            - OutputWaveformType.TRIANGULAR, OutputWaveformType.TRIANGLE, OutputWaveformType.TRIANGLE, or "TRIANG",
            - OutputWaveformType.ARB1 or "ARB1",
            - OutputWaveformType.ARB2 or "ARB2",
            - OutputWaveformType.ARB3 or "ARB3",
            - OutputWaveformType.ARB4 or "ARB4".

        Args:
            output_type (OutputWaveformType): Arbitrary output waveform type.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="ARBLOAD?", process_cmd_string=add_lf)
    def get_arb_waveform(self) -> OutputWaveformType:
        """Returns the arbitrary output waveform type.

        Possible values are:

            - OutputWaveformType.DC or "DC",
            - OutputWaveformType.SINC or "SINC",
            - OutputWaveformType.HAVERSINE or "HAVESINE",
            - OutputWaveformType.CARDIAC or "CARDIAC",
            - OutputWaveformType.EXP_RISE, OutputWaveformType.EXPRISE, or "EXPRISE",
            - OutputWaveformType.LOG_RISE, OutputWaveformType.LOGRISE, or "LOGRISE",
            - OutputWaveformType.EXP_FALL, OutputWaveformType.EXPFALL, or "EXPFALL",
            - OutputWaveformType.LOG_FALL, OutputWaveformType.LOGFALL, "LOGFALL",
            - OutputWaveformType.GAUSSIAN, OutputWaveformType.GAUSS, or "GAUSSIAN",
            - OutputWaveformType.LORENTZ or "LORENTZ",
            - OutputWaveformType.D_LORENTZ, OutputWaveformType.DLORENTZ, or "LORENTZ",
            - OutputWaveformType.TRIANGULAR, OutputWaveformType.TRIANGLE, OutputWaveformType.TRIANGLE, or "TRIANG",
            - OutputWaveformType.ARB1 or "ARB1",
            - OutputWaveformType.ARB2 or "ARB2",
            - OutputWaveformType.ARB3 or "ARB3",
            - OutputWaveformType.ARB4 or "ARB4".

        Returns:
            Arbitrary waveform type.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string="ARBRESIZE ${output_type} ${size}", process_cmd_string=add_lf
    )
    def set_arb_size(self, output_type: OutputWaveformType, size: float) -> None:
        """Sets the size of the arbitrary waveform.

        Args:
            output_type (OutputWaveformType): Arbitrary output waveform type.
            size (float): Size of the arbitrary waveform.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARBRESIZE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_arb_size(self, output_type: OutputWaveformType) -> float:
        """Returns the size of the arbitrary waveform.

        Args:
            output_type (OutputWaveformType): Arbitrary output waveform type.

        Returns:
            Size of the arbitrary waveform.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string="ARBDEF ${arb}, ${name}, ${interpolation}", process_cmd_string=add_lf
    )
    def define_arb_waveform(self, arb: OutputWaveformType, name: str, interpolation: Output):
        """Defines an arbitrary waveform with the given name and waveform point interpolation state.

        Args:
            arb (ARB): Arbitrary waveform type (ARB1/ARB2/ARB3/ARB4).
            name (str): Name (capitalised, no numbers).
            interpolation (Output): Indicates whether to use waveform point interpolation.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB1 ${binary}", process_cmd_string=parse_arb_data)
    def load_arb1_data(self, binary: ArbDataFile) -> None:
        """Loads data to an existing arbitrary waveform memory location ARB1.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Args:
            binary (ArbDataFile): Data consisting of two bytes per point with no characters between bytes or points.
                                  The point data is sent high byte first. The data block has a header which consists of
                                  the # character followed by several ascii coded numeric characters. The first of
                                  these defines the number of ascii characters to follow and these following characters
                                  define the length of the binary data in bytes. The instrument will wait for data
                                  indefinitely If less data is sent. If more data is sent the extra is processed by the
                                  command parser which results in a command error.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB2 ${binary}", process_cmd_string=parse_arb_data)
    def load_arb2_data(self, binary: ArbDataFile) -> None:
        """Loads data to an existing arbitrary waveform memory location ARB2.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Args:
            binary (ArbDataFile): Data consisting of two bytes per point with no characters between bytes or points.
                                  The point data is sent high byte first. The data block has a header which consists of
                                  the # character followed by several ascii coded numeric characters. The first of
                                  these defines the number of ascii characters to follow and these following characters
                                  define the length of the binary data in bytes. The instrument will wait for data
                                  indefinitely If less data is sent. If more data is sent the extra is processed by the
                                  command parser which results in a command error.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB3 ${binary}", process_cmd_string=parse_arb_data)
    def load_arb3_data(self, binary: ArbDataFile) -> None:
        """Loads data to an existing arbitrary waveform memory location ARB3.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Args:
            binary (ArbDataFile): Data consisting of two bytes per point with no characters between bytes or points.
                                  The point data is sent high byte first. The data block has a header which consists of
                                  the # character followed by several ascii coded numeric characters. The first of
                                  these defines the number of ascii characters to follow and these following characters
                                  define the length of the binary data in bytes. The instrument will wait for data
                                  indefinitely If less data is sent. If more data is sent the extra is processed by the
                                  command parser which results in a command error.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB4 ${binary}", process_cmd_string=parse_arb_data)
    def load_arb4_data(self, binary: ArbDataFile) -> None:
        """Loads data to an existing arbitrary waveform memory location ARB4.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Args:
            binary (ArbDataFile): Data consisting of two bytes per point with no characters between bytes or points.
                                  The point data is sent high byte first. The data block has a header which consists of
                                  the # character followed by several ascii coded numeric characters. The first of
                                  these defines the number of ascii characters to follow and these following characters
                                  define the length of the binary data in bytes. The instrument will wait for data
                                  indefinitely If less data is sent. If more data is sent the extra is processed by the
                                  command parser which results in a command error.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB1 ${binary}")
    def load_arb1_ascii(self, binary: str) -> None:
        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB2 ${binary}")
    def load_arb2_ascii(self, binary: str) -> None:
        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB3 ${binary}")
    def load_arb3_ascii(self, binary: str) -> None:
        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ARB4 ${binary}")
    def load_arb4_ascii(self, binary: str) -> None:
        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB1DEF?",
        process_cmd_string=add_lf,
        process_response=parse_arb_def,
    )
    def get_arb1_def(self) -> tuple[str, Output, int]:
        """Returns the user-specified waveform name, waveform point interpolation state, and waveform length of ARB1.

        Returns:
            Waveform name for ARB1,
            Waveform point interpolation state for ARB1,
            Waveform length of ARB1.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB2DEF?",
        process_cmd_string=add_lf,
        process_response=parse_arb_def,
    )
    def get_arb2_def(self) -> tuple[str, Output, int]:
        """Returns the user-specified waveform name, waveform point interpolation state, and waveform length of ARB2.

        Returns:
            Waveform name for ARB2,
            Waveform point interpolation state for ARB2,
            Waveform length of ARB2.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB3DEF?",
        process_cmd_string=add_lf,
        process_response=parse_arb_def,
    )
    def get_arb3_def(self) -> tuple[str, Output, int]:
        """Returns the user-specified waveform name, waveform point interpolation state, and waveform length of ARB3.

        Returns:
            Waveform name for ARB3,
            Waveform point interpolation state for ARB3,
            Waveform length of ARB3.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB4DEF?",
        process_cmd_string=add_lf,
        process_response=parse_arb_def,
    )
    def get_arb4_def(self) -> tuple[str, Output, int]:
        """Returns the user-specified waveform name, waveform point interpolation state, and waveform length of ARB4.

        Returns:
            Waveform name for ARB4,
            Waveform point interpolation state for ARB4,
            Waveform length of ARB4.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB1?",
        process_cmd_string=add_lf,
        process_response=parse_arb_data_response,
    )
    def get_arb1(self) -> str:
        """Returns the data from the existing arbitrary waveform location ARB1.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Returns: Data consisting of two bytes per point with no characters between bytes or points. The point data is
                 sent high byte first. The data block has a header which consists of the # character followed by
                 several ascii coded numeric characters. The first of these defines the number of ascii characters to
                 follow and these following characters define the length of the binary data in bytes. The instrument
                 will wait for data indefinitely If less data is sent. If more data is sent the extra is
                 processed by the command parser which results in a command error.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB2?",
        process_cmd_string=add_lf,
        process_response=parse_arb_data_response,
    )
    def get_arb2(self) -> str:
        """Returns the data from the existing arbitrary waveform location ARB2.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Returns: Data consisting of two bytes per point with no characters between bytes or points. The point data is
                 sent high byte first. The data block has a header which consists of the # character followed by
                 several ascii coded numeric characters. The first of these defines the number of ascii characters to
                 follow and these following characters define the length of the binary data in bytes. The instrument
                 will wait for data indefinitely If less data is sent. If more data is sent the extra is
                 processed by the command parser which results in a command error.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB3?",
        process_cmd_string=add_lf,
        process_response=parse_arb_data_response,
    )
    def get_arb3(self) -> str:
        """Returns the data from the existing arbitrary waveform location ARB3.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Returns: Data consisting of two bytes per point with no characters between bytes or points. The point data is
                 sent high byte first. The data block has a header which consists of the # character followed by
                 several ascii coded numeric characters. The first of these defines the number of ascii characters to
                 follow and these following characters define the length of the binary data in bytes. The instrument
                 will wait for data indefinitely If less data is sent. If more data is sent the extra is
                 processed by the command parser which results in a command error.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ARB4?",
        process_cmd_string=add_lf,
        process_response=parse_arb_data_response,
    )
    def get_arb4(self) -> str:
        """Returns the data from the existing arbitrary waveform location ARB4.

        This command does not need the command terminator code 0x0A (Line Feed).

        The waveform memory size is 8192 points, with a vertical resolution of 16 bits.

        Returns: Data consisting of two bytes per point with no characters between bytes or points. The point data is
                 sent high byte first. The data block has a header which consists of the # character followed by
                 several ascii coded numeric characters. The first of these defines the number of ascii characters to
                 follow and these following characters define the length of the binary data in bytes. The instrument
                 will wait for data indefinitely If less data is sent. If more data is sent the extra is
                 processed by the command parser which results in a command error.
        """

        raise NotImplementedError

    # Modulation commands

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MOD ${modulation}",
        process_cmd_string=add_lf,
    )
    def set_modulation(self, modulation: Modulation) -> None:
        """Sets the modulation type.

        Possible values are:

            - Modulation.OFF or "OFF" for no modulation,
            - Modulation.AM or "AM" for Amplitude Modulation,
            - Modulation.AMSC, Modulation.AM_SC, or "AMSC"   # Amplitude Modulation - Suppressed Carrier,
            - Modulation.FM or "FM" for Frequency Modulation,
            - Modulation.PM or "PM" for Phase Modulation,
            - Modulation.ASK or "ASK" for Amplitude Shift Keying,
            - Modulation.FSK or "FSK" for Frequency Shift Keying,
            - Modulation.SUM or "SUM" for Carrier + Modulating signal,
            - Modulation.BPSK or "BPSK" for Binary Phase Shift Keying,
            - Modulation.PWM or "PWM" for Pulse Width Modulation.

        Args:
            modulation (Modulation): Modulation type.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MOD?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def set_modulation(self) -> Modulation:
        """Returns the current modulation type.

        Possible values are:

            - Modulation.OFF or "OFF" for no modulation,
            - Modulation.AM or "AM" for Amplitude Modulation,
            - Modulation.AMSC, Modulation.AM_SC, or "AMSC"   # Amplitude Modulation - Suppressed Carrier,
            - Modulation.FM or "FM" for Frequency Modulation,
            - Modulation.PM or "PM" for Phase Modulation,
            - Modulation.ASK or "ASK" for Amplitude Shift Keying,
            - Modulation.FSK or "FSK" for Frequency Shift Keying,
            - Modulation.SUM or "SUM" for Carrier + Modulating signal,
            - Modulation.BPSK or "BPSK" for Binary Phase Shift Keying,
            - Modulation.PWM or "PWM" for Pulse Width Modulation.

        Returns:
            Modulation type.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODAMSHAPE ${shape}",
        process_cmd_string=add_lf,
    )
    def set_am_waveform_shape(self, shape: Waveform) -> None:
        """Sets the waveform shape for AM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Args:
            shape (Waveform): Waveform shape.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODAMSHAPE?",
        process_cmd_string=add_lf,
    )
    def get_am_waveform_shape(self) -> Waveform:
        """Returns the waveform shape for AM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Returns:
            Waveform shape for AM modulation.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODFMSHAPE ${shape}",
        process_cmd_string=add_lf,
    )
    def set_fm_waveform_shape(self, shape: Waveform) -> None:
        """Sets the waveform shape for FM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Args:
            shape (Waveform): Waveform shape.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODFMSHAPE?",
        process_cmd_string=add_lf,
    )
    def get_fm_waveform_shape(self) -> Waveform:
        """Returns the waveform shape for FM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Returns:
            Waveform shape for FM modulation.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPMSHAPE ${shape}",
        process_cmd_string=add_lf,
    )
    def set_pm_waveform_shape(self, shape: Waveform) -> None:
        """Sets the waveform shape for PM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Args:
            shape (Waveform): Waveform shape.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPMSHAPE?",
        process_cmd_string=add_lf,
    )
    def get_pm_waveform_shape(self) -> Waveform:
        """Returns the waveform shape for PM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Returns:
            Waveform shape for PM modulation.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPWMSHAPE ${shape}",
        process_cmd_string=add_lf,
    )
    def set_pwm_waveform_shape(self, shape: Waveform) -> None:
        """Sets the waveform shape for PWM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Args:
            shape (Waveform): Waveform shape.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPWMSHAPE?",
        process_cmd_string=add_lf,
    )
    def get_pwm_waveform_shape(self) -> Waveform:
        """Returns the waveform shape for PWM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Returns:
            Waveform shape for PWM modulation.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODSUMSHAPE ${shape}",
        process_cmd_string=add_lf,
    )
    def set_sum_waveform_shape(self, shape: Waveform) -> None:
        """Sets the waveform shape for SUM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Args:
            shape (Waveform): Waveform shape.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODSUMSHAPE?",
        process_cmd_string=add_lf,
    )
    def get_sum_waveform_shape(self) -> Waveform:
        """Returns the waveform shape for SUM modulation.

        Possible values are:

            - Waveform.SINE or "SINE" for sinusoidal
            - Waveform.SQUARE or "SQUARE" for square
            - Waveform.RAMP or "RAMP" for ramp
            - Waveform.RAMPUP, Waveform.RAMP_UP, or "RAMPUP" for ramp up
            - Waveform.RAMPDOWN, Waveform.RAMP_DOWN, or "RAMPDOWN" for ramp down
            - Waveform.TRIANGULAR or "TRAING" for triangular
            - Waveform.PULSE or "PULSE" for pulse
            - Waveform.NOISE or "NOISE" for Gaussian white noise
            - Waveform.PRBSPN7 or "PRBSPN7" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 7 bits)
            - Waveform.PRBSPN9 or "PRBSPN9" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 9 bits)
            - Waveform.PRBSPN11 or "PRBSPN11" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 11 bits)
            - Waveform.PRBSPN15 or "PRBSPN15" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 15 bits)
            - Waveform.PRBSPN20 or "PRBSPN20" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 20 bits)
            - Waveform.PRBSPN23 or "PRBSPN23" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 23 bits)
            - Waveform.PRBSPN29 or "PRBSPN29" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 29 bits)
            - Waveform.PRBSPN31 or "PRBSPN31" for Pseudo-Random Binary Sequence (PRBS) (LFSR length: 31 bits)
            - Waveform.ARBITRARY/Waveform.ARB or "ARB" for arbitrary

        Returns:
            Waveform shape for PWM modulation.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODAMSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_am_source(self, source: WaveformSource):
        """Sets the AM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (WaveformSource): AM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODAMSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_am_source(self) -> WaveformSource:
        """Returns the AM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            AM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODFMSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_fm_source(self, source: WaveformSource):
        """Sets the FM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (WaveformSource): FM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODFMSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_fm_source(self) -> WaveformSource:
        """Returns the FM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            FM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPMSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_pm_source(self, source: WaveformSource):
        """Sets the PM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (WaveformSource): PM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPMSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_pm_source(self) -> WaveformSource:
        """Returns the PM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            PM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPWMSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_pwm_source(self, source: WaveformSource):
        """Sets the PWM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (WaveformSource): PWM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPWMSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_pwm_source(self) -> WaveformSource:
        """Returns the PWM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            PWM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPWMSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_sum_source(self, source: WaveformSource):
        """Sets the SUM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (WaveformSource): SUM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODSUMSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_sum_source(self) -> WaveformSource:
        """Returns the SUM waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            SUM waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODAMFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_am_frequency(self, frequency: float):
        """Sets the PWM waveform source.

        Args:
            frequency (float): AM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODAMFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_am_frequency(self) -> float:
        """Returns the AM waveform frequency.

        Returns:
            AM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODAMFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_am_frequency(self, frequency: float):
        """Sets the AM waveform frequency.

        Args:
            frequency (float): AM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODAMFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_am_frequency(self) -> float:
        """Returns the AM waveform frequency.

        Returns:
            AM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODFMFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_am_frequency(self, frequency: float):
        """Sets the FM waveform frequency.

        Args:
            frequency (float): FM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODFMFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_am_frequency(self) -> float:
        """Returns the FM waveform frequency.

        Returns:
            FM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPMFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_pm_frequency(self, frequency: float):
        """Sets the PM waveform frequency.

        Args:
            frequency (float): PM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPMFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pm_frequency(self) -> float:
        """Returns the PM waveform frequency.

        Returns:
            PM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPWMFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_pwm_frequency(self, frequency: float):
        """Sets the PWM waveform frequency.

        Args:
            frequency (float): PWM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPWMFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pwm_frequency(self) -> float:
        """Returns the PWM waveform frequency.

        Returns:
            PWM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODSUMFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_sum_frequency(self, frequency: float):
        """Sets the SUM waveform frequency.

        Args:
            frequency (float): SUM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODSUMFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sum_frequency(self) -> float:
        """Returns the SUM waveform frequency.

        Returns:
            SUM waveform frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODAMDEPTH ${depth}",
        process_cmd_string=add_lf,
    )
    def set_am_depth(self, depth: float):
        """Sets the AM waveform depth.

        Args:
            depth (float): AM waveform depth [%].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODAMDEPTH?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_am_depth(self) -> float:
        """Returns the AM waveform depth.

        Returns:
            AM waveform depth [%].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODFMDEV ${deviation}",
        process_cmd_string=add_lf,
    )
    def set_fm_deviation(self, deviation: float):
        """Sets the FM waveform deviation.

        Args:
            deviation (float): FM waveform deviation [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODFMDEV?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_fm_deviation(self) -> float:
        """Returns the FM waveform deviation.

        Returns:
            FM waveform deviation [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPMDEV ${deviation}",
        process_cmd_string=add_lf,
    )
    def set_pm_deviation(self, deviation: float):
        """Sets the PM waveform deviation.

        Args:
            deviation (float): PM waveform deviation [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPMDEV?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pm_deviation(self) -> float:
        """Returns the PM waveform deviation.

        Returns:
            PM waveform deviation [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPWMDEV ${deviation}",
        process_cmd_string=add_lf,
    )
    def set_pwm_deviation(self, deviation: float):
        """Sets the PWM waveform deviation.

        Args:
            deviation (float): PWM waveform deviation [%].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPWMDEV?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_pwm_deviation(self) -> float:
        """Returns the PWM waveform deviation.

        Returns:
            PWM waveform deviation [%].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODSUMLEVEL ${level}",
        process_cmd_string=add_lf,
    )
    def set_sum_level(self, level: float):
        """Sets the SUM waveform level.

        Args:
            level (float): SUM waveform level [%].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODSUMLEVEL?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sum_level(self) -> float:
        """Returns the SUM waveform level.

        Returns:
            SUM waveform level [%].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODFSKSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_fsk_source(self, source: WaveformSource) -> None:
        """Sets the FSK waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (WaveformSource): FSK waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODFSKSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_fsk_source(self) -> WaveformSource:
        """Returns the FSK waveform source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            FSK waveform source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODHOPFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_hop_frequency(self, frequency: float) -> None:
        """Sets the HOP frequency.

        Args:
            frequency (float): HOP frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODHOPFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_hop_frequency(self) -> float:
        """Returns the HOP frequency.

        Returns:
            HOP frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODFSKRATE ${rate}",
        process_cmd_string=add_lf,
    )
    def set_fsk_rate(self, rate: float) -> None:
        """Sets the FSK rate.

        Args:
            rate (float): FSK rate [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODFSKRATE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_fsk_rate(self) -> float:
        """Returns the FSK rate.

        Returns:
            FSK rate [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPOLFSK ${slope}",
        process_cmd_string=add_lf,
    )
    def set_fsk_slope(self, slope: Slope) -> None:
        """Sets the FSK slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Args:
            slope (Slope): FSK slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPOLFSK?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_fsk_slope(self) -> Slope:
        """Returns the FSK slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Returns:
            FSK slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODBPSKSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_bpsk_source(self, source: WaveformSource) -> None:
        """Sets the BPSK source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (Source): BPSK source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODBPSKSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_bpsk_source(self) -> WaveformSource:
        """Returns the BPSK source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            BPSK source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODBPSKPHASE ${source}",
        process_cmd_string=add_lf,
    )
    def set_bpsk_phase(self, offset: float) -> None:
        """Sets the BPSK phase offset.

        Args:
            offset (float): BPSK phase offset [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODBPSKPHASE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_bpsk_phase(self) -> float:
        """Returns the BPSK phase offset.

        Returns:
            BPSK phase offset [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODBPSKRATE ${rate}",
        process_cmd_string=add_lf,
    )
    def set_bpsk_rate(self, rate: float) -> None:
        """Sets the BPSK rate.

        Args:
            rate (float): BPSK rate [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODBPSKRATE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_bpsk_rate(self) -> float:
        """Returns the BPSK rate.

        Returns:
            BPSK rate [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPOLBPSK ${slope}",
        process_cmd_string=add_lf,
    )
    def set_bpsk_slope(self, slope: Slope) -> None:
        """Sets the BPSK slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Args:
            slope (Slope): BPSK slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPOLBPSK?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_bpsk_slope(self) -> Slope:
        """Returns the BPSK slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Returns:
            BPSK slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODASKSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_ask_source(self, source: WaveformSource) -> None:
        """Sets the ASK source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Args:
            source (Source): ASK source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODASKSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_ask_source(self) -> WaveformSource:
        """Returns the ASK source.

        Possible values are:

            - WaveformSource.INT, WaveformSource.INTERNAL, or "INT" for internal,
            - WaveformSource.EXT, WaveformSource.EXTERNAL, or "EXT" for external.

        Returns:
            ASK source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODHOPAMPL ${amplitude}",
        process_cmd_string=add_lf,
    )
    def set_hop_frequency(self, amplitude: float) -> None:
        """Sets the HOP amplitude.

        Args:
            amplitude (float): HOP amplitude [Vpp].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODHOPAMPL?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_hop_amplitude(self) -> float:
        """Returns the HOP amplitude.

        Returns:
            HOP amplitude [Vpp].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODASKRATE ${rate}",
        process_cmd_string=add_lf,
    )
    def set_ask_rate(self, rate: float) -> None:
        """Sets the ASK rate.

        Args:
            rate (float): ASK rate [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODASKRATE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_ask_rate(self) -> float:
        """Returns the ASK rate.

        Returns:
            ASK rate [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="MODPOLASK ${slope}",
        process_cmd_string=add_lf,
    )
    def set_ask_slope(self, slope: Slope) -> None:
        """Sets the ASK slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Args:
            slope (Slope): ASK slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="MODPOLASK?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_ask_slope(self) -> Slope:
        """Returns the ASK slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Returns:
            ASK slope.
        """

        raise NotImplementedError

    # Sweep commands

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPTYPE ${sweep_type}",
        process_cmd_string=add_lf,
    )
    def set_sweep_type(self, sweep_type: SweepType) -> None:
        """Sets the sweep type.

        Possible values are:

            - SweepType.LINUP or "LINUP",
            - SweepType.LINDN or "LINDN",
            - SweepType.LOGUP or "LOGUP",
            - SweepType.LOGDN or "LOGDN".

        Args:
            sweep_type (SweepType): Sweep type.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPTYPE?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_sweep_type(self) -> SweepType:
        """Returns the sweep type.

        Possible values are:

            - SweepType.LINUP or "LINUP",
            - SweepType.LINDN or "LINDN",
            - SweepType.LOGUP or "LOGUP",
            - SweepType.LOGDN or "LOGDN".

        Returns:
            Sweep type.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPMODE ${sweep_mode}",
        process_cmd_string=add_lf,
    )
    def set_sweep_mode(self, sweep_mode: SweepMode) -> None:
        """Sets the sweep mode.

        Possible values are:

            - SweepMode.CONT, SweepMode.CONTINUOUS, or "CONT",
            - SweepMode.TRIG, SweepMode.TRIGGER, or "TRIG".

        Args:
            sweep_mode (SweepType): Sweep mode.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPMODE?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_sweep_mode(self) -> SweepMode:
        """Returns the sweep mode.

        Possible values are:

            - SweepMode.CONT, SweepMode.CONTINUOUS, or "CONT",
            - SweepMode.TRIG, SweepMode.TRIGGER, or "TRIG".

        Returns:
            Sweep mode.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPTRGSRC ${trigger_source}",
        process_cmd_string=add_lf,
    )
    def set_sweep_trigger_source(self, trigger_source: SweepMode) -> None:
        """Sets the sweep trigger source.

        Possible values are:

            - SweepMode.INT, SweepMode.INTERNAL, or "INT",
            - SweepMode.EXT, SweepMode.EXTERNAL, or "EXT",
            - SweepMode.MAN, SweepMode.MANUAL, or "MAN".

        Args:
            trigger_source (SweepType): Sweep trigger source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPTRGSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_sweep_trigger_source(self) -> SweepMode:
        """Returns the sweep trigger source.

        Possible values are:

            - SweepMode.INT, SweepMode.INTERNAL, or "INT",
            - SweepMode.EXT, SweepMode.EXTERNAL, or "EXT",
            - SweepMode.MAN, SweepMode.MANUAL, or "MAN".

        Returns:
            Sweep trigger source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPTRGPER ${period}",
        process_cmd_string=add_lf,
    )
    def set_sweep_trigger_source(self, period: float) -> None:
        """Sets the sweep trigger period.

        Args:
            period (period): Sweep trigger period [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPTRGPER?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sweep_trigger_source(self) -> float:
        """Returns the sweep trigger period.

        Returns:
            Sweep trigger period [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPTRGPOL ${slope}",
        process_cmd_string=add_lf,
    )
    def set_sweep_trigger_slope(self, slope: Slope) -> None:
        """Sets the sweep trigger slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Args:
            slope (Slope): Sweep trigger slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPTRGPOL?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_sweep_trigger_slope(self) -> Slope:
        """Returns the sweep trigger slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Returns:
            Sweep trigger slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPBEGFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_sweep_start_frequency(self, frequency: float) -> None:
        """Sets the sweep start frequency.

        Args:
            frequency (float): Sweep start frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPBEGFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sweep_start_frequency(self) -> float:
        """Returns the sweep start frequency.

        Returns:
            Sweep start frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPENDFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_sweep_stop_frequency(self, frequency: float) -> None:
        """Sets the sweep stop frequency.

        Args:
            frequency (float): Sweep stop frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPENDFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sweep_stop_frequency(self) -> float:
        """Returns the sweep stop frequency.

        Returns:
            Sweep stop frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPCNTFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_sweep_center_frequency(self, frequency: float) -> None:
        """Sets the sweep centre frequency.

        Args:
            frequency (float): Sweep centre frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPCNTFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sweep_center_frequency(self) -> float:
        """Returns the sweep centre frequency.

        Returns:
            Sweep centre frequency [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPSPNFREQ ${frequency}",
        process_cmd_string=add_lf,
    )
    def set_sweep_frequency_span(self, frequency: float) -> None:
        """Sets the sweep frequency span.

        Args:
            frequency (float): Sweep frequency span [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPSPNFREQ?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sweep_frequency_span(self) -> float:
        """Returns the sweep centre frequency.

        Returns:
            Sweep frequency span [Hz].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWPTIME ${time}",
        process_cmd_string=add_lf,
    )
    def set_sweep_time(self, time: float) -> None:
        """Sets the sweep time.

        Args:
            time (float): Sweep time [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWPTIME?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sweep_time(self) -> float:
        """Returns the sweep time.

        Returns:
            Sweep time [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SWP ${switch}",
        process_cmd_string=add_lf,
    )
    def set_sweep(self, switch: Sweep) -> None:
        """Sets the sweep to ON or OFF.

        Args:
            switch (Sweep): ON or OFF.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="SWP?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_sweep(self) -> Sweep:
        """Returns the sweep.

        Returns:
            ON or OFF.
        """

        raise NotImplementedError

    # Burst commands

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BSTTRGSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_burst_trigger_source(self, source: TriggerSource) -> None:
        """Sets the burst trigger source.

        Possible values are:

            - TriggerSource.INT, TriggerSource.INTERNAL, or "INT",
            - TriggerSource.EXT, TriggerSource.EXTERNAL, or "EXT",
            - TriggerSource.MAN, TriggerSource.MANUAL, or "MAN".

        Args:
            source (TriggerSource): Burst trigger source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="BSTTRGSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_burst_trigger_source(self) -> TriggerSource:
        """Returns the burst trigger source.

        Possible values are:

            - TriggerSource.INT, TriggerSource.INTERNAL, or "INT",
            - TriggerSource.EXT, TriggerSource.EXTERNAL, or "EXT",
            - TriggerSource.MAN, TriggerSource.MANUAL, or "MAN".

        Returns:
            Burst trigger source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BSTPER ${period}",
        process_cmd_string=add_lf,
    )
    def set_burst_trigger_period(self, period: float) -> None:
        """Sets the burst trigger period.

        Args:
            period (float): Burst trigger source [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="BSTPER?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_burst_trigger_period(self) -> float:
        """Returns the burst trigger period.


        Returns:
            Burst trigger period [s].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BSTTRGPOL ${slope}",
        process_cmd_string=add_lf,
    )
    def set_burst_trigger_slope(self, slope: Slope) -> None:
        """Sets the burst trigger slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Args:
            slope (Slope): Burst trigger slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="BSTTRGPOL?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_burst_trigger_slope(self) -> Slope:
        """Returns the burst trigger slope.

        Possible values are:

            - Slope.POS, Slope.POSITIVE, or "POS" for a positive slope,
            - Slope.NEG, Slope.NEGATIVE, or "NEG" for a negative slope.

        Returns:
            Burst trigger slope.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BSTCOUNT ${count}",
        process_cmd_string=add_lf,
    )
    def set_burst_count(self, count: int) -> None:
        """Sets the burst count.
        Args:
            count (int): Burst count.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="BSTCOUNT?",
        process_cmd_string=add_lf,
        process_response=parse_ints,
    )
    def get_burst_count(self) -> int:
        """Returns the burst count.

        Returns:
            Burst count.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BSTPHASE ${phase}",
        process_cmd_string=add_lf,
    )
    def set_burst_count(self, phase: float) -> None:
        """Sets the burst phase.
        Args:
            phase (float): Burst phase [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="BSTPHASE?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_burst_count(self) -> float:
        """Returns the burst phase.

        Returns:
            Burst phase [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BST ${burst}",
        process_cmd_string=add_lf,
    )
    def set_burst(self, burst: Burst) -> None:
        """Sets the burst.

        Args:
            burst (Burst): Burst.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="BST?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_burst(self) -> Burst:
        """Returns the burst.

        Returns:
            Burst.
        """

        raise NotImplementedError

    # External counter commands

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="CNTRSWT ${counter_status}", process_cmd_string=add_lf)
    def set_counter_status(self, counter_status: Output) -> None:
        """Sets the external counter to ON or OFF.

        Args:
            counter_status (Output): ON/OFF.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CNTRSWT?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_counter_status(self) -> Output:
        """Returns the external counter status (ON/OFF).

        Returns:
            External counter status (ON/OFF).
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="CNTRCPLNG ${counter_source}", process_cmd_string=add_lf)
    def set_counter_source(self, counter_source: CounterSource):
        """Sets the counter source to AC (Alternating Current) or DC (Direct Current) coupled input.

        Args:
            counter_source (CounterSource): "AC" or CounterSource.AC for Alternating Current, "DC" or CounterSource.DC
                                            for Direct Current coupled input.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CNTRCPLNG?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_counter_source(self) -> CounterSource:
        """Returns the counter source coupled input (AC for Alternating Current, DC for Direct Current).

        Returns:
            CounterSource.AC or "AC" for Alternating Current, CounterSource.DC or "DC" for Direct Current coupled input.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="CNTRTYPE ${counter_type}", process_cmd_string=add_lf)
    def set_counter_type(self, counter_type: CounterType) -> None:
        """Sets the counter type.

        Possible values are:

            "FREQUENCY" (CounterType.FREQUENCY): measure the frequency of the signal,
            "PERIOD" (CounterType.PERIOD): measure the period of the signal,
            "WIDTH" (CounterType.WIDTH): measure the positive width of the signal,
            "NWIDTH" (CounterType.NWIDTH): measure the negative width of the signal,
            "DUTY" (CounterType.DUTY): measure the duty cycle of the signal.

        Args:
            Counter type (FREQUENCY/PERIOD/WIDTH/NWIDTH/DUTY).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CNTRTYPE?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_counter_type(self) -> CounterType:
        """Returns the counter type.

        Possible values are:

            "FREQUENCY" (CounterType.FREQUENCY): measure the frequency of the signal,
            "PERIOD" (CounterType.PERIOD): measure the period of the signal,
            "WIDTH" (CounterType.WIDTH): measure the positive width of the signal,
            "NWIDTH" (CounterType.NWIDTH): measure the negative width of the signal,
            "DUTY" (CounterType.DUTY): measure the duty cycle of the signal.

        Returns:
            Counter type (FREQUENCY/PERIOD/WIDTH/NWIDTH/DUTY).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CNTRVAL?",
        process_cmd_string=add_lf,
        process_response=parse_floats,
    )
    def get_counter_value(self) -> float:
        """Returns the currently measured count value.

        If the counter type is FREQUENCY, the returned value is expressed in Hz.  If the counter type is DUTY (duty
        cycle), the returned value is expressed in %.  Else the returned value is expressed in s.

        Returns:
            Currently measure count value.  If the counter type is FREQUENCY, the returned value is expressed in Hz.
            If the counter type is DUTY (duty cycle), the returned value is expressed in %.  Else the returned value is
            expressed in s.
        """

        raise NotImplementedError

    # Clock and miscellaneous commands

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="CLKSRC ${source}",
        process_cmd_string=add_lf,
    )
    def set_clock_source(self, source: ClockSource) -> None:
        """Sets clock source.

        Possible values are:

            - ClockSource.INT, ClockSource.INTERNAL, or "INT": internal clock,
            - ClockSource.EXT, ClockSource.EXTERNAL, or "EXT": external clock.

        Args:
            source (ClockSource): Burst phase [°].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CLKSRC?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_clock_source(self) -> ClockSource:
        """Returns the clock source.

        Returns:
            Clock source.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="CHNTRG ${trigger}",
        process_cmd_string=add_lf,
    )
    def set_manual_trigger_operation(self, trigger: ChannelMode) -> None:
        """Sets the manual trigger operation.

        Possible values are:

            - ManualTriggerOperation.SINGLE, or "SINGLE": single-channel mode,
            - ManualTriggerOperation.DUAL or "DUAL": dual-channel mode.

        Args:
            trigger (ChannelMode): Manual trigger operation.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="CHNTRG?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_manual_trigger_operation(self) -> ChannelMode:
        """Returns the manual trigger operation.

        Returns:
            Manual trigger operation.
        """

        raise NotImplementedError

    # Dual-channel function commands

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="AMPLCPLNG ${coupling}",
        process_cmd_string=add_lf,
    )
    def set_amplitude_coupling(self, coupling: AmplitudeCoupling) -> None:
        """Sets the amplitude coupling.

        Possible values are:

            - AmplitudeCoupling.ON, or "ON",
            - AmplitudeCoupling.OFF or "OFF".

        Args:
            coupling (AmplitudeCoupling): Amplitude coupling.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="AMPLCPLNG?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_amplitude_coupling(self) -> AmplitudeCoupling:
        """Returns the amplitude coupling.

        Possible values are:

            - AmplitudeCoupling.ON, or "ON",
            - AmplitudeCoupling.OFF or "OFF".

        Returns:
            Amplitude coupling.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="AMPLCPLNG ${coupling}",
        process_cmd_string=add_lf,
    )
    def set_output_coupling(self, coupling: OutputCoupling) -> None:
        """Sets the output coupling.

        Possible values are:

            - OutputCoupling.ON, or "ON",
            - OutputCoupling.OFF or "OFF".

        Args:
            coupling (OutputCoupling): Output coupling.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="AMPLCPLNG?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_output_coupling(self) -> OutputCoupling:
        """Returns the output coupling.

        Possible values are:

            - OutputCoupling.ON, or "ON",
            - OutputCoupling.OFF or "OFF".

        Returns:
            Output coupling.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="FRQCPLSWT ${coupling}",
        process_cmd_string=add_lf,
    )
    def set_frequency_coupling(self, coupling: FrequencyCoupling) -> None:
        """Sets the frequency coupling.

        Possible values are:

            - FrequencyCoupling.ON, or "ON",
            - FrequencyCoupling.OFF or "OFF".

        Args:
            coupling (OutputCoupling): Frequency coupling.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="FRQCPLSWT?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_frequency_coupling(self) -> FrequencyCoupling:
        """Returns the frequency coupling.

        Possible values are:

            - FrequencyCoupling.ON, or "ON",
            - FrequencyCoupling.OFF or "OFF".

        Returns:
            Frequency coupling.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="TRACKING ${tracking}",
        process_cmd_string=add_lf,
    )
    def set_channel_tracking(self, tracking: ChannelTracking) -> None:
        """Sets the channel tracking.

        Possible values are:

            - ChannelTracking.ON, or "ON",
            - ChannelTracking.OFF or "OFF".

        Args:
            tracking (ChannelTracking): Channel tracking.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="TRACKING?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_channel_tracking(self) -> ChannelTracking:
        """Returns the channel tracking.

        Possible values are:

            - ChannelTracking.ON, or "ON",
            - ChannelTracking.OFF or "OFF".

        Returns:
            Channel tracking
        """

        raise NotImplementedError

    # System and status commands

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="*CLS", process_cmd_string=add_lf)
    def clear_status(self) -> None:
        """Clears the status structure.

        This indirectly clears the status byte register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*ESE ${bits}",
        process_cmd_string=add_lf,
    )
    def set_std_event_status_enable_register(self, bits: int) -> None:
        """Enables specified bits in the Standard Event Status Enable register.

        The bits in the Standard Event Status Enable register are:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 0 | 1 | Operation complete |
            | 1 | 2 | Not used |
            | 2 | 4 | Query error |
            | 3 | 8 | Not used |
            | 4 | 16 | Execution error |
            | 5 | 32 | Command error |
            | 6 | 64 | User request (not used) |
            | 7 | 128 | Power on |

        Args:
            bits (int): Integer value expressed in base 2 (binary) that represents the weighted bit value of the
                        Standard Event Status Enable register and the binary-weighted decimal value for each bit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*ESE?",
        process_cmd_string=add_lf,
        process_response=parse_ints,
    )
    def get_std_event_status_enable_register(self) -> int:
        """Returns the current value of the Standard Event Status Enable register.

        The bits in the Standard Event Status Enable register are:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 0 | 1 | Operation complete |
            | 1 | 2 | Not used |
            | 2 | 4 | Query error |
            | 3 | 8 | Not used |
            | 4 | 16 | Execution error |
            | 5 | 32 | Command error |
            | 6 | 64 | User request (not used) |
            | 7 | 128 | Power on |

        Returns:
            Integer value expressed in base 2 (binary) that represents the weighted bit value of the Standard Event
            Status Enable register and the binary-weighted decimal value for each bit.  Values range from 0 to 255.

        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*ESR?",
        process_cmd_string=add_lf,
        process_response=parse_ints,
    )
    def get_std_event_status_register(self) -> int:
        """Returns the current value of the Standard Event Status register.

        Returns:
            Integer value expressed in base 2 (binary) that represents the weighted bit value of the Standard Event
            Status register and the binary-weighted decimal value for each bit.  Values range from 0 to 255.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="*IST?", process_cmd_string=add_lf, process_response=parse_ints
    )
    def get_ist_local_message(self):
        """Returns the IST local message as defined by IEEE Std. 488.2.

        Returns:
            IST local message: 0 if the local message is False, 1 if the local message is True.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*OPC ${bits}",
        process_cmd_string=add_lf,
    )
    def set_opc_bit(self, bit: int) -> None:
        """Sets the Operation Complete bit in the Standard Event Status Enable register.

        This will happen immediately the command is executed because of the sequential nature of all operations.

        Args:
            bit (int): Operation Complete bit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*OPC?",
        process_cmd_string=add_lf,
        process_response=parse_ints,
    )
    def get_opc_bit(self) -> int:
        """Returns the Operation Complete bit in the Standard Event Status Enable register.

        Returns:
            Operation Complete bit in the Standard Event Status Enable register..
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*PRE ${bits}",
        process_cmd_string=add_lf,
    )
    def set_pre_register(self, bit: int) -> None:
        """Sets the Parallel Poll Enable Register.

        Args:
            bit (int): Parallel Poll Enable Register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*PRE?",
        process_cmd_string=add_lf,
        process_response=parse_ints,
    )
    def get_pre_register(self) -> int:
        """Returns the Parallel Poll Enable Register.

        Returns:
            Parallel Poll Enable Register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*SRE ${bit}",
        process_cmd_string=add_lf,
    )
    def set_sre_register(self, bit: int) -> None:
        """Sets the Service Request Enable Register.

        Args:
            bit (int): Service Request Enable Register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*SRE?",
        process_cmd_string=add_lf,
        process_response=parse_ints,
    )
    def get_sre_register(self) -> int:
        """Returns the Service Request Enable Register.

        Returns:
            Service Request Enable Register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*WAI",
        process_cmd_string=add_lf,
    )
    def wait(self) -> None:
        """Waits for the instrument to complete the current operation.

        As all commands are completely executed before the next is started this command takes no additional action.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*STB?",
        process_cmd_string=add_lf,
        process_response=parse_ints,
    )
    def get_status_byte_register(self) -> int:
        """Returns the current value of the Status Byte register.

        The weighted sum of the bit values of the Status Byte register is returned, ranging from 0 to 255.  The
        following bits, described in 1999 SCPI Syntax & Stype, Sect. 9, are supported:

            | Bit | Binary weight | Description |
            | --- | --- | --- |
            | 7 | 128 | Not used |
            | 6 | 64 | Requesting Service Message (RQS) / Master Status Summary (MSS) |
            | 5 | 32 | Event Status Bit Summary (ESB) |
            | 4 | 16 | Message Available Queue Summary (MAV) |

        Returns:
            Weighted sum of the bit values of the Status Byte register, ranging from 0 to 255.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*TST?",
        process_cmd_string=add_lf,
    )
    def selftest(self):
        """The PSU has no self-test capability.

        Returns:
            Always returns 0.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="EER?", process_cmd_string=add_lf, process_response=parse_ints
    )
    def execution_error_register(self) -> int:
        """Queries and clears the execution error register.

        This register contains a number representing the last error encountered over the current interface.

        Returns:
            Execution error register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION, cmd_string="QER?", process_cmd_string=add_lf, process_response=parse_ints
    )
    def query_error_register(self) -> int:
        """Query and clear the query error register.

        Returns:
            Query error register.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*LRN?",
        process_cmd_string=add_lf,
        process_response=unpack_response,
    )
    def get_setup(self) -> bytes:
        """Returns the complete setup of the instrument as a binary data block.

        To re-install the setup the block should be returned to the instrument exactly as it is received. The syntax of
        the response is LRN <BIN>. The settings in the instrument are not affected by execution of the *LRN? command.

        Returns:
            Complete setup of the instrument as a binary data block.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="LRN",
        process_cmd_string=add_lf,
    )
    def install_data(self):
        """Installs data from a previous *LRN? command"""

        # TODO Should this be *LRN instead of LRN?

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="*RST", process_cmd_string=add_lf)
    def reset(self) -> None:
        """Resets the instrument to the remote operation default settings."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*RCL",
        process_cmd_string=add_lf,
        process_response=unpack_response,
    )
    def recall(self) -> bytes:
        """Re-cals a previously stored instrument setup file from the specified non-volatile memory location.

        Returns:
            Previously stored instrument setup file from the specified non-volatile memory location.
        """

        # TODO Input argument?

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*SAV",
        process_cmd_string=add_lf,
    )
    def save(self) -> None:
        """Saves the complete instrument setup file to the specified non-volatile memory location"""

        # TODO Input argument?

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*TRG",
        process_cmd_string=add_lf,
    )
    def trigger(self):
        """This command is the same as pressing the TRIGGER key.

        Its effect will depend on the context in which it is asserted. If the trigger source is manual and the
        generator is set to perform triggered burst or triggered sweep operation, this command sends a trigger pulse to
        the generator. If the trigger source is manual and the generator is set to perform gated burst operation, this
        command simply inverts the level of the manual trigger to high or low.
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*IDN?",
        process_cmd_string=add_lf,
        process_response=parse_awg_instrument_id,
    )
    def get_id(self) -> tuple[str, str, str, float, float, float]:
        """Returns the instrument identification.

        Returns:
            Manufacturer,
            Model,
            Serial number,
            Revision of the main firmware (XX.xx),
            Revision of the remote interface firmware (YY.yy),
            Revision of the USB flash drive firmware (ZZ.zz).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BEEPMODE ${beep_mode}",
        process_cmd_string=add_lf,
    )
    def set_beep_mode(self, beep_mode: BeepMode):
        """Sets the beep mode.

        Possible values are:
            - BeepMode.ON or "ON",
            - BeepMode.OFF or "OFF".
            - BeepMode.WARN, BeepMode.WARNING, or "WARN".
            - BeepMode.ERROR or "ERROR".

        Args:
            beep_mode (BeepMode): Beep mode.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="BEEPMODE?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_beep_mode(self) -> BeepMode:
        """Returns the beep mode.

        Possible values are:
            - BeepMode.ON or "ON",
            - BeepMode.OFF or "OFF".
            - BeepMode.WARN, BeepMode.WARNING, or "WARN".
            - BeepMode.ERROR or "ERROR".

        Returns:
            Beep mode.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BEEP",
        process_cmd_string=add_lf,
    )
    def beep(self) -> None:
        """Sounds one beep."""

        raise NotImplementedError

    # I/F management commands

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="LOCAL",
        process_cmd_string=add_lf,
    )
    def go_local(self) -> None:
        """Puts the instrument in local mode.

        This does not release any active interface lock so that the lock remains with the selected interface when the
        next remote command is received.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ADDRESS?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_address(self) -> str:
        """Returns the bus address of the instrument.

        This address is used by GPIB, if fitted, or may be used as a general identifier over the other interfaces.

        Returns:
            Bus address of the instrument.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="IPADDR ${ip_address}",
        process_cmd_string=add_lf,
    )
    def set_ip_address(self, ip_address: str):
        """Sets the present IP address of the LAN interface, provided it is connected.

        Args:
            ip_address (str): Static IP address of the LAN interface
            Present IP address of the LAN interface, provided it is connected.  The parameter must be strictly a dotted
            quad for the IP address, with each address part an <NR1> in the range 0 to 255, (e.g. 192.168.1.101).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="IPADDR?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_ip_address(self):
        """Returns the present IP address of the LAN interface, provided it is connected.

        Returns:
            Present IP address of the LAN interface, provided it is connected.  If it is not connected, the response
            will be the static IP if configured to always use that static IP, otherwise it will be 0.0.0.0 if waiting
            for DHCP or Auto-IP. The response is nnn.nnn.nnn.nnn<RMT>, where each nnn is 0 to 255.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="NETMASK ${netmask}",
        process_cmd_string=add_lf,
    )
    def set_netmask(self, netmask: str):
        """Sets network netmask of the LAN interface, provided it is connected.

        Returns:
            Present network netmask of the LAN interface, provided it is connected. The parameter must be strictly a
            dotted quad for the netmask, with each part an <NR1> in the range 0 to 255, (e.g. 255.255.255.0).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="NETMASK?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_netmask(self):
        """Returns the present network netmask of the LAN interface, provided it is connected.

        Returns:
            Present network netmask of the LAN interface, provided it is connected.  The response is
            nnn.nnn.nnn.nnn<RMT>, where each nnn is 0 to 255.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="NETCONFIG ${config}",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_network_config(self, config: NetworkConfig) -> None:
        """Sets the first means by which an IP address will be sought.

        Possible values are:
            - NetworkConfig.DHCP or "DHCP",
            - NetworkConfig.AUTO or "AUTO",
            - NetworkConfig.STATIC or "STATIC".

        Args:
            config (NetworkConfig): First means by which an IP address will be sought.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="NETCONFIG?",
        process_cmd_string=add_lf,
        process_response=parse_strings,
    )
    def get_network_config(self) -> NetworkConfig:
        """Returns the first means by which an IP address will be sought.

        Possible values are:
            - NetworkConfig.DHCP or "DHCP",
            - NetworkConfig.AUTO or "AUTO",
            - NetworkConfig.STATIC or "STATIC".

        Returns:
            First means by which an IP address will be sought.
        """

        raise NotImplementedError


class Tgf4000Controller(Tgf4000Interface, DynamicCommandMixin):
    """AWG device controller interface."""

    def __init__(self, device_id: str):
        """Initialisation of an Aim-TTi TGF4000 arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

        self.transport = self.tgf4000 = Tgf4000EthernetInterface(device_id=device_id)

        # self.transport = Tgf4000DeviceController(self.device_name, AEU_SETTINGS.HOSTNAME,
        #                                      AEU_SETTINGS[self.device_name + "_PORT"])
        # self.killer = SignalCatcher()

    # def add_observer(self, observer: DeviceConnectionObserver):
    #     # forward the observer to the generic AEUDeviceController class, i.e. self.transport
    #     # notification of state changes will be done by this transport class.
    #     self.transport.add_observer(observer)

    # noinspection PyMethodMayBeStatic
    def is_simulator(self) -> bool:
        return False

    def is_connected(self) -> bool:
        """Checks whether the connection to the Aim-TTI TGF4000 is open.

        Returns:
            True if the connection to the Aim-TTI TGF4000 is open; False otherwise.
        """

        return self.transport.is_connected()

    def connect(self):
        """Opens the connection to the Aim-TTI TGF4000.

        Raises:
            Tgf4000Error: When the connection could not be opened.
        """

        self.transport.connect()

    def disconnect(self):
        """Closes the connection to the Aim-TTi TGF4000.

        Raises:
            Tgf4000Error: When the connection could not be closed.
        """

        self.transport.disconnect()

    def reconnect(self):
        """Re-connects to the Aim-TTi TGF4000."""

        self.transport.reconnect()


class Tgf4000Simulator(Tgf4000Interface):
    def __init__(self, device_id: str):
        """Initalisation of a simulator for the Aim-TTi TGF4000 arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

        self._is_connected = True
        self.channel = -1

        self.waveform_type = [None, None]
        self.output_load = [None, None]
        self.amplitude = [None, None]
        self.dc_offset = [None, None]
        self.duty_cycle = [None, None]
        self.frequency = [None, None]
        self.output_status = [Output.OFF, Output.OFF]
        self.arb = [None, None]

        # self.arbs = {
        #     ARB.ARB1: ["A", Output.OFF, 0],
        #     ARB.ARB2: ["B", Output.OFF, 0],
        #     ARB.ARB3: ["C", Output.OFF, 0],
        #     ARB.ARB4: ["D", Output.OFF, 0],
        # }

        self.arb1 = None
        self.arb2 = None
        self.arb3 = None
        self.arb4 = None

        self.counter_status = [Output.OFF, Output.OFF]
        self.counter_source = [CounterSource.AC, CounterSource.AC]
        self.counter_type = [CounterType.FREQUENCY, CounterType.FREQUENCY]

    def reset(self) -> None:
        pass

    def set_channel(self, channel: int) -> None:
        self.channel = channel

    def get_channel(self) -> int:
        return self.channel

    def set_waveform_type(self, waveform_type: Waveform) -> None:
        self.waveform_type[self.get_channel() - 1] = waveform_type

    def get_waveform_type(self) -> Waveform:
        return self.waveform_type[self.get_channel() - 1]

    def set_output_load(self, load: float) -> None:
        self.output_load = load

    def get_output_load(self) -> float:
        return self.output_load[self.get_channel() - 1]

    def set_amplitude(self, amplitude: float) -> None:
        self.amplitude[self.get_channel() - 1] = amplitude

    def get_amplitude(self) -> float:
        return self.amplitude[self.get_channel() - 1]

    def set_dc_offset(self, offset: float) -> None:
        self.dc_offset[self.get_channel() - 1] = offset

    def get_dc_offset(self) -> float:
        return self.dc_offset[self.get_channel() - 1]

    def set_duty_cycle(self, duty_cycle: float):
        self.duty_cycle[self.get_channel() - 1] = duty_cycle

    def get_duty_cycle(self) -> float:
        return self.duty_cycle[self.get_channel() - 1]

    def set_frequency(self, frequency: float):
        self.frequency[self.get_channel() - 1] = frequency

    def get_frequency(self) -> float:
        return self.frequency[self.get_channel() - 1]

    def set_output_status(self, output_status: Output) -> None:
        self.output_status[self.get_channel() - 1] = output_status

    def get_output_status(self) -> Output:
        return self.output_status[self.get_channel() - 1]

    # def set_arb_waveform(self, arb: ARB):
    #     self.arb[self.get_channel() - 1] = arb
    #
    # def get_arb_waveform(self) -> ARB:
    #     return self.arb[self.get_channel() - 1]
    #
    # def define_arb_waveform(self, arb: ARB, name: str, interpolation: Output):
    #     self.arbs[arb][0] = name
    #     self.arbs[arb][1] = interpolation

    #
    # def load_arb1_data(self, binary: ArbDataFile) -> None:
    #
    #     arb_data = ArbData()
    #     arb_data.init_from_file(binary)
    #     arb_data = arb_data.string
    #
    #     self.arbs[ARB.ARB1][2] = (len(arb_data) - 2 - int(arb_data[1])) / 2
    #     self.arb1 = arb_data
    #
    # def load_arb2_data(self, binary: ArbDataFile) -> None:
    #
    #     arb_data = ArbData()
    #     arb_data.init_from_file(binary)
    #     arb_data = arb_data.string
    #
    #     self.arbs[ARB.ARB2][2] = (len(arb_data) - 2 - int(arb_data[1])) / 2
    #     self.arb2 = arb_data
    #
    # def load_arb3_data(self, binary: ArbDataFile) -> None:
    #
    #     arb_data = ArbData()
    #     arb_data.init_from_file(binary)
    #     arb_data = arb_data.string
    #
    #     self.arbs[ARB.ARB3][2] = (len(arb_data) - 2 - int(arb_data[1])) / 2
    #     self.arb3 = arb_data
    #
    # def load_arb4_data(self, binary: ArbDataFile) -> None:
    #
    #     arb_data = ArbData()
    #     arb_data.init_from_file(binary)
    #     arb_data = arb_data.string
    #
    #     self.arbs[ARB.ARB4][2] = (len(arb_data) - 2 - int(arb_data[1])) / 2
    #     self.arb4 = arb_data
    #
    # def load_arb1_ascii(self, binary: str) -> None:
    #
    #     self.arb1 = binary
    #
    # def load_arb2_ascii(self, binary: str) -> None:
    #
    #     self.arb1 = binary
    #
    # def load_arb3_ascii(self, binary: str) -> None:
    #
    #     self.arb1 = binary
    #
    # def load_arb4_ascii(self, binary: str) -> None:
    #
    #     self.arb1 = binary

    # def get_arb1_def(self) -> (str, Output, int):
    #     return self.arbs[ARB.ARB1][0], self.arbs[ARB.ARB1][1], self.arbs[ARB.ARB1][2]
    #
    # def get_arb2_def(self) -> (str, Output, int):
    #     return self.arbs[ARB.ARB2][0], self.arbs[ARB.ARB2][1], self.arbs[ARB.ARB2][2]
    #
    # def get_arb3_def(self) -> (str, Output, int):
    #     return self.arbs[ARB.ARB3][0], self.arbs[ARB.ARB3][1], self.arbs[ARB.ARB3][2]
    #
    # def get_arb4_def(self) -> (str, Output, int):
    #     return self.arbs[ARB.ARB4][0], self.arbs[ARB.ARB4][1], self.arbs[ARB.ARB4][2]

    def get_arb1(self) -> str:
        return self.arb1

    def get_arb2(self) -> str:
        return self.arb2

    def get_arb3(self) -> str:
        return self.arb3

    def get_arb4(self) -> str:
        return self.arb4

    def clear_status(self) -> None:
        pass

    def execution_error_register(self) -> int:
        return 0

    def query_error_register(self) -> int:
        return 0

    def get_id(self) -> (str, str, str, float, float, float):
        return "THURLBY THANDAR", "TGF4162", "527758", 01.00, 02.10, 01.20

    def set_counter_status(self, counter_status: Output) -> None:
        self.counter_status[self.get_channel() - 1] = counter_status

    def get_counter_status(self) -> Output:
        return self.counter_status[self.get_channel() - 1]

    def set_counter_source(self, counter_source: CounterSource):
        self.counter_source[self.get_channel() - 1] = counter_source

    def get_counter_source(self) -> CounterSource:
        return self.counter_source[self.get_channel() - 1]

    def set_counter_type(self, counter_type: CounterType) -> None:
        self.counter_type[self.get_channel() - 1] = counter_type

    def get_counter_type(self) -> CounterType:
        return self.counter_type[self.get_channel() - 1]

    def get_counter_value(self) -> float:
        return 1

    def align(self) -> None:
        pass

    def connect(self):
        self._is_connected = True

    def disconnect(self):
        self._is_connected = False

    def reconnect(self):
        self._is_connected = True

    def is_connected(self) -> bool:
        return self._is_connected

    def is_simulator(self) -> bool:
        return True


class Tgf4000Proxy(DynamicProxy, Tgf4000Interface):
    def __init__(self, device_id: str):
        """Initialisation of a proxy for the Aim-TTi TGF4000 arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        # super().__init__(device_id)

        hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")
        protocol = CS_SETTINGS[device_id].get("PROTOCOL", "tcp")
        commanding_port = CS_SETTINGS[device_id].get("COMMANDING_PORT", 0)
        service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "pmx_a_cs")

        # Fixed ports -> Use information from settings

        if commanding_port != 0:
            super().__init__(connect_address(protocol, hostname, commanding_port))

        # Dynamic port allocation -> Use Registry Client

        else:
            with RegistryClient() as reg:
                service = reg.discover_service(service_type)

                if service:
                    protocol = service.get("protocol", "tcp")
                    hostname = service["host"]
                    port = service["port"]

                    super().__init__(connect_address(protocol, hostname, port), timeout=PROXY_TIMEOUT)

                else:
                    raise RuntimeError(f"No service registered as {service_type}")

        self.device_id = device_id
