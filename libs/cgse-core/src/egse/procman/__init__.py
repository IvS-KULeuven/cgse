import logging
import textwrap
from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import is_control_server_active
from egse.decorators import dynamic_interface
from egse.listener import EventInterface, Event
from egse.plugin import entry_points
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
    """ Checks if the Process Manager Control Server is active.

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
    """ Returns a string representing the status of the Process Manager.

    Returns: String representation of the status of the Process Manager.
    """

    if is_process_manager_active():
        with ProcessManagerProxy() as sm:
            text =  textwrap.dedent(
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


class ProcessManagerCommand(ClientServerCommand):
    """ Client-server command for the Process Manager."""

    pass


class ProcessManagerInterface(EventInterface):
    
    def __init__(self):
        
        super().__init__()
        self.setup = load_setup()

    @dynamic_interface
    def get_core_processes(self) -> dict:
        """ Returns a dictionary with the core CGSE processes.

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
        """ Returns a dictionary with the devices that are included in the setup.

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
        """ Returns a list with the identifiers of the devices that are included in the setup.

        The devices for which the identifiers are returned are the ones that are included in the setup that is currently
        loaded in the Configuration Manager.

        Returns: List with the identifiers of the devices that are included in the setup.
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


class ProcessManagerProxy(Proxy, ProcessManagerInterface):
    """ Proxy for process management, used to connect to the Process Manager Control Server and send commands remotely.
    """

    def __init__(self, protocol: str = None, hostname: str = None, port: int = -1, timeout=PROXY_TIMEOUT):
        """ Initialisation of a new Proxy for Process Management.

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
                    protocol = service.get('protocol', 'tcp')
                    hostname = service['host']
                    port = service['port']
                else:
                    raise RuntimeError(f"No service registered as {CTRL_SETTINGS.SERVICE_TYPE}")

        super().__init__(connect_address(protocol, hostname, port), timeout=timeout)
