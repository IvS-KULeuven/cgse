from egse.power_supply.rs_pro.rsd3000_devif import Rsd3000EthernetInterface
from egse.device import DeviceInterface
from egse.mixin import dynamic_command, add_lf, DynamicCommandMixin, CommandType
from egse.proxy import DynamicProxy
from egse.registry.client import RegistryClient
from egse.zmq_ser import connect_address
from egse.power_supply.rs_pro import CS_SETTINGS, PROXY_TIMEOUT


def split_result_on_comma(response: str) -> tuple[str, ...]:
    """Splits the given response string on commas.

    Args:
        response (str): Response string to split.

    Returns:
        Tuple of strings split on commas.
    """

    return tuple(response.split(","))


def to_float(response: str) -> float:
    """Converts the given response string to a float.

    Args:
        response (str): Response string to convert.

    Returns:
        Float value converted from the response string.
    """

    return float(response)


class Rsd3000Error(Exception):
    """An RS-PRO RS-D3000-specific error."""

    pass


class Rsd3000Interface(DeviceInterface):
    """Base class for the RS-PRO RS-D3000 series."""

    def __init__(self, device_id: str):
        """Initialisation of an RS-PRO RS-D3000 interface.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__()

        self.device_id = device_id

        self.ethernet_interface = Rsd3000EthernetInterface(device_id=device_id)

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="*IDN?",
        process_cmd_string=add_lf,
        process_response=split_result_on_comma,
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

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="ISET${channel}:${current}", process_cmd_string=add_lf)
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
        process_cmd_string=add_lf,
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

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="IOUT{channel}?",
        process_cmd_string=add_lf,
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

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="VSET${channel}:${voltage}", process_cmd_string=add_lf)
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
        process_cmd_string=add_lf,
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
        cmd_string="VOUT{channel}?",
        process_cmd_string=add_lf,
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

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OUT{int(bool)}", process_cmd_string=add_lf)
    def set_output(self, output: bool) -> None:
        """Turns the output on or off.

        Args:
            output (bool): True to turn the output on; False to turn the output off.

        Example:
            OUT1 turns on the output.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OUT1", process_cmd_string=add_lf)
    def enable_output(self) -> None:
        """Turns the output on."""

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OUT0", process_cmd_string=add_lf)
    def disable_output(self) -> None:
        """Turns the output off."""

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.TRANSACTION,
        cmd_string="RCL${memory}",
        process_cmd_string=add_lf,
    )
    def recall(self, memory: int) -> bytes:
        """Re-calls the panel settings from the given memory slot.

        Args:
            memory (int): Memory slot (1 - 5).

        Returns:
            Panel settings stored in the given memory slot.
        """

        # TODO Input argument?

        raise NotImplementedError

    @dynamic_command(
        cmd_type=CommandType.WRITE,
        cmd_string="SAV${memory}",
        process_cmd_string=add_lf,
    )
    def save(self, memory: int) -> None:
        """Stores the panel setting in the given memory slot.

        Args:
            memory (int): Memory slot (1 - 5).
        """

        # TODO Input argument?

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.TRANSACTION, cmd_string="STATUS?", process_cmd_string=add_lf)
    def get_status(self) -> bytes:
        """Returns the status of the power supply unit."""

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OCP${int(ocp)}", process_cmd_string=add_lf)
    def set_ocp(self, ocp: bool) -> None:
        """Turns the power supply unit's OCP on/off.

        Args:
            ocp (bool): True to turn the OCP on; False to turn the OCP off.
        """

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OCP1", process_cmd_string=add_lf)
    def enable_ocp(self) -> None:
        """Turns the power supply unit's OCP on."""

        raise NotImplementedError

    @dynamic_command(cmd_type=CommandType.WRITE, cmd_string="OCP0", process_cmd_string=add_lf)
    def disable_ocp(self) -> None:
        """Turns the power supply unit's OCP off."""

        raise NotImplementedError


class Rsd3000Controller(Rsd3000Interface, DynamicCommandMixin):
    """RS-PRO RS-D3000 device controller interface."""

    def __init__(self, device_id: str):
        """Initialisation of an RS-PRO RS-D3000 arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

        self.transport = self.rsd3000 = Rsd3000EthernetInterface(device_id=device_id)

    # noinspection PyMethodMayBeStatic
    def is_simulator(self) -> bool:
        return False

    def is_connected(self) -> bool:
        """Checks whether the connection to the RS-PRO RS-D3000 is open.

        Returns:
            True if the connection to the RS-PRO RS-D3000 is open; False otherwise.
        """

        return self.transport.is_connected()

    def connect(self):
        """Opens the connection to the RS-PRO RS-D3000.

        Raises:
            Rsd3000Error: When the connection could not be opened.
        """

        self.transport.connect()

    def disconnect(self):
        """Closes the connection to the RS-PRO RS-D3000.

        Raises:
            Rsd3000Error: When the connection could not be closed.
        """

        self.transport.disconnect()

    def reconnect(self):
        """Re-connects to the RS-PRO RS-D3000."""

        self.transport.reconnect()


class Rsd3000Simulator(Rsd3000Interface):
    def __init__(self, device_id: str):
        """Initalisation of a simulator for the RS-PRO RS-D3000 arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        super().__init__(device_id)

    # def get_id(self) -> (str, str, str):
    #     return "THURLBY THANDAR", "TGF4162", "527758", 01.00, 02.10, 01.20


class Rsd3000Proxy(DynamicProxy, Rsd3000Interface):
    def __init__(self, device_id: str):
        """Initialisation of a proxy for the RS-PRO RS-D3000 arbitrary wave generator with the given identifier.

        Args:
            device_id (str): Device identifier, as per (local) settings and setup.
        """

        # super().__init__(device_id)

        hostname = CS_SETTINGS[device_id].get("HOSTNAME", "localhost")
        protocol = CS_SETTINGS[device_id].get("PROTOCOL", "tcp")
        commanding_port = CS_SETTINGS[device_id].get("COMMANDING_PORT", 0)
        service_type = CS_SETTINGS[device_id].get("SERVICE_TYPE", "rsd3000_cs")

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
