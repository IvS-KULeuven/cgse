"""
This process doesn't do anything and serves as a skeleton for testing sub-processes.

This process listens on port 5556 for ZeroMQ messages (using the REQ-REP protocol)
and understands the following commands:

* Ping: returns "Pong" as an answer
* Quit: returns "Quiting" as an answer
* Status?: returns status information of the SubProcess

"""

import logging
import pickle
import sys
import time

import zmq

from egse.process import ProcessStatus

logger = logging.getLogger("egse.tests")

PORT = 5556


def main():
    status = ProcessStatus()

    context = zmq.Context.instance()

    process_socket: zmq.Socket = context.socket(zmq.REP)
    process_socket.bind(f"tcp://*:{PORT}")

    while True:
        #  Wait for next request from client
        try:
            message = pickle.loads(process_socket.recv())
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt, terminating...")
            break

        logger.info(f"Received request: {message}")

        #  Send reply back to client

        if message == "Ping":
            process_socket.send(pickle.dumps("Pong"))
        if message == "Quit":
            process_socket.send(pickle.dumps("Quiting"))
            break
        if message == "Status?":
            status.update()
            process_socket.send(pickle.dumps(str(status)))

        #  Do some 'work'
        time.sleep(0.1)

    process_socket.close(linger=0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    sys.exit(main())
