"""
The Process Manager Control Server is the service that handles all Common-EGSE
processes.  The list of processes to handle, is taken from the Configuration
Manager (from the setup).

The Process Manager Control Server is implemented as a standard control server.
"""

import logging
import multiprocessing

import rich
import sys
import typer
import zmq

from egse.confman import ConfigurationManagerProxy
from egse.control import ControlServer
from egse.listener import EVENT_ID
from egse.process import SubProcess
from egse.procman import ProcessManagerProxy, LOGGER
from egse.procman.procman_protocol import ProcessManagerProtocol
from egse.settings import Settings
from egse.storage import store_housekeeping_information


CTRL_SETTINGS = Settings.load("Process Manager Control Server")


class ProcessManagerControlServer(ControlServer):

    def __init__(self):

        super().__init__()

        self.device_protocol = ProcessManagerProtocol(self)

        LOGGER.debug(f"Binding ZeroMQ socket to {self.device_protocol.get_bind_address()}")

        self.register_as_listener(
            proxy=ConfigurationManagerProxy,
            listener={'name': 'Process Manager CS', 'proxy': ProcessManagerProxy, 'event_id': EVENT_ID.SETUP}
        )
        self.device_protocol.bind(self.dev_ctrl_cmd_sock)

        self.poller.register(self.dev_ctrl_cmd_sock, zmq.POLLIN)

        self.set_hk_delay(10.0)

        LOGGER.info(f"PM housekeeping saved every {self.hk_delay / 1000:.1f} seconds.")

    def get_communication_protocol(self):

        return CTRL_SETTINGS.PROTOCOL

    def get_commanding_port(self):

        return CTRL_SETTINGS.COMMANDING_PORT

    def get_service_port(self):

        return CTRL_SETTINGS.SERVICE_PORT

    def get_monitoring_port(self):

        return CTRL_SETTINGS.MONITORING_PORT

    def get_storage_mnemonic(self):

        try:
            return CTRL_SETTINGS.STORAGE_MNEMONIC
        except AttributeError:
            return "PM"

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
            }
        )

    def unregister_from_storage_manager(self):

        from egse.storage import unregister_from_storage_manager
        unregister_from_storage_manager(origin=self.get_storage_mnemonic())

    def after_serve(self):

        from egse.confman import ConfigurationManagerProxy
        self.unregister_as_listener(proxy=ConfigurationManagerProxy, listener={'name': 'Process Manager CS'})


app = typer.Typer(name="pm_cs", no_args_is_help=True)


@app.command()
def start():
    """ Starts the Process Manager (pm_cs).

    The pm_cs is normally started automatically on egse-server boot.
    """

    multiprocessing.current_process().name = "pm_cs"

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
    """ Starts the Process Manager Control Server in the background."""

    proc = SubProcess("pm_cs", ["pm_cs", "start"])
    proc.execute()


@app.command()
def stop():
    """ Sends a 'quit_server' command to the Process Manager."""

    try:
        with ProcessManagerProxy() as pm:
            sp = pm.get_service_proxy()
            sp.quit_server()
    except ConnectionError:
        rich.print("[red]ERROR: Couldn't connect to the process manager.[/]")


@app.command()
def status():
    """ Prints the status of the control server."""

    import rich
    from egse.procman import get_status

    rich.print(get_status(), end='')


if __name__ == "__main__":

    sys.exit(app())
