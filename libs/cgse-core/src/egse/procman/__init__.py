import logging
import subprocess
import textwrap
from pathlib import Path
from typing import Union

from egse.command import ClientServerCommand
from egse.control import is_control_server_active
from egse.decorators import dynamic_interface
from egse.listener import EventInterface, Event
from egse.plugin import entry_points
from egse.process import SubProcess
from egse.proxy import Proxy
from egse.registry.client import RegistryClient
from egse.settings import Settings
from egse.setup import Setup, load_setup
from egse.storage import is_storage_manager_active
from egse.zmq_ser import connect_address

HERE = Path(__file__).parent
LOGGER = logging.getLogger("egse.procman")

CTRL_SETTINGS = Settings.load("Process Manager Control Server")
COMMAND_SETTINGS = Settings.load(location=HERE, filename="procman.yaml")
PROXY_TIMEOUT = 10_000


def is_process_manager_active(timeout: float = 0.5) -> bool:
    """Checks if the Process Manager Control Server is active.

    To check whether the Process Manager is active, a "Ping" command is sent.  If a "Pong" reply is received before
    timeout, that means that the Control Server is active (and True will be returned).  If no reply is received before
    timeout or if the reply is not "Pong", the Control Server is inactive (and False will be returned).

    Args:
        - timeout (float): Timeout when waiting for a reply [s] from the Control Server

    Returns: True if the Process Manager Control Server is active; False otherwise.
    """

    with RegistryClient() as client:
        endpoint = client.get_endpoint(CTRL_SETTINGS.SERVICE_TYPE)

    if endpoint is None:
        return False

    return is_control_server_active(endpoint, timeout)


def get_status() -> str:
    """Returns a string representing the status of the Process Manager.

    Returns: String representation of the status of the Process Manager.
    """

    if is_process_manager_active():
        with ProcessManagerProxy() as sm:
            text = textwrap.dedent(
                f"""\
                Process Manager:
                    Status: [green]active[/]
                    Hostname: {sm.get_ip_address()}
                    Monitoring port: {sm.get_monitoring_port()}
                    Commanding port: {sm.get_commanding_port()}
                    Service port: {sm.get_service_port()}
                """
            )
        return text

    else:
        return "Process Manager Status: [red]not active"


class StartCommand:
    """Command to start the Control Server for a device."""

    def __init__(self, device_id: str, cgse_cmd: str, device_args: Union[list, None], simulator_mode: bool = False):
        """Initialisation of a start command for a device Control Server.

        Args:
            device_id (str): Device identifier
            cgse_cmd (str): CGSE command to start/stop the Control Server or to query its status
            device_args (Union[list, None]): Device arguments
            simulator_mode (bool): Whether to start the Control Server in simulator mode rather than operational mode
        """

        self._device_id = device_id
        self._cgse_cmd = cgse_cmd
        self._device_args = device_args
        self._simulator_mode = simulator_mode

    @property
    def device_id(self) -> str:
        """Returns the device identifier.

        Returns: Device identifier
        """

        return self._device_id

    @property
    def device_args(self) -> Union[list, None]:
        """Returns the device arguments.

        Returns: Device arguments
        """

        return self._device_args

    @property
    def cmd(self) -> str:
        """Returns the full CGSE command to start the Control Server.

        Returns: Full CGSE command to start the Control Server.
        """

        cmd = f"{self._cgse_cmd} start {self.device_id}"

        if self.device_args:
            cmd = f"{cmd} {self.device_args}"
        if self.simulator_mode:
            cmd = f"{cmd} --sim"

        return cmd

    @property
    def simulator_mode(self) -> bool:
        """Checks whether the Control Server should be started in simulator mode rather than operational mode.

        Returns: True if the Control Server should be started in simulator mode; False otherwise.
        """

        return self._simulator_mode


