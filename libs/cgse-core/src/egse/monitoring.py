from __future__ import annotations

import importlib
import multiprocessing
import pickle
import time
from typing import Callable
from typing import Tuple

import typer
import zmq
from zmq import ZMQError

from egse.control import ControlServer
from egse.log import logger
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.setup import load_setup
from egse.system import format_datetime
from egse.zmq_ser import MessageIdentifier
from egse.zmq_ser import bind_address


class MonitoringProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__(control_server)

    def get_bind_address(self):
        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_monitoring_port())

    def get_status(self):
        return {
            "timestamp": format_datetime(),
        }

    def send_status(self, status):
        self.send(status)

    def get_housekeeping(self) -> dict:
        return {
            "timestamp": format_datetime(),
        }


class Monitoring:
    """Context manager to monitor processes.

    Most control servers publish status information on their `MONITORING_PORT`.

    Parameters:
        endpoint: the endpoint to which the service will connect
        subscribe: subscription string, default is 'ALL'
        use_pickle: use pickle to process responses, currently always True
        callback: function that is called to process the response
        timeout: stop monitoring after timeout seconds
    """

    def __init__(
        self,
        endpoint: str,
        subscribe: Tuple[str] = None,
        use_pickle: bool = True,
        callback: Callable = None,
        timeout: float = None,  # in fractional seconds
    ):
        self._subscribe = subscribe or ["ALL"]
        self._endpoint = endpoint
        self._context = zmq.Context().instance()
        self._socket = None
        self._setup = None
        self._subscriptions = set()
        self._use_pickle = use_pickle
        self._callback = callback
        self._timeout = timeout
        self.return_code = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._socket.closed:
            self.disconnect()

    def connect(self):
        logger.debug(f"Connecting to {self._endpoint}")
        self._socket = self._context.socket(zmq.SUB)
        self._socket.connect(self._endpoint)

        # Get the high watermark value for the reception socket
        rcv_hwm = self._socket.getsockopt(zmq.RCVHWM)

        logger.debug(f"Receive High Water Mark: {rcv_hwm}")

        self._setup = load_setup()

        logger.debug(f"Using Setup {self._setup.get_id()}")

    def disconnect(self):
        logger.debug(f"Disconnecting from {self._endpoint}")
        self._socket.close(linger=0)
        self._subscriptions.clear()

    def unsubscribe_all(self):
        for sub in self._subscriptions:
            self._socket.unsubscribe(sub)
        self._subscriptions.clear()

    def unsubscribe(self, sync_id: int):
        subscribe_string = sync_id.to_bytes(1, byteorder="big") if sync_id else b""
        try:
            self._subscriptions.remove(subscribe_string)
            self._socket.unsubscribe(subscribe_string)
        except KeyError:
            logger.warning(f"Trying to unsubscribe a key that was not previously subscribed: {subscribe_string}")

    def subscribe(self, sync_id: int = None):
        subscribe_string = sync_id.to_bytes(1, byteorder="big") if sync_id else b""

        logger.debug(f"Subscribing {sync_id}")

        if subscribe_string in self._subscriptions:
            return

        self._socket.subscribe(subscribe_string)
        self._subscriptions.add(subscribe_string)

    def _clear_message_queue(self):
        # unsubscribing and subscribing again doesn't seem to work, so we close and re-open the socket.
        # Then we subscribe to restore the previous state.

        self._socket.close(linger=0)

        self._socket = self._context.socket(zmq.SUB)
        self._socket.connect(self._endpoint)

        for sub in self._subscriptions:
            self._socket.subscribe(sub)

    def handle_multi_part(self, message_id) -> Tuple[int, list]:
        message_parts = []
        message_id = int.from_bytes(message_id, byteorder="big")
        while True:
            message_parts.append(pickle.loads(self._socket.recv()))
            if not self._socket.getsockopt(zmq.RCVMORE):
                break

        return message_id, message_parts

    def handle_single_part(self, message) -> Tuple[int, list]:
        message_id = MessageIdentifier.ALL
        response = pickle.loads(message)

        return message_id, [response]

    def run(self):
        for item in self._subscribe or ["ALL"]:
            try:
                sync_id = MessageIdentifier[item.upper()]
            except KeyError:
                msg = f"incorrect subscribe identifier, use one of {[x.name for x in MessageIdentifier]}"
                logger.error(f"[red]ERROR: {msg}[/]")
                raise ValueError(msg)
            else:
                self.subscribe(sync_id)

        return self._monitoring_loop()

    def _monitoring_loop(self):
        start_time = time.monotonic()

        while True:
            try:
                message = self._socket.recv(zmq.NOBLOCK)
                more_parts = self._socket.getsockopt(zmq.RCVMORE)

                if more_parts:
                    sync_id, response = self.handle_multi_part(message)
                else:
                    sync_id, response = self.handle_single_part(message)

                start_time = time.monotonic()

                if self._callback:
                    rc = self._callback(sync_id, response, self._setup)
                    if isinstance(rc, (tuple, list)):
                        do_break, rc, *_ = rc  # discard any extra values
                    else:
                        do_break = rc
                    self.return_code = rc
                    if do_break:
                        break
                else:
                    logger.info(f"{MessageIdentifier(sync_id).name}, {response}")
            except ZMQError:
                if self._timeout and time.monotonic() - start_time > self._timeout:
                    self.return_code = None
                    break
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt caught!")
                break
            except pickle.UnpicklingError as exc:
                logger.error(f"UnpicklingError: {exc}")

        return self.return_code

    def resume(self, callback=None, clear_messages: bool = False):
        if clear_messages:
            self._clear_message_queue()
        if callback:
            self._callback = callback

        return self._monitoring_loop()

    def get_return_code(self):
        return self.return_code


