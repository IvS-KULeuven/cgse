"""
The Process Manager Control Server is the service that handles all Common-EGSE
processes.  The list of processes to handle, is taken from the Configuration
Manager (from the setup).

The Process Manager Control Server is implemented as a standard control server.
"""

import multiprocessing
import sys

import rich
import typer
import zmq
from rich.console import Console

from egse.control import ControlServer
from egse.log import logging
from egse.logger import remote_logging
from egse.process import SubProcess
from egse.procman.procman_protocol import ProcessManagerProtocol
from egse.registry.client import RegistryClient
from egse.services import ServiceProxy
from egse.procman import (
    PROCESS_NAME,
    SERVICE_TYPE,
    PROTOCOL,
    COMMANDING_PORT,
    SERVICE_PORT,
    MONITORING_PORT,
    HOSTNAME,
    STORAGE_MNEMONIC,
)
from egse.storage import store_housekeeping_information
from egse.zmq_ser import get_port_number

# Use explicit name here otherwise the logger will probably be called __main__

logger = logging.getLogger("egse.procman")


class ProcessManagerControlServer(ControlServer):
    def __init__(self):
        super().__init__()

        multiprocessing.current_process().name = PROCESS_NAME

        self.logger = logger
        self.service_name = PROCESS_NAME
        self.service_type = SERVICE_TYPE

        self.device_protocol = ProcessManagerProtocol(self)

        self.logger.debug(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.register_service(service_type=SERVICE_TYPE)

        self.set_hk_delay(10.0)

        self.logger.info(f"PM housekeeping saved every {self.hk_delay / 1000:.1f} seconds.")

    def get_communication_protocol(self):
        return PROTOCOL

    def get_commanding_port(self):
        return get_port_number(self.dev_ctrl_cmd_sock) or COMMANDING_PORT

    def get_service_port(self):
        return get_port_number(self.dev_ctrl_service_sock) or SERVICE_PORT

    def get_monitoring_port(self):
        return get_port_number(self.dev_ctrl_mon_sock) or MONITORING_PORT

    def get_storage_mnemonic(self):
        return STORAGE_MNEMONIC

    def is_storage_manager_active(self):
        from egse.storage import is_storage_manager_active

        return is_storage_manager_active()

    def store_housekeeping_information(self, data):
        origin = self.get_storage_mnemonic()
        store_housekeeping_information(origin, data)

    def register_to_storage_manager(self):
        from egse.storage import register_to_storage_manager
        from egse.storage.persistence import TYPES

        register_to_storage_manager(
            origin=self.get_storage_mnemonic(),
            persistence_class=TYPES["CSV"],
            prep={
                "column_names": list(self.device_protocol.get_housekeeping().keys()),
                "mode": "a",
            },
        )

    def unregister_from_storage_manager(self):
        from egse.storage import unregister_from_storage_manager

        unregister_from_storage_manager(origin=self.get_storage_mnemonic())

    def after_serve(self):
        self.deregister_service()


app = typer.Typer(name=PROCESS_NAME)

console = Console(width=120)


@app.command()
def start():
    """Starts the Process Manager (pm_cs).

    The pm_cs is normally started automatically on egse-server boot.
    """

    multiprocessing.current_process().name = PROCESS_NAME

    with remote_logging():
        try:
            control_server = ProcessManagerControlServer()
            control_server.serve()
        except KeyboardInterrupt:
            print("Shutdown requested...exiting")
        except SystemExit as exit_code:
            print(f"System Exit with code {exit_code}.")
            sys.exit(exit_code.code)
        except Exception:
            import traceback

            traceback.print_exc(file=sys.stdout)

    return 0


@app.command()
def start_bg():
    """Starts the Process Manager Control Server in the background."""

    proc = SubProcess("pm_cs", ["pm_cs", "start"])
    proc.execute()


@app.command()
def stop():
    """Sends a 'quit_server' command to the Process Manager."""

    if COMMANDING_PORT == 0:
        with RegistryClient() as reg:
            service = reg.discover_service(settings.SERVICE_TYPE)
            rich.print("service = ", service)
            if service:
                hostname = service["host"]
                port = service["metadata"]["service_port"]
            else:
                rich.print(
                    "[red]ERROR: Couldn't determine how to connect to the process manager. No service defined.[/]"
                )
                return
    else:
        hostname = HOSTNAME
        port = SERVICE_PORT

    rich.print("[green]Sending 'quit' command to process manager..[/]")
    try:
        with ServiceProxy(hostname=hostname, port=port) as proxy:
            proxy.quit_server()
    except ConnectionError as exc:
        console.print(f"[red]ERROR: Couldn't connect to process manager: {exc}[/]")


@app.command()
def status():
    """Prints the status of the control server."""

    import rich
    from egse.procman import get_status

    rich.print(get_status(), end="")


if __name__ == "__main__":
    sys.exit(app())