class StopCommand:
    """Command to stop the Control Server for a device."""

    def __init__(self, device_id: str, cgse_cmd: str):
        """Initialisation of a stop command for a device Control Server.

        Args:
            device_id (str): Device identifier
            cgse_cmd (str): CGSE command to start/stop the Control Server or to query its status
        """

        self._device_id = device_id
        self._cgse_cmd = cgse_cmd

    @property
    def device_id(self) -> str:
        """Returns the device identifier.

        Returns: Device identifier
        """

        return self._device_id

    @property
    def cmd(self) -> str:
        """Returns the full CGSE command to stop the Control Server.

        Returns: Full CGSE command to stop the Control Server.
        """

        return f"{self._cgse_cmd} stop {self.device_id}"


class StatusCommand:
    """Command to query the status of a Control Server for a device."""

    def __init__(self, device_id: str = None, cgse_cmd: str = None):
        """Initialisation of a status command for a device Control Server.

        Args:
            device_id (str): Device identifier
            cgse_cmd (str): CGSE command to start/stop the Control Server or to query its status
        """

        self._device_id = device_id
        self._cgse_cmd = cgse_cmd

    @property
    def device_id(self) -> str:
        """Returns the device identifier.

        Returns: Device identifier
        """

        return self._device_id

    @property
    def cmd(self) -> str:
        """Returns the full CGSE command to query the status of the Control Server.

        Returns: Full CGSE command to query the status of the Control Server.
        """
        return f"{self._cgse_cmd} status {self.device_id}"


class ProcessManagerCommand(ClientServerCommand):
    """Client-server command for the Process Manager."""

    pass


class ProcessManagerInterface(EventInterface):
    def __init__(self):
        super().__init__()
        self.setup = load_setup()

    @dynamic_interface
    def get_core_processes(self) -> dict:
        """Returns a dictionary with the core CGSE processes.

        These processes should be running at all times, and can neither be started nor shut down from the Process
        Manager.  On an operational machine, these processes should be added to systemd to make sure they are
        re-started automatically if they are stopped.

        The keys in the dictionary are the names of the core processes (as they will be displayed in the PM UI).  The
        values are the names of the scripts as defined in the pyproject.toml file(s) under `[project.scripts]`.  Those
        can be used to start and stop the core processes, and to request their status.

        Returns: Dictionary with the core CGSE processes.
        """

        raise NotImplementedError

    # @dynamic_interface
    # def get_processing_processes(self):
    #
    #     raise NotImplementedError
    #
    # @dynamic_interface
    # def get_sut_processes(self):
    #
    #     raise NotImplementedError

    @dynamic_interface
    def get_devices(self) -> dict:
        """Returns a dictionary with the devices that are included in the setup.

        The device processes that are listed in the returned dictionary are the ones that are included in the setup
        that is currently loaded in the Configuration Manager.  The keys in the dictionary are taken from the
        "device_name" entries in the setup file.  The corresponding values consist of a tuple with the following
        entries:
            - `device` raw value (should be `Proxy` classes);
            - device identifier;
            - device arguments (optional);

        Returns: Dictionary with the devices that are included in the setup. The keys are the device name,
                 the values are tuples with the 'device' raw value, device identifier, and the (optional) device
                 arguments as a tuple.
        """

        raise NotImplementedError

    @dynamic_interface
    def get_device_ids(self) -> dict:
        """Returns a list with the identifiers of the devices that are included in the setup.

        The devices for which the identifiers are returned are the ones that are included in the setup that is currently
        loaded in the Configuration Manager.

        Returns: List with the identifiers of the devices that are included in the setup.
        """

        raise NotImplementedError

    @dynamic_interface
    def start_process(self, start_cmd: StartCommand) -> None:
        """Starts a process.

        Args:
            start_cmd (StartCommand): Command to start a process
        """

        raise NotImplementedError

    @dynamic_interface
    def stop_process(self, stop_cmd: StopCommand) -> None:
        """Stops a process.

        Args:
            stop_cmd (StopCommand): Command to stop a process
        """

        raise NotImplementedError

    @dynamic_interface
    def get_core_service_status(self, status_cmd: StatusCommand) -> dict:
        """Returns the status of a core service.

        Args:
            status_cmd (StatusCommand): Command to query the status of a core service

        Returns: Status of a core service
        """

        raise NotImplementedError

    @dynamic_interface
    def get_device_process_status(self, status_cmd: StatusCommand) -> dict:
        """Returns the status of a process.

        Args:
            status_cmd (StatusCommand): Command to query the status of a process

        Returns: Status of a process
        """

        raise NotImplementedError


