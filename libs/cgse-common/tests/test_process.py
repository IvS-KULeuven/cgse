import logging
import pickle
import sys
import time

import zmq

from egse.config import find_file
from egse.process import SubProcess
from egse.process import get_process_info
from egse.process import is_process_running
from egse.process import list_processes

logger = logging.getLogger(__name__)

# TODO
#   * How can we test detached processes?


def test_is_process_running():

    # The empty_process.py should be located in the src/tests/scripts directory of the project

    stub = SubProcess("Stub Process", [sys.executable, str(find_file('empty_process.py').resolve())])
    stub.execute()

    time.sleep(0.1)  # allow process time to start/terminate

    list_processes(items=["python", "empty"])

    assert is_process_running(items=["python", "empty_process"])
    assert not is_process_running(items=["python", "Empty_process"], case_sensitive=True)  # command is lower case

    assert is_process_running(items=["python", "empty"], case_sensitive=True)

    assert is_process_running(items=["empty_process"])
    assert is_process_running(items="empty_process")

    assert not is_process_running(items=["_$123^_", "empty"])

    stub.quit()


def test_get_process_info():
    # The empty_process.py should be located in the src/tests/scripts directory of the project

    stub = SubProcess("Stub Process", [sys.executable, str(find_file('empty_process.py').resolve())])
    stub.execute()

    time.sleep(0.1)  # allow process time to start/terminate

    if len(get_process_info(["empty_process"])) > 1:
        logger.warning("Multiple process with 'empty_process' running.")

        # We would need this construct if multiple processes matching the criteria are running
        assert any(stub.pid == p['pid'] for p in get_process_info(["empty_process"]))
    else:
        assert get_process_info("empty_process")[0]['pid'] == stub.pid

    stub.quit()


def test_unknown_process():

    # The file unknown.exe does not exist and this will raise a FileNotFoundError which is caught in the execute()
    # method.
    process = SubProcess("Unknown App", ["unknown.exe"])

    assert process.execute()
    time.sleep(0.5)  # allow process time to terminate
    assert not process.is_running()
    assert process.returncode() is not None


def test_error_during_execute():

    # The __file__  exists, but is not executable and will therefore raise a PermissionError which is caught in the
    # `execute()` method.

    process = SubProcess("Stub Process", [__file__])

    assert process.execute()
    time.sleep(0.5)  # allow process time to terminate
    assert process.returncode() is not None
    assert not process.is_running()


def test_terminated_process():

    # Process void-0 exits with an exit code of 0

    process = SubProcess("Stub Procces", [sys.executable, str(find_file('void-0.py').resolve())])

    assert process.execute()
    time.sleep(0.5)  # allow process time to terminate
    assert not process.is_running()
    assert process.returncode() == 0

    # Process void-1 exits with an exit code of 1

    process = SubProcess("Stub Procces", [sys.executable, str(find_file('void-1.py').resolve())])

    assert process.execute()
    time.sleep(0.5)  # allow process time to terminate
    assert not process.is_running()
    assert process.returncode() == 1


def test_active_process():

    # The empty_process.py should be located in the src/tests/scripts directory of the project

    stub = SubProcess("Stub Process", [sys.executable, str(find_file('empty_process.py').resolve())])

    # We can set this cmd_port here because we know this from the empty_process.py file
    # In nominal situations, the cmd_port is known from the configuration file of the
    # system (because all processes are known) or communicated to the process manager
    # by the sub-process.

    cmd_port = 5556

    # Execute the sub-process.

    assert stub.execute()

    time.sleep(0.1)

    assert stub.is_running()
    assert is_active(cmd_port)  # check if the empty_process is active
    assert stub.returncode() is None

    status: str = get_status(cmd_port)
    logger.info(f"ProcessStatus: {status}")

    assert "PID" in status
    assert "UUID" in status
    assert "Up" in status

    time.sleep(1)

    logger.info(f"ProcessStatus: {get_status(cmd_port)}")

    assert stub.quit() == 0  # no processes running after quit()

    time.sleep(0.1)

    assert not stub.exists()
    assert not stub.is_running()
    assert not is_active(cmd_port)  # this method takes about 1 second because of the timeout (see send() below)
    assert stub.returncode() == 0


# Helper function to communicate with the empty_process.py

def is_active(port: int):
    """
    This check is to see if we get a response from the process with ZeroMQ.

    Returns:
        True if process responds to ZeroMQ requests.
    """
    return send(port, "Ping") == "Pong"


def get_status(port: int) -> str:
    """
    Returns status information of the running empty_process.

    Returns:
        ProcessStatus: status inormation on the running process.
    """
    return send(port, "Status?")


def send(port: int, command: str):
    """
    Sends a command to the sub-process and waits for a reply.

    The command is pickled before sending and the reply is also expected to be pickled.
    If no reply is received after 1 second, None is returned.

    Args:
        port (int): zeromq port where the command should be sent to
        command (str): the command to send to the sub-process

    Returns:
        The unpickled reply from the sub-process.
    """
    reply = None
    logger.info(f"Sending command {command} to {port}")

    pickle_string = pickle.dumps(command)

    with zmq.Context.instance().socket(zmq.REQ) as socket:
        socket.setsockopt(zmq.LINGER, 0)

        socket.connect(f"tcp://localhost:{port}")
        try:
            socket.send(pickle_string, zmq.DONTWAIT)

            if socket.poll(1000, zmq.POLLIN):
                pickle_string = socket.recv(zmq.DONTWAIT)
                reply = pickle.loads(pickle_string)

        except zmq.error as exc:
            logger.exception(f"Send failed with: {exc}")

    return reply
