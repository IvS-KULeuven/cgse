from __future__ import annotations

import contextlib
import pickle
import queue
import random
import threading
import time

import zmq

from egse.system import format_datetime
from egse.zmq_ser import MessageIdentifier


def _g_tick(period: float):
    """Generator for ticks every period [s]."""
    next_time = time.monotonic()
    while True:
        next_time += period
        yield max(next_time - time.monotonic(), 0)


class HeartbeatBroadcaster(threading.Thread):
    """
    Sends a heartbeat signal to the endpoint using a PUB-SUB protocol.

    The heartbeat message is sent by default every second, but that can be changed
    by the `period` argument (which is in fractional seconds).

    Since the broadcaster runs in a thread, it is not a full prove method that the parent process is still running.
    Therefore, the parent process can set a custom messages on the queue. That custom message will be broadcast at
    the same time as the next heartbeat, which is probably not the time that the custom message was set. Keep that
    in mind.
    """

    def __init__(self, period: float = 1.0, endpoint: str = "tcp://*:5555"):
        super().__init__()
        self._period = period
        self._endpoint = endpoint
        self._socket: zmq.Socket | None = None
        self._running = False
        self._canceled = threading.Event()
        self._queue = queue.Queue()
        self._heartbeat_id = MessageIdentifier.HEARTBEAT.to_bytes(1, byteorder="big")
        self._custom_id = MessageIdentifier.CUSTOM.to_bytes(1, byteorder="big")

    def run(self):
        ctx = zmq.Context.instance()
        self._socket = ctx.socket(zmq.PUB)
        self._socket.bind(self._endpoint)
        self._running = True

        g = _g_tick(self._period)
        while True:
            if self._canceled.is_set():
                break
            time.sleep(next(g))
            self.send_heartbeat()
            self.send_custom_message()

    def send_heartbeat(self):
        timestamp = format_datetime()
        self._socket.send_multipart([self._heartbeat_id, pickle.dumps(f"Heartbeat – {timestamp}")])

    def send_custom_message(self):
        with contextlib.suppress(queue.Empty):
            message = self._queue.get_nowait()
            self._socket.send_multipart([self._custom_id, pickle.dumps(message)])

    def set_message(self, message: str):
        self._queue.put_nowait(message)

    def cancel(self) -> None:
        self._canceled.set()


if __name__ == "__main__":
    broadcaster = HeartbeatBroadcaster()
    broadcaster.start()

    # You will see that the timestamp of this custom message is drifting because
    # we do not take the execution time of the `set_message()` etc. intyo accout.
    # In the actual HeartbeatBroadcaster above, we do take that into account.

    try:
        while True:
            broadcaster.set_message(f"Custom message – {format_datetime()}")
            time.sleep(1.0 * random.choice([1, 2, 3, 4]))
    except KeyboardInterrupt:
        broadcaster.cancel()
