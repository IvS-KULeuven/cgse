"""
This module provides Process Management functionality for the Common-EGSE.
"""
import importlib
import logging
import pickle
import time

import sys
from pathlib import Path

import zmq

from egse.command import ClientServerCommand
from egse.confman import ConfigurationManagerProxy
from egse.control import ControlServer
from egse.response import Success, Failure
from egse.decorators import dynamic_interface
from egse.dpu import fitsgen
from egse.dpu.dpu_cs import is_dpu_cs_active
from egse.fee import n_fee_hk
from egse.fov import fov_hk
from egse.process import SubProcess
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.settings import Settings
from egse.setup import Setup
from egse.state import GlobalState
from egse.storage import is_storage_manager_active
from egse.system import find_class
from egse.system import format_datetime
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

HERE = Path(__file__).parent

CTRL_SETTINGS = Settings.load("Process Manager Control Server")
COMMAND_SETTINGS = Settings.load(location=HERE, filename="procman.yaml")

LOGGER = logging.getLogger(__name__)


def is_process_manager_cs_active(timeout: float = 0.5):
    """Checks if the Process Manager Control Server is active.

    To check whether the Control Server is active, a "Ping" command is sent.
    If a "Pong" reply is received before timeout, the Control Server is said
    to be active (and True will be returned).  If no reply is received before
    timeout or if the reply is not "Pong", the Control Server is said to be
    inactive (and False will be returned).

    Args:
        - timeout (float): Timeout when waiting for a reply [s].

    Returns:
        True if the Process Manager Control Server is active; False otherwise.
    """

    # Create a socket and connect it to the commanding port of the CS

    socket = zmq.Context.instance().socket(zmq.REQ)
    endpoint = connect_address(
        CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.HOSTNAME, CTRL_SETTINGS.COMMANDING_PORT
    )
    socket.connect(endpoint)

    # Send a "Ping" command and wait for a reply
    # (but not beyond timeout)

    data = pickle.dumps("Ping")
    socket.send(data)
    rlist, _, _ = zmq.select([socket], [], [], timeout=timeout)

    # Reply received before timeout
    # (should be "Pong")

    status = False

    if socket in rlist:

        # Only if the reply is "Pong", the CS is active

        data = socket.recv()
        response = pickle.loads(data)

        status = response == "Pong"

    # No reply received -> inactive

    socket.close(linger=0)

    return status


