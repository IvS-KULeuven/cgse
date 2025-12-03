from typing import Any

import sys

from egse.hk import read_conversion_dict
from egse.log import egse_logger
from egse.registry.client import RegistryClient
from egse.settings import Settings
import zmq
import pickle
from egse.ariel.facility.database import DatabaseTableWatcher
import typer
import rich

from egse.setup import load_setup
from egse.storage import register_to_storage_manager, TYPES, is_storage_manager_active, StorageProxy
from egse.system import get_host_ip
from egse.zmq_ser import connect_address, get_port_number, bind_address

LOGGER = egse_logger
CTRL_SETTINGS = Settings.load("Facility HK")

TIMEOUT_RECV = 1.0  # seconds
ORIGIN_LIST = {"TCU": "TCU_TABLE", "LAKESHORE": "LAKESHORE_TABLE"}


class FacilityHousekeepingExporter:
    def __init__(self):
        """Initialisation of a facility HK exporter.

        This process will extract HK from the facility database, store it in TA-EGSE-consistent CSV files and ingest it
        into the metrics database.

        Upon initialisation, the following actions are performed:

            - From the settings file, we read which tables in the facility database have to be watched for new entries
              (one table per sensor).  In this file, we also configure which is the corresponding storage mnemonic that
              will be used by the Storage Manager.
            - For each selected table, a dedicated watcher is defined.  It is the task of the watcher to keep an eye
              on its database table, extract new entries, pass them to the Storage Manager (with the corresponding
              storage mnemonics), and ingest it into the metrics database.
            - Register the process to the registry client.  This way we can find back its host and ports (which is
              required when using dynamic port allocation), and report its status.
            - We will probably store the data from multiple sensors in the same file.  We therefore need to pass on to
              the Storage Manager which origin will receives and store which column names.  If we don't do this, we end
              up with corrupt CSV files.
        """

        self.watchers = {}

        # Define a watcher for the tables listed in the settings
        # Keep track of all (unique) storage mnemonics / origins (to collect the corresponding column names)

        self.origins = []

        for table_name in CTRL_SETTINGS.TABLES:
            origin, server_id = CTRL_SETTINGS.TABLES[table_name]
            self.origins.append(origin)
            self.watchers[table_name] = DatabaseTableWatcher(table_name, origin, server_id)

        self.origins = list(set(self.origins))  # Remove duplicates

        self.keep_extracting = True
        print(f"Keep extracting: {self.keep_extracting}")

        # Create ZeroMQ socket for commanding

        self.zmq_context = zmq.Context.instance()
        self.cmd_socket = self.zmq_context.socket(zmq.REP)
        endpoint = bind_address(CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.COMMANDING_PORT)
        self.cmd_socket.bind(endpoint)  # Bind the socket to the endpoint -> Port allocation happens here

        # Registration to the registry client

        self.registry = RegistryClient()
        self.registry.connect()
        self.register_service()

        # Register to the Storage Manager (pass the columns names for each storage mnemonic)

        self.register_to_storage_manager()

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

        # De-registration from the Storage Manager

        self.unregister_from_storage_manager()

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

    def deregister_service(self) -> None:
        """De-registers the FacilityHousekeepingExporter from the Registry Client."""

        if self.registry:
            self.registry.stop_heartbeat()
            self.registry.deregister()
            self.registry.close()

    @staticmethod
    def register_to_storage_manager() -> None:
        """Registers the origins to the Storage Manager.

        Each sensor has its own table in the facility database.  In the TA-EGSE framework, we want to offer the option
        to store data from multiple sensors in the same file.  Therefore we must register - for each storage
        mnemonic - which are all the possible column names.  Note that the column names in the CSV files do not
        necessarily correspond to the table names in the facility database.  This is configured in the telemetry
        dictionary.
        """

        if is_storage_manager_active():
            storage_registrations = {}

            # Data from which table in the facility database should be extracted and stored under which storage mnemonic?

            for table_name, (origin, _) in CTRL_SETTINGS.TABLES.items():
                storage_registrations.setdefault(origin, []).append(table_name)

            # The column names in the CSV files do not necessarily correspond to the table names in the facility
            # database.  This is configured in the telemetry dictionary.

            for origin, table_names in storage_registrations.items():
                hk_conversion_dict = read_conversion_dict(origin, use_site=False, setup=load_setup())
                column_names = [hk_conversion_dict[table_name] for table_name in table_names]

                # Make sure there is also a column (the first one) for the timestamp

                column_names = ["timestamp"] + column_names

                register_to_storage_manager(
                    origin=origin,
                    persistence_class=TYPES["CSV"],
                    prep={
                        "column_names": column_names,
                        "mode": "a",
                    },
                )
        else:
            LOGGER.warning("The Storage Manager is not active")
            raise

    def unregister_from_storage_manager(self) -> None:
        """De-registers all storage mnemonics for the facility database from the Storage Manager."""

        if is_storage_manager_active():
            try:
                with StorageProxy() as proxy:
                    for origin in self.origins:
                        response = proxy.unregister({"origin": origin})
                        if not response.successful:
                            LOGGER.warning(f"Couldn't unregister {origin} from the Storage Manager: {response}")
                        else:
                            LOGGER.info(response)
            except ConnectionError as exc:
                LOGGER.warning(f"Couldn't connect to the Storage Manager for de-registration: {exc}")
                raise
        else:
            LOGGER.warning("The Storage Manager is not active")
            raise


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


def send_request(command_request: str) -> Any:
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
def start() -> None:
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
def stop() -> None:
    """Stops the FacilityHousekeepingExporter."""

    response = send_request("quit")

    if response == "ACK":
        rich.print("FacilityHousekeepingExporter successfully terminated.")
    else:
        rich.print(f"[red] ERROR: {response}")


@app.command()
def status() -> None:
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
