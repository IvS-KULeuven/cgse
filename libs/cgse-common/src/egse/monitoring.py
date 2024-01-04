import logging
import multiprocessing
import pickle

import click
import rich
import zmq

from egse.control import ControlServer
from egse.protocol import CommandProtocol
from egse.system import format_datetime
from egse.zmq_ser import MessageIdentifier
from egse.zmq_ser import bind_address

logger = logging.getLogger("egse.monitoring")

class MonitoringProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

    def get_bind_address(self):
        return bind_address(self.control_server.get_communication_protocol(), self.control_server.get_monitoring_port())

    def get_status(self):
        return {
            'timestamp': format_datetime(),
        }

    def send_status(self, status):
        self.send(status)

    def get_housekeeping(self) -> dict:
        return {
            'timestamp': format_datetime(),
        }



@click.command()
@click.argument('hostname')
@click.argument('port')
@click.option('--subscribe', '-s', default=('ALL',), multiple=True,
              help="subscribe to a sync identifier, can appear multiple times")
@click.option('--multipart', '-m', is_flag=True, default=False, help="use multipart messages")
@click.option('--pickle/--no-pickle', 'use_pickle', default=True)
def monitoring(hostname: str, port: int, subscribe: str, multipart: bool, use_pickle: bool):
    """Monitor the status of a control server on hostname:port.

    The port number shall correspond to the port number on which the control server is publishing
    status information.
    """
    context = zmq.Context()

    receiver = context.socket(zmq.SUB)
    receiver.connect(f"tcp://{hostname}:{port}")

    for item in subscribe:
        sync_id = 0
        try:
            sync_id = MessageIdentifier[item.upper()]
        except KeyError:
            rich.print(f"[red]ERROR: incorrect subscribe identifier, "
                       f"use one of {[x.name for x in MessageIdentifier]}")
            ctx = click.get_current_context()
            rich.print(ctx.get_help())
            ctx.exit()

        if sync_id == MessageIdentifier.ALL:
            subscribe_string = b''
        else:
            subscribe_string = sync_id.to_bytes(1, byteorder='big')

        receiver.subscribe(subscribe_string)

    while True:
        try:
            if multipart:
                sync_id, message = receiver.recv_multipart()
                sync_id = int.from_bytes(sync_id, byteorder='big')
            else:
                sync_id = MessageIdentifier.ALL
                message = receiver.recv()
            response = pickle.loads(message) if use_pickle else message
            rich.print(f"{MessageIdentifier(sync_id).name}, {response}", flush=True)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt caught!")
            break

    receiver.close(linger=0)
    context.term()


if __name__ == "__main__":
    multiprocessing.current_process().name = "Monitoring"
    monitoring()
