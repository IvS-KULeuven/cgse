import numpy as np
import threading

from egse.power_supply.rs_pro.rsd3305p_devif import Rsd3305pUsbInterface
from egse.device import DeviceInterface
from egse.mixin import dynamic_command, DynamicCommandMixin, CommandType
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address
from egse.power_supply.rs_pro import (
    CS_SETTINGS,
    PROXY_TIMEOUT,
    OperatingMode,
    to_float,
    decode_status,
    split_result_on_blanks,
    to_string,
    to_int,
)


class Rsd3305pError(Exception):
    """An RS-PRO RS-D3305P-specific error."""

    pass


class Rsd3305pInterface(DeviceInterface):
    """Base class for the RS-PRO RS-D3305P."""

    def __init__(self, device_id: str):
        """Initialisation of an RS-PRO RS-D3305P interface.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__()

        self.device_id = device_id

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="LOCK1")
    def lock_front_panel(self) -> None:
        """Locks the front panel."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="LOCK0",
    )
    def unlock_front_panel(self) -> None:
        """Unlocks the front panel."""

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ISET${channel}:${current}")
    def set_current(self, channel: int, current: float) -> None:
        """Sets the output current for the given channel.

        Args:
            channel (int): Channel number.
            current (float): Current output value [A].

        Example:
            ISET1:2.225 sets the CH1 output current to 2.225A.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="ISET${channel}?",
        process_response=to_float,
    )
    def get_current_config(self, channel: int) -> float:
        """Returns the current setpoint for the given channel.

        Args:
            channel (int): Channel number.

        Returns:
            Current setpoint for the given channel [A].

        Example:
            ISET1? returns the CH1 output current setting.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="VSET${channel}:${voltage}")
    def set_voltage(self, channel: int, voltage: float) -> None:
        """Sets the output voltage for the given channel.

        Args:
            channel (int): Channel number.
            voltage (float): Voltage output value [V].

        Example:
            VSET1:20.50 sets the CH1 output voltage to 20.50V.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="VSET${channel}?",
        process_response=to_float,
    )
    def get_voltage_config(self, channel: int) -> float:
        """Returns the voltage setpoint for the given channel.

        Args:
            channel (int): Channel number.

        Returns:
            Voltage setpoint for the given channel [V].

        Example:
            VSET1? returns the CH1 output voltage setting.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="IOUT${channel}?",
        process_response=to_float,
    )
    def get_current(self, channel: int) -> float:
        """Returns the actual output current for the given channel.

        Args:
            channel (int): Channel number.

        Returns:
              Actual output current for the given channel [A].

        Example:
            IOUT1? returns the CH1 output current.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="VOUT${channel}?",
        process_response=to_float,
    )
    def get_voltage(self, channel: int) -> float:
        """Returns the actual output voltage for the given channel.

        Args:
            channel (int): Channel number.

        Returns:
              Actual output voltage for the given channel [V].

        Example:
            VOUT1? returns the CH1 output voltage.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="TRACK${mode}")
    def select_operating_mode(self, mode: OperatingMode) -> None:
        """Selects the operating mode of the power supply unit.

        Allowed operating modes are:

            - OperatingMode.INDEPENDENT = 0
            - OperatingMode.TRACKING_SERIES = 1
            - OperatingMode.TRACKING_PARALLEL = 2

        Args:
            mode (OperatingMode): Operating mode to select.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BEEP1",
    )
    def enable_beep(self) -> None:
        """Turns on the beep."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="BEEP0",
    )
    def disable_beep(self) -> None:
        """Turns off the beep."""

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="STATUS?", process_response=decode_status)
    def get_status(self) -> dict:
        """Returns the status of the power supply unit.

        The status byte contains the following information:

            - bit 0: 0 when channel 1 is operated in CC mode, 1 when channel 1 is operated in CV mode;
            - bit 1: 0 when channel 2 is operated in CC mode, 1 when channel 2 is operated in CV mode;
            - bits 2 and 3: operating mode (00: independent, 01: tracking series, 10: tracking parallel);
            - bits 4 and 5 -> not mentioned in the documentation;
            - bit 6: 0 if the output of channel 1 is off, 1 if the output of channel 1 is on;
            - bit 7: 0 if the output of channel 2 is off, 1 if the output of channel 2 is on.

        This is decoded into a dictionary with the following keys:

            - "ch1_mode": "CC" or "CV" (mode of channel 1);
            - "ch2_mode": "CC" or "CV" (mode of channel 2);
            - "tracking": "Independent", "Series", or "Parallel" (operating mode);
            - "ch1_on": True if the output of channel 1 is on, False otherwise;
            - "ch2_on": True if the output of channel 2 is on, False otherwise.

        Returns:
            Dictionary of decoded status bytes.  The keys in this dictionary are:

                - "ch1_mode": "CC" or "CV" (mode of channel 1);
                - "ch2_mode": "CC" or "CV" (mode of channel 2);
                - "tracking": "Independent", "Series", or "Parallel" (operating mode);
                - "ch1_on": True if the output of channel 1 is on, False otherwise;
                - "ch2_on": True if the output of channel 2 is on, False otherwise.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*IDN?",
        process_response=split_result_on_blanks,
    )
    def get_id(self) -> tuple[str, str, str]:
        """Returns the instrument identification.

        Returns:
            Tuple with:
                - Manufacturer,
                - Model,
                - Software version.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="RCL${memory}",
    )
    def recall(self, memory: int) -> bytes:
        """Re-calls the panel settings from the given memory slot.

        Args:
            memory (int): Memory slot (0 - 9).

        Returns:
            Panel settings stored in the given memory slot.

        Example:
            RCL1 recalls the panel settings stored in memory slot 1.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SAV${memory}",
    )
    def save(self, memory: int) -> None:
        """Stores the panel setting in the given memory slot.

        Args:
            memory (int): Memory slot (0 - 9).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="OUT${channel}:1",
    )
    def enable_output(self, channel: int) -> None:
        """Turns the output of the given channel on.

        Args:
            channel (int): Channel number (1 or 2).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="OUT${channel}:0",
    )
    def disable_output(self, channel: int) -> None:
        """Turns the output of the given channel off.

        Args:
            channel (int): Channel number (1 or 2).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="OUT12:1",
    )
    def enable_both_outputs(self) -> None:
        """Turns the output of both channels on."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="OUT12:0",
    )
    def disable_both_outputs(self) -> None:
        """Turns the output of both channels off."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="VASTEP${channel}:${start_voltage}, ${end_voltage}, ${step_voltage}, ${step_time}",
    )
    def automatic_voltage_step(
        self, channel: int, start_voltage: float, end_voltage: float, step_voltage: float, step_time: float
    ) -> None:
        """Sets the automatic step voltage output.

        Args:
            channel (int): Channel number (1 or 2).
            start_voltage (float): Start voltage [V].
            end_voltage (float): End voltage [V].
            step_voltage (float): Step voltage [V].
            step_time (float): Step time [s].

        Example:
            VASTEP1:1, 30, 0.1, 0.2 sets the starting voltage of channel 1 to 1V, ending voltage at 30V, step voltage at 0.1V, and set time at 0.2s.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="VAST0P${channel}",
    )
    def stop_automatic_voltage_step(self, channel: int) -> None:
        """Stops the automatic step voltage output.

        Args:
            channel (int): Channel number (1 or 2).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="VSTEP${channel}:${voltage}",
    )
    def set_trigger_voltage_step(self, channel: int, voltage: float) -> None:
        """Sets the trigger step voltage output.

        This sets by which amount the voltage will be increased/decreased when `voltage_up`/`voltage_down` is called.

        Args:
            channel (int): Channel number (1 or 2).
            voltage (float): Trigger step voltage [V].

        Example:
            VSTEP1:1.5 sets the trigger step voltage to 1.5V.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="VUP${channel}",
    )
    def voltage_up(self, channel: int) -> None:
        """Increases the voltage of the given channel.

        The amount by which the voltage is increased is set by `set_trigger_voltage_step`.

        Example:
            Set the trigger step voltage to 1.5V:
                VSTEP1:1.5
            Then increase the voltage of channel 1 by 1.5V:
                VUP1
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="VDOWN${channel}",
    )
    def voltage_down(self, channel: int) -> None:
        """Decreases the voltage of the given channel.

        The amount by which the voltage is decreased is set by `set_trigger_voltage_step`.

        Example:
            Set the trigger step voltage to 1.5V:
                VSTEP1:1.5
            Then decrease the voltage of channel 1 by 1.5V:
                VDOWN1
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="IASTEP${channel}:${start_current}, ${end_current}, ${step_current}, ${step_time}",
    )
    def automatic_current_step(
        self, channel: int, start_current: float, end_current: float, step_current: float, step_time: float
    ) -> None:
        """Sets the automatic step current output.

        Args:
            channel (int): Channel number (1 or 2).
            start_current (float): Start current [A].
            end_current (float): End current [A].
            step_current (float): Step current [A].
            step_time (float): Step time [s].

        Example:
            IASTEP2:1, 3, 0.1, 1 sets the starting current of channel 1 to 1V, ending current at 3V, step current at 0.1A, and set time at 1s.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="IAST0P${channel}",
    )
    def stop_automatic_current_step(self, channel: int) -> None:
        """Stops the automatic step current output.

        Args:
            channel (int): Channel number (1 or 2).
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="ISTEP${channel}:${current}",
    )
    def set_trigger_current_step(self, channel: int, current: float) -> None:
        """Sets the trigger step current output.

        This sets by which amount the current will be increased/decreased when `current_up`/`current_down` is called.

        Args:
            channel (int): Channel number (1 or 2).
            current (float): Trigger step current [A].

        Example:
            ISTEP1:0.5 sets the trigger step voltage to 0.5A.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="IUP${channel}",
    )
    def current_up(self, channel: int) -> None:
        """Increases the current of the given channel.

        The amount by which the current is increased is set by `set_trigger_current_step`.

        Example:
            Set the trigger step current to 0.5V:
                ISTEP1:0.5
            Then increase the current of channel 1 by 0.5A:
                IUP1
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="IDOWN${channel}",
    )
    def current_down(self, channel: int) -> None:
        """Decreases the current of the given channel.

        The amount by which the current is decreased is set by `set_trigger_current_step`.

        Example:
            Set the trigger step current to 0.5A:
                ISTEP1:0.5
            Then decrease the current of channel 1 by 0.5A:
                IDOWN1
        """
        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string=":SYST:IPAD ${ip_address}",
    )
    def set_ip_address(self, ip_address: str) -> None:
        """Sets the IP address of the power supply unit.

        Args:
            ip_address (str): IP address to set.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string=":SYST:IPAD?", process_response=to_string)
    def get_ip_address(self) -> str:
        """Returns the IP address of the power supply unit.

        Returns:
            IP address of the power supply unit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string=":SYST:SMASK",
    )
    def set_subnet_mask(self, subnet_mask: str) -> None:
        """Sets the subnet mask of the power supply unit.

        Args:
            subnet_mask (str): Subnet mask to set.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=":SYST:SMASK?",
        process_response=to_string,
    )
    def get_subnet_mask(self) -> str:
        """Returns the subnet mask of the power supply unit.

        Returns:
            Subnet mask of the power supply unit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string=":SYST:DHCP 1",
    )
    def enable_dhcp(self) -> None:
        """Enables the DHCP mode of the power supply unit."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string=":SYST:DHCP 0",
    )
    def disable_dhcp(self) -> None:
        """Disables the DHCP mode of the power supply unit."""

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string=":SYST:MAC?", process_response=to_string)
    def get_mac_address(self) -> str:
        """Returns the MAC address of the power supply unit.

        Returns:
            MAC address of the power supply unit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string=":SYST:PORT?",
    )
    def set_port(self, port: int) -> None:
        """Sets the port of the power supply unit.

        The port number should be a number in the range 0-65535, excl. 18191.

        Args:
            port (int): Port to set for the power supply unit [1, 65535].
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=":SYST:PORT?",
        process_response=to_int,
    )
    def get_port(self) -> int:
        """Returns the port of the power supply unit.

        The port number should be a number in the range 0-65535, excl. 18191.

        Returns:
            Port of the power supply unit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string=":SYST:BAUD ${baudrate}",
    )
    def set_baudrate(self, baudrate: int) -> None:
        """Sets the baudrate of the power supply unit.

        Args:
            baudrate (int): Baudrate to set for the power supply unit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=":SYST:BAUD?",
        process_response=to_int,
    )
    def get_baudrate(self) -> int:
        """Returns the baudrate of the power supply unit.

        Returns:
            Baudrate of the power supply unit.
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string=":SYST:DEVINFO?",
    )
    def get_device_info(self) -> dict:
        """Returns the device information of the power supply unit.

        Returns:
            TODO
        """

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string=":SYST:FACTRESET",
    )
    def reset(self) -> None:
        """Restores the factory defaults of the interface."""

        raise NotImplementedError

    # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OCP${int(ocp)}", process_cmd_string=add_lf)
    # def set_ocp(self, ocp: bool) -> None:
    #     """Turns the power supply unit's OCP on/off.
    #
    #     Args:
    #         ocp (bool): True to turn the OCP on; False to turn the OCP off.
    #     """
    #
    #     raise NotImplementedError
    #
    # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OCP1", process_cmd_string=add_lf)
    # def enable_ocp(self) -> None:
    #     """Turns the power supply unit's OCP on."""
    #
    #     raise NotImplementedError
    #
    # @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OCP0", process_cmd_string=add_lf)
    # def disable_ocp(self) -> None:
    #     """Turns the power supply unit's OCP off."""
    #
    #     raise NotImplementedError


