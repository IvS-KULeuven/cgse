import random
from pathlib import Path

from egse.control import ControlServer
from egse.procman import ProcessManagerController, ProcessManagerCommand
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

HERE = Path(__file__).parent

CTRL_SETTINGS = Settings.load("Process Manager Control Server")
COMMAND_SETTINGS = Settings.load(location=HERE, filename="procman.yaml")


class ProcessManagerProtocol(CommandProtocol):
    """
    Command Protocol for Process Management.
    """

    def __init__(self, control_server: ControlServer):
        """Initialisation of a new Protocol for Process Management.

        The initialisation of this Protocol consists of the following steps:

            - Create a Controller to which the given Control Server should send commands;
            - Load the commands;
            - Build a look-up table for the commands.

        Args:
            - control_server (ControlServer): Control Server via which commands should be sent to the Controller
        """

        super().__init__(control_server)

        # Create a new Controller for Process Management

        self.controller = ProcessManagerController()

        # Load the commands (for commanding of the PM Controller) from the
        # YAML file into a dictionary, stored in the PM Protocol

        self.load_commands(COMMAND_SETTINGS.Commands, ProcessManagerCommand, ProcessManagerController)

        # Build a look-up table for the methods

        self.build_device_method_lookup_table(self.controller)

    def get_bind_address(self):
        """Returns the address to bind a socket to.

        This bind address is a properly formatted URL, based on the communication protocol and the commanding port.

        Returns: Properly formatted URL to bind a socket to.
        """

        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_commanding_port())

    def get_status(self) -> dict:
        """Returns the status information for the Control Server.

        This status information is returned in the form of a dictionary that contains the following information about
        the Control Server for Process Management:

            - timestamp (str): string representation of the current datetime;
            - PID (int): process ID for the Control Server;
            - Up (float): uptime of the Control Server [s];
            - UUID (uuid1): Universally Unique Identifier for the Control Server;
            - RSS (int): 'Resident Set Size', this is the non-swapped physical memory a process has used [byte];
            - USS (int): 'Unique Set Size', this is the memory which is unique to a process [byte];
            - CPU User (float): time spent in user mode [s];
            - CPU System (float): time spent in kernel mode [s];
            - CPU count: number of CPU cores in use by the process;
            - CPU% (float): process CPU utilization as a percentage [%].

        Returns: Dictionary with status information for the Control Server for Process Management.
        """

        return super().get_status()

    def get_housekeeping(self) -> dict:
        """Returns the housekeeping data for the Control Server.

        This housekeeping data is returns in the form of a dictionary that contains the following information about
        the Control Server for Process Management:

            - timestamp (str): string representation of the current datetime.

        Returns: Dictionary with housekeeping data for the Control Server for Process Management.
        """

        return {
            "timestamp": format_datetime(),
            "random": random.randint(0, 100),
        }