class ProcessManagerController(ProcessManagerInterface):
    def __init__(self):
        super().__init__()

        # self._configuration = ConfigurationManagerProxy()

        if not is_storage_manager_active():
            LOGGER.error("No Storage Manager available!!!!")

    def get_core_processes(self) -> dict:
        core_processes = {}
        for ep in sorted(entry_points("cgse.process_management.core_services"), key=lambda x: x.name):
            core_processes[ep.name] = ep.value

        return core_processes

    def get_devices(self) -> dict:
        try:
            setup = load_setup()

            devices = {}
            devices = Setup.find_devices(setup, devices=devices)

            return devices

        except AttributeError:
            return {}

    def get_device_ids(self) -> dict:
        try:
            setup = load_setup()

            device_ids = {}
            device_ids = Setup.find_device_ids(setup, device_ids=device_ids)

            return device_ids

        except AttributeError:
            return {}

    def handle_event(self, event: Event):
        LOGGER.info(f"An event is received, {event=}")
        LOGGER.info(f"Setup ID: {event.context['setup_id']}")

        self.setup = load_setup(setup_id=event.context["setup_id"])

    def start_process(self, start_cmd: StartCommand):
        # subprocess.call(start_cmd.cmd, shell=True) -> PM hangs
        process = SubProcess("MyApp", [start_cmd.cmd], shell=True)
        process.execute()

    def stop_process(self, stop_cmd: StopCommand):
        subprocess.call(stop_cmd.cmd, shell=True)

    def get_core_service_status(self, status_cmd: StatusCommand) -> dict:
        output = subprocess.check_output(status_cmd.cmd, shell=True).decode("utf-8")
        cs_is_active = not ("inactive" in output or "not active" in output)

        return {"core_service_name": status_cmd.device_id, "core_service_is_active": cs_is_active}

    def get_device_process_status(self, status_cmd: StatusCommand) -> dict:
        output = subprocess.check_output(status_cmd.cmd, shell=True).decode("utf-8")
        # return output
        cs_is_active = not ("inactive" in output or "not active" in output)

        if cs_is_active:
            device_is_connected = not "not connected" in output
            is_simulator_mode = "simulator" in output

            return {
                "device_id": status_cmd.device_id,
                "cs_is_active": True,
                "device_is_connected": device_is_connected,
                "is_simulator_mode": is_simulator_mode,
            }
        else:
            return {"device_id": status_cmd.device_id, "cs_is_active": False}


class ProcessManagerProxy(Proxy, ProcessManagerInterface):
    """Proxy for process management, used to connect to the Process Manager Control Server and send commands remotely."""

    def __init__(self, protocol: str = None, hostname: str = None, port: int = -1, timeout=PROXY_TIMEOUT):
        """Initialisation of a new Proxy for Process Management.

        If no connection details (transport protocol, hostname, and port) are not provided, these are taken from the
        settings file.

        Args:
            protocol (str): Transport protocol
            hostname (str): Location of the control server (IP address)
            port (int): TCP port on which the Control Server is listening for commands
        """

        if hostname is None:
            with RegistryClient() as reg:
                service = reg.discover_service(CTRL_SETTINGS.SERVICE_TYPE)

                if service:
                    protocol = service.get("protocol", "tcp")
                    hostname = service["host"]
                    port = service["port"]
                else:
                    raise RuntimeError(f"No service registered as {CTRL_SETTINGS.SERVICE_TYPE}")

        super().__init__(connect_address(protocol, hostname, port), timeout=timeout)