class Rsd3305pController(Rsd3305pInterface, DynamicCommandMixin):
    """RS-PRO RS-D3305P device controller interface."""

    def __init__(self, device_id: str):
        """Initialisation of an RS-PRO RS-D3305P power supply with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

        self.transport = self.rsd3305p = Rsd3305pUsbInterface(device_id=device_id)

    # noinspection PyMethodMayBeStatic
    def is_simulator(self) -> bool:
        return False

    def is_connected(self) -> bool:
        """Checks whether the connection to the RS-PRO RS-D3305P is open.

        Returns:
            True if the connection to the RS-PRO RS-D3305P is open; False otherwise.
        """

        return self.transport.is_connected()

    def connect(self):
        """Opens the connection to the RS-PRO RS-D3305P.

        Raises:
            Rsd3305pError: When the connection could not be opened.
        """

        self.transport.connect()

    def disconnect(self):
        """Closes the connection to the RS-PRO RS-D3305P.

        Raises:
            Rsd3305pError: When the connection could not be closed.
        """

        self.transport.disconnect()

    def reconnect(self):
        """Re-connects to the RS-PRO RS-D3305P."""

        self.transport.reconnect()


class Rsd3305pSimulator(Rsd3305pInterface):
    def __init__(self, device_id: str):
        """Initalisation of a simulator for the RS-PRO RS-D3305P arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

        self.output_enabled = [False, False]

        self.voltage_setpoints = [0, 0]
        self.current_setpoints = [0, 0]

        self.trigger_voltage_step = [0, 0]
        self.trigger_current_step = [0, 0]

        self.operating_mode = OperatingMode.INDEPENDENT

    def lock_front_panel(self) -> None:
        pass

    def unlock_front_panel(self) -> None:
        pass

    def set_current(self, channel: int, current: float) -> None:
        self.voltage_setpoints[channel - 1] = current

    def get_current_config(self, channel: int) -> float:
        return self.voltage_setpoints[channel - 1]

    def set_voltage(self, channel: int, voltage: float) -> None:
        self.current_setpoints[channel - 1] = voltage

    def get_voltage_config(self, channel: int) -> float:
        return self.current_setpoints[channel - 1]

    def get_current(self, channel: int) -> float:
        if self.output_enabled[channel - 1]:
            return np.random.normal(self.get_current_config(channel), 1, 1)
        else:
            return 0

    def get_voltage(self, channel: int) -> float:
        return np.random.normal(self.get_voltage_config(channel), 1, 1)

    def select_operating_mode(self, mode: OperatingMode) -> None:
        self.operating_mode = mode

    def enable_beep(self):
        pass

    def disable_beep(self):
        pass

    def get_status(self):
        # TODO
        pass

    def get_id(self) -> tuple[str, str, str]:
        return "RS-D3305P", "VX.X", "SN:XXXXXX"

    def save(self, memory: int) -> None:
        pass

    def recall(self, memory: int) -> bytes:
        pass

    def enable_output(self, channel: int):
        self.output_enabled[channel - 1] = True

    def disable_output(self, channel: int):
        self.output_enabled[channel - 1] = False

    def enable_both_outputs(self) -> None:
        self.enable_output(1)
        self.enable_output(2)

    def disable_both_outputs(self) -> None:
        self.disable_output(1)
        self.disable_output(2)

    def set_trigger_voltage_step(self, channel: int, voltage: float) -> None:
        self.trigger_voltage_step[channel - 1] = voltage

    def voltage_up(self, channel: int) -> None:
        self.voltage_setpoints[channel - 1] += self.trigger_voltage_step[channel - 1]

    def voltage_down(self, channel: int) -> None:
        self.voltage_setpoints[channel - 1] -= self.trigger_voltage_step[channel - 1]

    def set_trigger_current_step(self, channel: int, current: float) -> None:
        self.trigger_current_step[channel - 1] = current

    def current_up(self, channel: int) -> None:
        self.current_setpoints[channel - 1] += self.trigger_current_step[channel - 1]

    def current_down(self, channel: int) -> None:
        self.current_setpoints[channel - 1] -= self.trigger_current_step[channel - 1]


class Rsd3305pProxy(DynamicProxy, Rsd3305pInterface):
    def __init__(self, device_id: str):
        """Initialisation of a proxy for the RS-PRO RS-D3305P arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        # super().__init__(device_id)

        hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")
        protocol = CS_SETTINGS[device_id].get("PROTOCOL", "tcp")
        commanding_port = CS_SETTINGS[device_id].get("COMMANDING_PORT", 0)
        service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "rsd3305p_cs")

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
