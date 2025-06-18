import logging
import time

from egse.signal import FileBasedSignaling
from egse.signal import create_signal_command_file

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("egse.test_signal")


def test_reregister():
    service_id = "SIGNAL-TEST"

    signaling = FileBasedSignaling(service_id)
    signaling.start_monitoring()

    create_signal_command_file(signaling.signal_dir, service_id, {"action": "reregister", "params": {"x": 42, "y": 23}})

    running = True

    def stop():
        nonlocal running

        logger.warning("Request to terminate the test.")

        running = False

    signaling.register_handler("stop", stop)

    count = 10

    while running:
        signaling.process_pending_commands()
        time.sleep(0.1)
        if count == 0:
            # This will be called after 10 seconds and end the test
            create_signal_command_file(signaling.signal_dir, service_id, {"action": "stop"})
        count -= 1

    signaling.stop()