class ProcessManagerProtocol(CommandProtocol):

    """
    Command Protocol for Process Management.
    """

    def __init__(self, control_server: ControlServer):
        """Initialisation of a new Protocol for Process Management.

        The initialisation of this Protocol consists of the following steps:

            - create a Controller to which the given Control Server should send commands;
            - load the commands;
            - build a look-up table for the commands.

        Args:
            - control_server: Control Server via which commands should be sent
                              to the Controller.
        """

        super().__init__()

        # Control Server for Process Management

        self.control_server = control_server

        # Create a new Controller for Process Management

        self.controller = ProcessManagerController()

        # Load the commands (for commanding of the PM Controller) from the
        # YAML file into a dictionary, stored in the PM Protocol

        self.load_commands(
            COMMAND_SETTINGS.Commands, ProcessManagerCommand, ProcessManagerController
        )

        # Build a look-up table for the methods

        self.build_device_method_lookup_table(self.controller)

    def get_bind_address(self):
        """Returns the address to bind a socket to.

        This bind address is a properly formatted URL, based on the
        communication protocol and the commanding port.

        Returns:
            - Properly formatted URL to bind a socket to.
        """

        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_status(self) -> dict:
        """Returns the status information for the Control Server.

        This status information is returned in the form of a dictionary that
        contains the following information about the Control Server for
        Process Management:

            - timestamp (str): string representation of the current datetime;
            - PID (int): process ID for the Control Server;
            - Up (float): uptime of the Control Server [s];
            - UUID (uuid1): Universally Unique Identifier for the Control
                            Server;
            - RSS (int): 'Resident Set Size', this is the non-swapped physical
                         memory a process has used [byte];
            - USS (int): 'Unique Set Size', this is the memory which is unique
                         to a process [byte];
            - CPU User (float): time spent in user mode [s];
            - CPU System (float): time spent in kernel mode [s];
            - CPU count: number of CPU cores in use by the process;
            - CPU% (float): process CPU utilization as a percentage [%].

        Returns:
            - Dictionary with status information for the Control Server for
              Process Management.
        """

        return super().get_status()

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping data for the Control Server.

        This housekeeping data is returns in the form of a dictionary that
        contains the following information about the Control Server for
        Process Management:

            - timestamp (str): string representation of the current datetime.

        Returns:
            - Dictionary with housekeeping data for the Control Server for
              Process Management.
        """

        return {"timestamp": format_datetime()}

    def quit(self):
        self.controller.quit()


class ProcessManagerCommand(ClientServerCommand):

    """
    Command (client-server) for Process Management.
    """

    pass


class ProcessManagerInterface:

    """
    Interface for dynamic loading of the commands for Process Management.
    """

    @dynamic_interface
    def get_cm_proxy(self):
        """
        Returns the Proxy for Configuration Management.

        Returns:
            - Proxy for Configuration Management.
        """

        raise NotImplementedError

    @dynamic_interface
    def start_cs(self, process_name, sim_mode):
        """Start the device Control Server with the given process name.

        This method can only be used to start the Control Server of a device
        that is included in the current setup.  Core processes (Storage,
        Configuration Manager, and Process Manager) cannot be started with
        this method.

        The Control Server can either be started in simulator mode (without
        H/W controller available) or in operational mode (with H/W controller
        available).

        The given process name is the one that is used as device name in the
        setup file and can also be found in the dictionary returned by the
        get_devices() method.

        Args:
            - process_name: Device name for which the Control Server should be
                            started.
            - sim_mode: Whether or not to start the Control Server in
                        simulator mode.
        """

        raise NotImplementedError

    @dynamic_interface
    def start_egse(self):
        """Start all device Control Servers in the current setup in operational mode.

        This method can only be used to start the Control Servers of the
        devices that are included in the current setup.  Core processes
        (Storage, Configuration Manager, and Process Manager) cannot be
        started with this method.
        """

        raise NotImplementedError

    @dynamic_interface
    def shut_down_egse(self, process_name):
        """Shut down the device Control Server with the given process name.

        This method can only be used to shut down the Control Server of a
        device that is included in the current setup.  Core processes (Storage,
        Configuration Manager, and Process Manager) cannot be shut down with
        this method.

        The given process name is the one that is used as device name in the
        setup file and can also be found in the dictionary returned by the
        get_devices() method.

        Args:
            - process_name: Device name for which the Control Server should be
                            shut down.
        """

    @dynamic_interface
    def shut_down_egse(self):
        """Shut down all device Control Servers in the current setup.

        This method can only be used to shut down the Control Servers of the
        devices that are included in the current setup.  Core processes
        (Storage, Configuration Manager, and Process Manager) cannot be shut
        down with this method.
        """

        raise NotImplementedError

    @dynamic_interface
    def start_fitsgen(self):
        """ Start the FITS generation."""

        raise NotImplementedError

    @dynamic_interface
    def stop_fitsgen(self):
        """ Stop the FITS generation."""

        raise NotImplementedError

    @dynamic_interface
    def start_fov_hk(self):
        """ Start the generation of FOV HK."""

        raise NotImplementedError

    @dynamic_interface
    def stop_fov_hk(self):
        """ Stop the generation of FOV HK."""

        raise NotImplementedError

    @dynamic_interface
    def start_n_fee_hk(self):
        """ Start the generation of N-FEE HK."""

        raise NotImplementedError

    @dynamic_interface
    def stop_n_fee_hk(self):
        """ Stop the generation of N-FEE HK."""

        raise NotImplementedError


class ProcessManagerController(ProcessManagerInterface):

    """
    Controller for Process Management.
    """

    def __init__(self):
        """Initialisation for the Process Manager Controller.

        Bother the Configuration Manager and the Storage manager should be running.
        """

        # Keep track of the Configuration Manager

        self._configuration = ConfigurationManagerProxy()

        # Storage Manager must be active

        if not is_storage_manager_active():

            LOGGER.error("No Storage Manager available!!!!")

    def quit(self):

        self._configuration.disconnect_cs()

    def get_cm_proxy(self):
        """
        Returns the Proxy for Configuration Management.

        Returns:
            - Proxy for Configuration Management.
        """

        if not self._configuration.has_commands():
            self._configuration.load_commands()

        return self._configuration

    def get_devices(self):
        """Returns a dictionary with the device processes.

        The devices processes that are listed in this dictionary are the ones
        that are included in the current setup.

        The keys in the dictionary are taken from the "device_name" entries in
        the setup file. The corresponding values in the dictionary are taken
        from the "device" entries in the setup file (and should be Proxy classes).

        Returns:
            - Dictionary with the devices that are included in the setup.
        """

        try:

            setup = GlobalState.setup

            devices = {}
            devices = Setup.find_devices(setup, devices=devices)

            return devices

        except AttributeError:

            return {}

    def get_core(self):
        """Returns a dictionary with the core EGSE processes.

        The core EGSE processes are:

            - the Storage Manager,
            - the Configuration Manager,
            - the Process Manager,
            - and the Synoptics Manager.

        These processes should be running at all times, and can neither be
        started nor shut down from within the Process Manager.

        The keys in the dictionary are the names of the core processes.  The
        values are the Proxy classes.

        Returns:
            - Dictionary with the core EGSE processes.

        """

        storage_proxy_class = "class//egse.storage.StorageProxy"
        confman_proxy_class = "class//egse.confman.ConfigurationManagerProxy"
        procman_proxy_class = "class//egse.procman.ProcessManagerProxy"
        syn_proxy_class = "class//egse.synoptics.SynopticsManagerProxy"

        return {
            "Storage": (storage_proxy_class, ()),
            "Configuration Manager": (confman_proxy_class, ()),
            "Process Manager": (procman_proxy_class, ()),
            "Synoptics Manager": (syn_proxy_class, ()),
        }

    def start_egse(self):
        """Start all device Control Servers in the current setup in operational mode.

        This method can only be used to start the Control Servers of the
        devices that are included in the current setup.  Core processes
        (Storage, Configuration Manager, and Process Manager) cannot be
        started with this method.
        """

        LOGGER.debug("Starting EGSE")

        devices = self.get_devices()

        for process_name, process_info in devices.items():

            proxy_type = process_info[0]
            device_args = process_info[1]

            try:

                with find_class(proxy_type)(*device_args):

                    # The CS is already running

                    LOGGER.info(f"{process_name} was already running")

            except ConnectionError:

                try:

                    module_name = proxy_type[7:].rsplit(".", 1)[0]
                    module = importlib.import_module(module_name)

                    cs_type = module.DEVICE_SETTINGS.ControlServer

                    # Operational mode

                    if str.startswith(proxy_type, "class//egse.aeu.aeu.CRIO"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-crio-cs"])

                    elif str.startswith(proxy_type, "class//egse.aeu.aeu.PSU"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-psu-cs", str(device_args[0])])

                    elif str.startswith(proxy_type, "class//egse.aeu.aeu.AWG"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-awg-cs", str(device_args[0])])

                    else:
                        if len(device_args) == 0:
                            cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start"])
                        else:
                            cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start", str(device_args[0])])

                    LOGGER.info(f"Starting Control Server for {process_name} in operational mode")
                    cs.execute(detach_from_parent=True)

                    if process_name == "DAQ6510":
                        setup = GlobalState.setup
                        das_delay = setup.gse.DAQ6510.route.delay
                        das_count = setup.gse.DAQ6510.route.scan.COUNT.SCAN
                        das_interval = setup.gse.DAQ6510.route.scan.INTERVAL

                        das = SubProcess("MyApp", [sys.executable, "-m", "egse.das", "daq6510", "--count",
                                                   str(das_count), "--interval", str(das_interval), "--delay",
                                                   str(das_delay)])
                        das.execute(detach_from_parent="True")

                    # Check to see the CS actually started

                    time.sleep(5)
                    try:
                        with find_class(proxy_type)(*device_args):
                            pass
                    except ConnectionError:
                        LOGGER.warning(f"Could not start Control Server for {process_name}")

                except AttributeError:

                    LOGGER.debug(f"Cannot start Control Server for {process_name}")

        LOGGER.debug("EGSE started")

    def start_cs(self, process_name, sim_mode):
        """Start the device Control Server with the given process name.

        This method can only be used to start the Control Server of a device
        that is included in the current setup.  Core processes (Storage,
        Configuration Manager, and Process Manager) cannot be started with
        this method.

        The Control Server can either be started in simulator mode (without
        H/W controller available) or in operational mode (with H/W controller
        available).

        The given process name is the one that is used as device name in the
        setup file and can also be found in the dictionary returned by the
        get_devices() method.

        Args:
            - process_name: Device name for which the Control Server should be
                            started.
            - sim_mode: Whether or not to start the Control Server in
                        simulator mode.
        """

        LOGGER.debug(f"Starting {process_name}")

        process_info = self.get_devices()[process_name]
        proxy_type = process_info[0]
        device_args = process_info[1]

        try:

            with find_class(proxy_type)(*device_args):

                # The CS is already running

                message = f"{process_name} was already running"
                LOGGER.info(message)
                return Success(message)

        except ConnectionError:

            try:

                module_name = proxy_type[7:].rsplit(".", 1)[0]
                module = importlib.import_module(module_name)

                if hasattr(module, "DEVICE_SETTINGS") and hasattr(module.DEVICE_SETTINGS, "ControlServer"):
                    cs_type = module.DEVICE_SETTINGS.ControlServer
                else:
                    raise AttributeError(f"DEVICE_SETTINGS (or ControlServer therein) not defined in {module_name}")

                # Simulator mode

                if sim_mode:

                    mode = "simulator mode"

                    if str.startswith(proxy_type, "class//egse.aeu.aeu.CRIO"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-crio-cs", "--sim"])

                    elif str.startswith(proxy_type, "class//egse.aeu.aeu.PSU"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-psu-cs", str(device_args[0]), "--sim"])

                    elif str.startswith(proxy_type, "class//egse.aeu.aeu.AWG"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-awg-cs", str(device_args[0]), "--sim"])

                    else:

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start", "--sim"])

                # Operational mode

                else:

                    mode = "operational mode"

                    if str.startswith(proxy_type, "class//egse.aeu.aeu.CRIO"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-crio-cs"])

                    elif str.startswith(proxy_type, "class//egse.aeu.aeu.PSU"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-psu-cs", str(device_args[0])])

                    elif str.startswith(proxy_type, "class//egse.aeu.aeu.AWG"):

                        cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start-awg-cs", str(device_args[0])])

                    else:
                        if len(device_args) == 0:
                            cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start"])
                        else:
                            cs = SubProcess("MyApp", [sys.executable, "-m", cs_type, "start", str(device_args[0])])
                    # os.system(sys.executable + " -m " + cs_type + " start")

                LOGGER.info(f"Starting Control Server for {process_name} in {mode}")
                cs.execute(detach_from_parent=True)

                if process_name == "DAQ6510":
                    das = SubProcess("MyApp", [sys.executable, "-m", "egse.das", "daq6510"])
                    das.execute(detach_from_parent="True")

                # Check to see the CS actually started

                time.sleep(5)
                try:
                    with find_class(proxy_type)(*device_args):
                        return Success(f"{process_name} successfully started")
                except ConnectionError as exc:
                    message = f"Could not start Control Server for {process_name}"
                    LOGGER.warning(message, exc_info=True)
                    return Failure(message, cause=exc)

            except AttributeError as exc:
                message = f"Cannot start Control Server for {process_name}"
                LOGGER.error(message, exc_info=True)
                return Failure(message, cause=exc)

        # with find_class(proxy_type)(*device_args):
        #         pass

    def shut_down_egse(self):
        """Shut down all device Control Servers in the current setup.

        This method can only be used to shut down the Control Servers of the
        devices that are included in the current setup.  Core processes
        (Storage, Configuration Manager, and Process Manager) cannot be shut
        down with this method.
        """

        LOGGER.debug("Shutting down EGSE")

        devices = self.get_devices()

        for key, process_info in reversed(devices.items()):

            LOGGER.debug(f"Shutting down {key}")

            proxy_type = process_info[0]
            device_args = process_info[1]

            try:

                with find_class(proxy_type)(*device_args) as process_proxy:

                    with process_proxy.get_service_proxy() as service_proxy:

                        service_proxy.quit_server()

            except ConnectionError:

                pass

        LOGGER.debug("EGSE shut down")

    def shut_down_cs(self, process_name):
        """Shut down the device Control Server with the given process name.

        This method can only be used to shut down the Control Server of a
        device that is included in the current setup.  Core processes (Storage,
        Configuration Manager, and Process Manager) cannot be shut down with
        this method.

        The given process name is the one that is used as device name in the
        setup file and can also be found in the dictionary returned by the
        get_devices() method.

        Args:
            - process_name: Device name for which the Control Server should be
                            shut down.
        """

        LOGGER.debug(f"Shutting down {process_name}")

        try:

            process_info = self.get_devices()[process_name]
            proxy_type = process_info[0]
            device_args = process_info[1]

            with find_class(proxy_type)(*device_args) as process_proxy:

                with process_proxy.get_service_proxy() as service_proxy:

                    LOGGER.debug("Shutting down CS")

                    service_proxy.quit_server()

        except ConnectionError:

            # The CS is already down

            LOGGER.info(f"{process_name} was already down")

    def start_fitsgen(self):
        """ Start the FITS generation."""

        # TODO Think about potential conditions for the FITS generator to be started:
        #   - FITS generator should not be running yet
        #   - FEE simulator must be running?
        #   - DPU CS must be running?

        # Check whether the DPU CS is running

        if not is_dpu_cs_active():
            message = "The DPU Control Server must be running to be able to start the FITS generation."
            LOGGER.critical(message)
            return Failure(message)

        LOGGER.info("Starting the FITS generation")

        fg = SubProcess("MyApp", [sys.executable, "-m", "egse.dpu.fitsgen", "start"])
        fg.execute(detach_from_parent=True)

        time.sleep(5)
        if fitsgen.send_request("status").get("status") != "ACK":
            return Failure("FITS generation could not be started for some unknown reason.")

        return Success("FITS generation successfully started.")

    def stop_fitsgen(self):
        """ Stop the FITS generation."""

        LOGGER.info("Stopping the FITS generation")

        fg = SubProcess("MyApp", [sys.executable, "-m", "egse.dpu.fitsgen", "stop"])
        fg.execute(detach_from_parent=True)

    def start_fov_hk(self):
        """ Start the generation of FOV HK."""

        LOGGER.info("Starting the generation of FOV HK")

        fg = SubProcess("MyApp", [sys.executable, "-m", "egse.fov.fov_hk", "start"])
        fg.execute(detach_from_parent=True)

        time.sleep(5)
        if fov_hk.send_request("status").get("status") != "ACK":
            return Failure("FOV HK generation could not be started for some unknown reason.")

        return Success("FOV HK generation successfully started.")

    def stop_fov_hk(self):
        """ Stop the generation of FOV HK."""

        LOGGER.info("Stopping the generation of FOV HK")

        fg = SubProcess("MyApp", [sys.executable, "-m", "egse.fov.fov_hk", "stop"])
        fg.execute(detach_from_parent=True)

    def start_n_fee_hk(self):
        """ Start the generation of N-FEE HK."""

        LOGGER.info("Starting the generation of N-FEE HK")

        fg = SubProcess("MyApp", [sys.executable, "-m", "egse.fee.n_fee_hk", "start"])
        fg.execute(detach_from_parent=True)

        time.sleep(5)
        if n_fee_hk.send_request("status").get("status") != "ACK":
            return Failure("N-FEE HK generation could not be started for some unknown reason.")

        return Success("N-FEE HK generation successfully started.")

    def stop_n_fee_hk(self):
        """ Stop the generation of N-FEE HK."""

        LOGGER.info("Stopping the generation of N-FEE HK")

        fg = SubProcess("MyApp", [sys.executable, "-m", "egse.fee.n_fee_hk", "stop"])
        fg.execute(detach_from_parent=True)


class ProcessManagerProxy(Proxy, ProcessManagerInterface):

    """
    Proxy for Process Managements, used to connect to the Process Manager
    Control Server and send commands remotely.
    """

    def __init__(
        self,
        protocol=CTRL_SETTINGS.PROTOCOL,
        hostname=CTRL_SETTINGS.HOSTNAME,
        port=CTRL_SETTINGS.COMMANDING_PORT,
    ):
        """Initialisation of a new Proxy for Process Management.

        If no connection details (transport protocol, hostname, and port) are
        not provided, these are taken from the settings file.

        Args:
            - protocol: Transport protocol [default is taken from settings
                        file].
            - hostname: Location of the control server (IP address) [default
                        is taken from settings file].
            - port: TCP port on which the Control Server is listening for
                    commands [default is taken from settings file].
        """

        super().__init__(connect_address(protocol, hostname, port))
