import sys

from egse.log import egse_logger
from egse.registry.client import RegistryClient
from egse.settings import Settings
import zmq
import pickle
from egse.ariel.facility.database import DatabaseTableWatcher
import typer
import rich

from egse.system import get_host_ip
from egse.zmq_ser import connect_address, get_port_number, bind_address

LOGGER = egse_logger
CTRL_SETTINGS = Settings.load("Facility HK")

TIMEOUT_RECV = 1.0  # seconds
ORIGIN_LIST = {"TCU": "TCU_TABLE", "LAKESHORE": "LAKESHORE_TABLE"}


class FacilityHousekeepingExporter:
    def __init__(self):
        self.watchers = {}

        # Define a watcher for the tables listed in the settings

        for origin in CTRL_SETTINGS.TABLES:
            table_name, server_id = CTRL_SETTINGS.TABLES[origin]
            self.watchers[origin] = DatabaseTableWatcher(origin, table_name, server_id)

        self.keep_extracting = True
        print(f"Keep extracting: {self.keep_extracting}")

        # Create ZeroMQ socket for commanding

        self.zmq_context = zmq.Context.instance()
        self.cmd_socket = self.zmq_context.socket(zmq.REP)
        endpoint = bind_address(CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.COMMANDING_PORT)
        self.cmd_socket.bind(endpoint)  # Bind the socket to the endpoint -> port allocation happens here

        # Registration to the registry client

        self.registry = RegistryClient()
        self.registry.connect()

        self.register_service()

    def run(self):
        """Starts watching for changes in the specified tables in the facility database."""

        watcher: DatabaseTableWatcher

        poller = zmq.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)

        # Start watching the tables

        for _, watcher in self.watchers.items():
            watcher.start_watching_db_table()

        try:
            while self.keep_extracting:
                print("Keep extracting")

                # Keep on listening for `quit` command
                if _check_commander_status(self.cmd_socket, poller):
                    self.keep_extracting = False
                    break

        except KeyboardInterrupt:
            LOGGER.info("KeyboardInterrupt caught")

        self.keep_extracting = False

        # De-registration from the registry client

        self.deregister_service()

        # Close the commanding socket

        poller.unregister(self.cmd_socket)
        self.cmd_socket.close(linger=0)

        # Stop watching the tables listed in the settings

        for _, watcher in self.watchers.items():
            watcher.stop_watching_db_table()

    def register_service(self) -> None:
        """Registers the FacilityHousekeepingExporter to the Registry Client."""

        self.registry.stop_heartbeat()
        self.registry.register(
            name=CTRL_SETTINGS.SERVICE_NAME.lower(),
            host=get_host_ip() or "127.0.0.1",
            port=get_port_number(self.cmd_socket),
            service_type=CTRL_SETTINGS.SERVICE_TYPE.lower(),
        )
        self.registry.start_heartbeat()

    def deregister_service(self):
        """De-registers the FacilityHousekeepingExporter from the Registry Client."""

        if self.registry:
            self.registry.stop_heartbeat()
            self.registry.deregister()
            self.registry.close()


def _check_commander_status(commander, poller: zmq.Poller) -> bool:
    """Checks the status of the commander.

    Checks whether a command has been received by the given commander.

    Args:
        commander: Commanding socket for the FOV HK generation.
        poller (zmq.Poller): Poller for the FOV HK generation.

    Returns: True if a quit command was received; False otherwise.
    """

    socks = dict(poller.poll(timeout=5000))  # Timeout of 5s

    if commander in socks:
        pickle_string = commander.recv()
        command = pickle.loads(pickle_string)

        if command.lower() == "quit":
            commander.send(pickle.dumps("ACK"))
            return True

        if command.lower() == "status":
            response = dict(status="ACK", host=CTRL_SETTINGS.HOSTNAME, command_port=CTRL_SETTINGS.COMMANDING_PORT)
            commander.send(pickle.dumps(response))

        return False

    return False


def send_request(command_request: str):
    """Sends a request to the FacilityHousekeepingExporter process and wait for a response.

    Args:
        command_request (str): Request.

    Returns: Response to the request.
    """

    with RegistryClient() as registry:
        service = registry.discover_service(CTRL_SETTINGS.SERVICE_TYPE.lower())

        if service:
            protocol = service.get("protocol", "tcp")
            hostname = service["host"]
            port = service["port"]
            endpoint = connect_address(protocol, hostname, port)

            ctx = zmq.Context().instance()
            socket = ctx.socket(zmq.REQ)
            socket.connect(endpoint)

            socket.send(pickle.dumps(command_request))
            rlist, _, _ = zmq.select([socket], [], [], timeout=TIMEOUT_RECV)

            if socket in rlist:
                response = socket.recv()
                response = pickle.loads(response)
            else:
                response = {"error": "Receive from ZeroMQ socket timed out for FacilityHousekeepingExporter."}
            socket.close(linger=0)

            return response

        else:
            return None


app = typer.Typer()


@app.command()
def start():
    """Starts the FacilityHousekeepingExporter."""

    try:
        rich.print("Starting the FacilityHousekeepingExporter")
        FacilityHousekeepingExporter().run()
    except KeyboardInterrupt:
        print("Shutdown requested... exiting")
    except SystemExit as exc:
        exit_code = exc.code if hasattr(exc, "code") else 0
        print(f"System Exit with code {exit_code}")
        sys.exit(exit_code)
    except Exception as exc:
        LOGGER.exception(f"Cannot start FacilityHousekeepingExporter: {exc}")


@app.command()
def stop():
    """Stops the FacilityHousekeepingExporter."""

    response = send_request("quit")

    if response == "ACK":
        rich.print("FacilityHousekeepingExporter successfully terminated.")
    else:
        rich.print(f"[red] ERROR: {response}")


@app.command()
def status():
    """Prints the status of the FacilityHousekeepingExporter."""

    rich.print("FacilityHousekeepingExporter:")

    response = send_request("status")

    if response and response.get("status") == "ACK":
        rich.print("  Status: [green]active")
        rich.print(f"  Hostname: {response.get('host')}")
        rich.print(f"  Commanding port: {response.get('command_port')}")
    else:
        rich.print("  Status: [red]not active")

    with RegistryClient() as registry:
        registry.list_services()


if __name__ == "__main__":
    import logging

    from egse.logger import set_all_logger_levels

    set_all_logger_levels(logging.DEBUG)

    sys.exit(app())