PROCESS_NAMES = {
    "DATA_DUMP": ("DATA DUMPER", "MONITORING_PORT"),
    "DPU_PROCESSOR": ("DPU Processor", "MONITORING_PORT"),
    "DPU_PROCESSOR_HEARTBEAT": ("DPU Processor", "HEARTBEAT_PORT"),
    "DPU_CS": ("DPU Control Server", "MONITORING_PORT"),
    "CM_CS": ("Configuration Manager Control Server", "MONITORING_PORT"),
    "SM_CS": ("Storage Control Server", "MONITORING_PORT"),
    "PM_CS": ("Process Manager Control Server", "MONITORING_PORT"),
    "SYN_CS": ("Synoptics Manager Control Server", "MONITORING_PORT"),
    "DATA_DISTRIBUTION": ("DPU Processor", "DATA_DISTRIBUTION_PORT"),
}


def _determine_port(proc_name: str):
    """
    Determine the port number for the given process name. The process names are specific for this tool and defined
    in the PROCESS_NAMES dictionary.
    """
    name, port = PROCESS_NAMES.get(proc_name.upper(), (None, None))

    logger.info(f"{name = }, {port = }")

    if name is not None:
        ctrl_settings = Settings.load(name)
        port = ctrl_settings.get(port)

    return port


app = typer.Typer()


@app.command()
def monitoring(
    hostname: str,
    port: str,
    subscribe: Tuple[str] = None,
    use_pickle: bool = True,
    list_names: bool = False,
    callback: str = None,
):
    """
    Monitor the status of a control server on hostname:port.

    The port number shall correspond to the port number on which the control server is publishing
    status information.
    """

    multiprocessing.current_process().name = "Monitoring"

    from rich import print

    if list_names:
        print("The available process names as aliases for port numbers are: ", end="")
        print(", ".join(PROCESS_NAMES))
        return
    elif hostname is None or port is None:
        print("You will need to provide both the HOSTNAME and the PORT argument.")
        return

    logger.info(f"{type(hostname) = }, {hostname = }")
    logger.info(f"{type(port) = }, {port = }, {_determine_port(port) = }")

    try:
        port = int(port)
    except ValueError:
        port = _determine_port(port_name := port)
        if port is None:
            print(
                f"[red]ERROR[/]: Couldn't determine port number from {port_name}, "
                f"use the '--list-names' flag to see available names."
            )
            return

    if callback is not None:
        callback_module = importlib.import_module("egse.monitoring")
        callback = getattr(callback_module, callback, None)

    with Monitoring(f"tcp://{hostname}:{port}", subscribe=subscribe, use_pickle=use_pickle, callback=callback) as moni:
        moni.run()


if __name__ == "__main__":
    app()
