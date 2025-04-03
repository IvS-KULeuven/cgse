import logging
import re
from pathlib import Path
from typing import Dict, Union
from typing import List
from typing import Tuple

from egse.decorators import dynamic_interface
from egse.device import DeviceConnectionState
from egse.device import DeviceInterface
from egse.mixin import DynamicCommandMixin, CommandType
from egse.mixin import add_lf
from egse.mixin import dynamic_command
from egse.proxy import Proxy
from egse.settings import Settings
from egse.tempcontrol.keithley.daq6510_dev import DAQ6510EthernetInterface
from egse.zmq_ser import connect_address

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent

CTRL_SETTINGS = Settings.load("Keithley Control Server")
FW_SETTINGS = Settings.load("Keithley DAQ6510")
DEVICE_SETTINGS = Settings.load(location=HERE, filename="daq6510.yaml")


DEFAULT_BUFFER_1 = "defbuffer1"
DEFAULT_BUFFER_2 = "defbuffer2"


class DAQ6510Interface(DeviceInterface):
    """
    Interface definition for the Keithley DAQ6510 Controller, Proxy, and Simulator.
    """

    @dynamic_interface
    def send_command(self, command: str, response: bool) -> Union[None, str]:
        """Sends the given SCPI command to the device.

        The valid commands are described in the DAQ6510 Reference Manual [DAQ6510-901-01 Rev. B / September 2019].

        Args:
            command (str): SCPI command as specified in the DAQ6510 Reference Manual
            response (bool): Indicates whether you expect a reply from the device

        Returns: Response from the DAQ6510 is returned when a response was expected. When `response` is False, None
                 will be returned.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*IDN?",
        process_cmd_string=add_lf,
    )
    def info(self) -> str:
        """Returns basic information about the device, its name, firmware version, etc.

        The string returned is subject to change without notice and can not be used for parsing information.

        Returns: Identification string of the instrument.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="*RST",
        process_cmd_string=add_lf,
    )
    def reset(self) -> None:
        """Resets the DAQ6510.

        This returns the instrument to default settings, and cancels all pending commands.

        Note:
            The `reset()` method also deletes all the user-defined buffers. The two default buffers are cleared.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE, cmd_string=":SYST:TIME ${year}, ${month}, ${day}, ${hour}, ${minute}, ${second}"
    )
    def set_time(self, year: int, month: int, day: int, hour: int, minute: int, second: int) -> None:
        """Sets the absolute date and time for the device.

        Args:
            year (int): Year
            month (int): Month
            day (int): Day
            hour (int): Hour
            minute (int): Minute
            second (int): Second
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string=":SYST:TIME? 1")
    def get_time(self) -> str:
        """Gets the date and time from the device in UTC.

        The returned string is of the format:

            <weekday> <month> <day> <hour>:<minute>:<second> <year>

        Returns: Data and time from the device in UTC.
        """

        raise NotImplementedError

    @dynamic_interface
    def read_buffer(self, start: int, end: int, buffer_name: str, elements: List[str]):
        """Reads specific data elements (measurements) from the given buffer.

        Args:
            start: (int) First index of the buffer that should be returned (>= 1)
            end (int): Last index of the buffer that should be returned
            buffer_name (str): Name of the buffer to read out
            elements (List[str]): List of elements from the buffer to include in the response

        Returns: List of all the readings.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="TRAC:ACTUAL? ${buffer_name}")
    def get_buffer_count(self, buffer_name: str = DEFAULT_BUFFER_1):
        """Returns the number of data points in the specified buffer.

        Args:
            buffer_name (str): Name of the buffer
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="TRACE:POINTS? ${buffer_name}")
    def get_buffer_capacity(self, buffer_name: str):
        """Returns the capacity of the specified buffer.

        Args:
            buffer_name (str): Name of the buffer
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="TRACE:DELETE ${buffer_name}")
    def delete_buffer(self, buffer_name: str) -> None:
        """Deletes the specified buffer.

        Args:
            buffer_name (str): Name of the buffer
        """

        raise NotImplementedError

    @dynamic_interface
    def clear_buffer(self, buffer_name: str) -> None:
        """Clears the given buffer.

        Args:
            buffer_name (str): Name of the buffer
        """

        raise NotImplementedError

    @dynamic_interface
    def create_buffer(self, buffer_name: str, size: int) -> None:
        """Creates a reading buffer with the given name and size.

        Args:
            buffer_name (str): Name of the buffer
            size (size): Maximum number of readings (size >= 10) [default: 1000]
        """

        raise NotImplementedError

    @dynamic_interface
    def configure_sensors(self, channel_list: str, *, sense: Dict[str, List[Tuple]]):
        """Configures the DAQ6510 to sense the specified channels.

        Args:
            channel_list (str): List of channels, as understood by the device
            sense (Dict[str], List[Tuple]): Dictionary with all the information on the configuration of the channels
        """

        raise NotImplementedError

    @dynamic_interface
    def setup_measurements(self, *, buffer_name: str, channel_list: str):
        """Sets up the measurements for the given channel list.

        Args:
            buffer_name (str): Name of the buffer to use [default: defbuffer1]
            channel_list (str): Channels to read out
        """

        raise NotImplementedError

    @dynamic_interface
    def perform_measurement(self, *, buffer_name: str, channel_list: str, count: int, interval: int) -> list:
        """Performs the actual measurements.

        Args:
            buffer_name (str): Name of the buffer
            channel_list (str): List of channels, as understood by the device
            count (int): Number of measurements to perform
            interval (int): Interval between measurements [s]
        """

        raise NotImplementedError


class DAQ6510Controller(DAQ6510Interface, DynamicCommandMixin):
    """
    The DAQ6510 Controller allows to remotely control the Keithley Data Acquisition System
    through an Ethernet interface.
    """

    def __init__(self, hostname: str = FW_SETTINGS.HOSTNAME, port: int = FW_SETTINGS.PORT):
        """Opens a TCP/IP socket connection with the Keithley DAQ6510 Hardware.

        Args:
            hostname (str): IP address or fully qualified hostname of the Hexapod hardware controller. The default is
                            defined in the ``settings.yaml`` configuration file.
            port (int): IP port number to connect to, by default set in the ``settings.yaml`` configuration file.

        Raises:
            Error: when the connection could not be established for some reason.
        """

        super().__init__()

        logger.debug(f"Initializing the DAQ6510 Controller with hostname={hostname} on port={port}")

        self.daq = self.transport = DAQ6510EthernetInterface(hostname, port)

        # We set the default buffer here, this can be changed with the `create_buffer()` method.

        self.buffer_name = DEFAULT_BUFFER_1

    def is_simulator(self) -> bool:
        """Indicates that the device is a real hardware controller

        Returns: False.
        """

        return False

    def connect(self) -> None:
        """Connects to the device controller."""

        self.daq.connect()
        self.notify_observers(DeviceConnectionState.DEVICE_CONNECTED)

    def disconnect(self) -> None:
        """Disconnects from the device controller."""

        self.daq.disconnect()
        self.notify_observers(DeviceConnectionState.DEVICE_NOT_CONNECTED)

    def reconnect(self) -> None:
        """Reconnects to the device controller."""

        if self.is_connected():
            self.disconnect()

        self.connect()

    def is_connected(self) -> bool:
        """Checks whether the device controller is connected.

        Returns: True if the device controller is connected; False otherwise.
        """

        return self.daq.is_connected()

    def send_command(self, command: str, response: bool) -> Union[None, str]:
        """Sends an SCPI command to the device.

        The valid commands are described in the DAQ6510 Reference Manual [DAQ6510-901-01 Rev. B / September 2019].

        Args:
            command (str): SCPI command as specified in the DAQ6510 Reference Manual
            response (bool): Indicates whether you expect a reply from the device

        Returns: The response from the DAQ6510 is returned when a response was expected. When `response` is False,
                 None will be returned.
        """

        return self.daq.trans(command) if response else self.daq.write(command)

    def read_buffer(self, start: int, end: int, buffer_name: str = DEFAULT_BUFFER_1, elements: List[str] = None):
        """Reads specific data elements (measurements) from the given buffer.

        Elements that can be specified to read out:

            - CHANNEL: Channel for which the data was acquired
            - DATE: Date when the data point was measured
            - READING: Actual reading of the measurement
            - TSTAMP: Timestamp when the data point was measured
            - UNIT: Unit of measure for the measurement
            - STATUS: Status information associated with the measurement

        Args:
            start: (int) First index of the buffer that should be returned (>= 1)
            end (int): Last index of the buffer that should be returned
            buffer_name (str): Name of the buffer to read out
            elements (List[str]): List of elements from the buffer to include in the response

        Returns: List of all the readings.
        """

        if elements is None:
            elements = ["READING"]
        else:
            elements = ", ".join(elements)

        return self.daq.trans(f'TRACE:DATA? {start}, {end}, "{buffer_name}", {elements}')

    def clear_buffer(self, buffer_name: str = DEFAULT_BUFFER_1) -> None:
        """Clears the given buffer.

        Args:
            buffer_name (str): Name of the buffer
        """

        response = self.daq.trans(f'TRACE:ACTUAL? "{buffer_name}"')

        logger.info(f"Clearing buffer '{buffer_name}' containing {response} readings.")

        self.daq.write(f'TRACE:CLEAR "{buffer_name}"')

    def create_buffer(self, buffer_name: str, size: int = 1000) -> None:
        """Creates a reading buffer with the given name.

        The name of the buffer must adhere to the following rules:

            - A buffer with this name should not exist in the device yet. When the buffer does exist, the DAQ6510 will
              show  a dialogue on the front panel with error 1115 saying the command cannot take an existing buffer
              name.
            - Buffer names must start with an alphabetic character.
            - The names cannot contain any periods nor the underscore (_) character.
            - The name can be up to 31 characters long.

        If the given size is 0, the instrument creates the largest reading buffer possible based on the available
        memory when the buffer is created.

        Args:
            buffer_name (str): Name of the buffer
            size (size): Maximum number of readings (size >= 10) [default: 1000]
        """

        self.daq.write(f'TRACE:MAKE "{buffer_name}", {size}')

        self.buffer_name = buffer_name

    # def reset(self) -> None:
    #
    #     self.daq.write("SYSTem:BEEPer 500, 0.1; :*RST; :SYSTem:BEEPer 1000, 0.1\n")

    def configure_sensors(self, channel_list: str, *, sense: Dict[str, List[Tuple]]) -> None:
        """Configures the different sensors in the `channel_list`.

        Each sensor in the list will be configured according to the settings given in the `sense` dictionary.

        The following code will configure channels 101 and 102 as 4-wire transducers of type PT100.

        ```
        channel_list = create_channel_list(101, 102)

        sense = {
            "TEMPERATURE": [
                ("TRANSDUCER", "FRTD"),
                ("RTD:FOUR", "PT100"),
            ]
        }

        daq.configure_sensors(channel_list, sense=sense)
        ```

        The `sense` argument is a dictionary where the keys are function names like "TEMPERATURE" or "VOLTAGE:DC",
        and the values are a list of settings for that function. The list of settings is a list of tuples with the
        command and the value, e.g. "TRANSDUCER" is the settings command and "FRTD" is its value. The list of settings
        will be sent to the device in the order that they take in the list.

        Args:
            channel_list (str): Channels to configure
            sense: Dictionary with all the information on the configuration
        """

        if "TEMPERATURE" in sense:
            # Allowed settings for TEMPERATURE:
            #
            # - TEMPERATURE:APERTURE                  (@<channelList>)
            # - TEMPERATURE:AVERAGE:COUNT             (@<channelList>)
            # - TEMPERATURE:AVERAGE:STATE             (@<channelList>)
            # - TEMPERATURE:AVERAGE:TCONTROL          (@<channelList>)
            # - TEMPERATURE:AVERAGE:WINDOW            (@<channelList>)
            # - TEMPERATURE:AVERAGE:AZERO:STATE
            # - TEMPERATURE:DELAY:AUTO
            # - TEMPERATURE:DELAY:USER<N>
            # - TEMPERATURE:LINE:SYNC
            # - TEMPERATURE:NPLCYCLES
            # - TEMPERATURE:OCOMPENSATED
            # - TEMPERATURE:ODETECTOR
            # - TEMPERATURE:RELATIVE
            # - TEMPERATURE:RELATIVE:ACQUIRE
            # - TEMPERATURE:RELATIVE:STATE
            # - TEMPERATURE:RTD:ALPHA, BETA, DELTA      (@<channelList>)
            # - TEMPERATURE:RTD:ZERO, TWO, THREE, FOUR  (@<channelList>)
            # - TEMPERATURE:TCOUPLE:RJUNCTION:SIMULATED
            # - TEMPERATURE:TCOUPLE:RJUNCTION:RSELECT
            # - TEMPERATURE:TCOUPLE:TYPE
            # - TEMPERATURE:THERMISTOR      (@<channelList>)
            # - TEMPERATURE:TRANSDUCER      (@<channelList>)
            # - TEMPERATURE:UNIT            (@<channelList>)
            #

            # set the function to temperature

            self.daq.write(f'SENSE:FUNCTION "TEMPERATURE", {channel_list}')

            for cmd, value in sense["TEMPERATURE"]:
                self.daq.write(f"SENSE:TEMPERATURE:{cmd} {value}, {channel_list}")

    def setup_measurements(self, *, buffer_name: str = DEFAULT_BUFFER_1, channel_list: str) -> None:
        """Sets up the measurements for the given channel list.

        Args:
            buffer_name (str): Name of the buffer to use [default: defbuffer1]
            channel_list (str): Channels to read out
        """

        self.daq.write(f'ROUTE:SCAN:BUFFER "{buffer_name}"')
        self.daq.write(f"ROUTE:SCAN:CREATE {channel_list}")
        self.daq.write(f"ROUTE:CHANNEL:OPEN {channel_list}")
        _ = self.daq.trans(f"ROUTE:CHANNEL:STATE? {channel_list}")
        self.daq.write("ROUTE:SCAN:START:STIMULUS NONE")

    def perform_measurement(
        self,
        *,
        buffer_name: str = DEFAULT_BUFFER_1,
        channel_list: str,
        count: int = 1,
        interval: int = 2,
    ) -> list:
        """Performs the actual measurements.

        This function will wait until all measurements have completed, so be careful with the arguments `count` and
        `interval` as they will multiply into the number of seconds that you will have to wait for the response.

        Args:
            buffer_name (str): Name of the buffer
            channel_list (str): List of channels, as understood by the device
            count (int): Number of measurements to perform
            interval (int): Interval between measurements [s]

        Returns: List of readings.
        """

        # Set the number of times a scan is repeated

        self.daq.write(f"ROUTE:SCAN:COUNT:SCAN {count}")
        self.daq.write(f"ROUTE:SCAN:INTERVAL {interval}")  # [seconds]

        #
        self.daq.write("INITIATE:IMMEDIATE")
        self.daq.write("*WAI")

        # Read out the buffer

        logger.debug("Buffer count = ", self.get_buffer_count())

        num_sensors = count_number_of_channels(channel_list)

        readings = []

        for idx in range(1, count * num_sensors + 1):
            response = self.read_buffer(
                idx, idx, buffer_name=buffer_name, elements=["CHANNEL", "TSTAMP", "READING", "UNIT"]
            )
            if response != "" and response != str(count * num_sensors):
                if "\n" in response:
                    response = response.split("\n")
                    for i in range(len(response)):
                        readings.append(response[i].split(","))
                else:
                    readings.append(response.split(","))
                if len(readings[0]) < 4:
                    del readings[0]

        return readings


class DAQ6510Simulator(DAQ6510Interface):
    """
    Simulator for the Keithley DAQ6510 system.
    """

    def read_buffer(self, start: int, end: int, buffer_name: str, elements: List[str]):
        pass

    def get_buffer_count(self, buffer_name: str = DEFAULT_BUFFER_1):
        pass

    def get_buffer_capacity(self, buffer_name: str):
        pass

    def delete_buffer(self, buffer_name: str):
        pass

    def clear_buffer(self, buffer_name: str):
        pass

    def create_buffer(self, buffer_name: str, size: int):
        pass

    def configure_sensors(self, channel_list: str, *, sense: Dict[str, List[Tuple]]):
        pass

    def setup_measurements(self, *, buffer_name: str, channel_list: str):
        pass

    def perform_measurement(self, *, buffer_name: str, channel_list: str, count: int, interval: int):
        pass

    def send_command(self, command: str, response: bool):
        pass

    def info(self) -> str:
        pass

    def reset(self):
        pass

    def is_simulator(self):
        """Indicates that the device is a simulator.

        Returns: True.
        """

        return True

    def connect(self):
        pass

    def disconnect(self):
        pass

    def reconnect(self):
        pass

    def is_connected(self):
        pass


class DAQ6510Proxy(Proxy, DAQ6510Interface):
    """
    The DAQ6510Proxy class is used to connect to the Keithley Control Server and send commands
    to the Keithley Hardware Controller remotely.
    """

    def __init__(
        self,
        protocol: str = CTRL_SETTINGS.PROTOCOL,
        hostname: str = CTRL_SETTINGS.HOSTNAME,
        port: int = CTRL_SETTINGS.COMMANDING_PORT,
        timeout: int = CTRL_SETTINGS.TIMEOUT * 1000,  # Timeout [ms]: > scan count * interval + (one scan duration)
    ):
        """Initialisation of a DAQ6510Proxy.

        Args:
            protocol (str): Transport protocol [default is taken from settings file]
            hostname (str): Location of the Control Server (IP address) [default is taken from settings file]
            port (int): TCP port on which the Control Server is listening for commands [default is taken from settings
                        file]
            timeout (int): Timeout by which to establish the connection [ms]
        """

        super().__init__(connect_address(protocol, hostname, port), timeout=timeout)


def create_channel_list(*args) -> str:
    """Createa a channel list that is understood by the SCPI commands of the DAQ6510.

    Channel names contain both the slot number and the channel number. The slot number is the number of the slot where
    the card is installed at the back of the device.

    When addressing multiple individual channels, add each of them as a separate argument, e.g. to include channels 1,
    3, and 7 from slot 1, use the following command:

        >>> create_channel_list(101, 103, 107)
        '(@101, 103, 107)'

    To designate a range of channels, only one argument should be given, i.e. a tuple containing two channels
    representing the range. The following tuple `(101, 110)` will create the following response: `"(@101:110)"`. The
    range is inclusive, so this will define a range of 10 channels in slot 1.

        >>> create_channel_list((201, 205))
        '(@201:205)'

    See reference manual for the Keithley DAQ6510 [DAQ6510-901-01 Rev. B / September 2019], chapter 11: Introduction to
    SCPI commands, SCPI command formatting, channel naming.

    Args:
        *args: Tuple or a list of channels

    Returns: String containing the channel list as understood by the device.
    """

    if not args:
        return ""

    # If only one argument is given, I expect either a tuple defining a range or just one channel. When several
    # arguments are given, I expect them all to be individual channels.

    if len(args) == 1:
        arg = args[0]
        if isinstance(arg, tuple):
            ch_list = f"(@{arg[0]}:{arg[1]})"
        else:
            ch_list = f"(@{arg})"

    else:
        ch_list = "(@" + ", ".join([str(arg) for arg in args]) + ")"

    return ch_list


def count_number_of_channels(channel_list: str) -> int:
    """Given a proper channel list, this function counts the number of channels.

    For ranges, it returns the actual number of channels that are included in the range.

        >>> count_number_of_channels("(@1,2,3,4,5)")
        5
        >>> count_number_of_channels("(@1, 3, 5)")
        3
        >>> count_number_of_channels("(@2:7)")
        6

    Args:
        channel_list (str): Channel list as understood by the SCPI commands of DAQ6510

    Returns: Number of channels in the list.
    """

    match = re.match(r"\(@(.*)\)", channel_list)
    group = match.groups()[0]

    parts = group.replace(" ", "").split(",")
    count = 0
    for part in parts:
        if ":" in part:
            split_part = part.split(":")
            count += int(split_part[1]) - int(split_part[0]) + 1
        else:
            count += 1

    return count


def get_channel_names(channel_list: str) -> List[str]:
    """Generates a list of channel names from a given channel list.

    Args:
        channel_list (str): Channel list as understood by the SCPI commands of DAQ6510

    Returns: List of channel names.
    """

    match = re.match(r"\(@(.*)\)", channel_list)
    group = match.groups()[0]

    parts = group.replace(" ", "").split(",")
    names = []
    for part in parts:
        if ":" in part:
            split_part = part.split(":")
            names.extend(str(ch) for ch in range(int(split_part[0]), int(split_part[1]) + 1))
        else:
            names.append(part)

    return names


if __name__ == "__main__":
    logging.basicConfig(level=20)

    print(f'{get_channel_names("(@101:105)")=}')
    print(f'{get_channel_names("(@101, 102, 103, 105)")=}')
    # sys.exit(0)

    daq = DAQ6510Controller()
    daq.connect()
    daq.reset()

    print(daq.info())

    buffer_capacity = daq.get_buffer_capacity()
    print(f"buffer {DEFAULT_BUFFER_1} can still hold {buffer_capacity} readings")

    buffer_count = daq.get_buffer_count()
    print(f"buffer {DEFAULT_BUFFER_1} holds {buffer_count} readings")

    channels = create_channel_list((101, 102))

    print(channels)

    sense_dict = {"TEMPERATURE": [("TRANSDUCER", "FRTD"), ("RTD:FOUR", "PT100"), ("UNIT", "KELVIN")]}

    daq.configure_sensors(channels, sense=sense_dict)

    daq.setup_measurements(channel_list=channels)

    meas_response = daq.perform_measurement(channel_list=channels, count=5, interval=1)

    print(meas_response)

    buffer_count = daq.get_buffer_count()
    print(f"buffer {DEFAULT_BUFFER_1} holds {buffer_count} readings")

    daq.disconnect()
