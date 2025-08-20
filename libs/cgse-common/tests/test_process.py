import logging
import os
import pickle
import sys
import time
import types
from pathlib import Path

import zmq

from egse.config import find_file
from egse.process import ProcessStatus
from egse.process import SubProcess
from egse.process import get_process_info
from egse.process import is_process_running
from egse.process import list_processes
from egse.process import list_zombies
from egse.process import ps_egrep
from egse.system import capture_rich_output

logger = logging.getLogger("egse.test.process")

HERE = Path(__file__).parent

# TODO
#   * How can we test detached processes?


def create_zombie():
    pid = os.fork()

    if pid == 0:  # Child process
        # Child immediately exits
        os._exit(0)  # noqa

    # Parent process continues

    print(f"Zombie child process created using 'fork' with PID: {pid}")

    return pid


def test_zombie():
    zombie_pid = create_zombie()

    zombies = list_zombies()
    print(f"{zombies = }")

    assert any([True for x in zombies if x["pid"] == zombie_pid])

    create_zombie()

    zombies = list_zombies()
    print(f"{zombies = }")

    assert len(list_zombies()) >= 2


def test_is_process_running():
    # The empty_process.py should be located in the src/tests/scripts directory of the project

    stub = SubProcess("Stub Process", [sys.executable, str(find_file("empty_process.py", root=HERE).resolve())])
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

    stub = SubProcess("Stub Process", [sys.executable, str(find_file("empty_process.py", root=HERE).resolve())])
    stub.execute()

    time.sleep(0.1)  # allow process time to start/terminate

    if len(get_process_info(["empty_process"])) > 1:
        logger.warning("Multiple process with 'empty_process' running.")

        # We would need this construct if multiple processes matching the criteria are running
        assert any(stub.pid == p["pid"] for p in get_process_info(["empty_process"]))
    else:
        assert get_process_info("empty_process")[0]["pid"] == stub.pid

    stub.quit()


def test_unknown_process():
    # The file unknown.exe does not exist and this will raise a FileNotFoundError which is caught in the execute()
    # method.
    process = SubProcess("Unknown App", ["unknown.exe"])

    assert not process.execute()
    time.sleep(0.5)  # allow process time to terminate
    logger.info(f"{process.exc_info = }")
    assert not process.is_running()
    assert process.returncode() is None


def test_error_during_execute():
    # The __file__  exists, but is not executable and will therefore raise a PermissionError which is caught in the
    # `execute()` method.

    process = SubProcess("Stub Process", [__file__])

    assert not process.execute()
    time.sleep(0.5)  # allow process time to terminate
    ei = process.exc_info
    print(f"{ei = }")
    assert ei["exc_type"] is PermissionError
    assert isinstance(ei["exc_value"], PermissionError)
    assert isinstance(ei["exc_traceback"], types.TracebackType)
    assert ei["command"] == __file__
    assert not process.is_running()
    assert process.returncode() is None


def test_terminated_process():
    # Process void-0 exits with an exit code of 0

    process = SubProcess("Stub Process", [sys.executable, str(find_file("void-0.py", root=HERE).resolve())])

    assert process.execute()
    time.sleep(0.5)  # allow process time to terminate
    assert not process.is_running()
    assert process.returncode() == 0

    # Process void-1 exits with an exit code of 1

    process = SubProcess("Stub Process", [sys.executable, str(find_file("void-1.py", root=HERE).resolve())])

    assert process.execute()
    time.sleep(0.5)  # allow process time to terminate
    assert not process.is_running()
    assert process.returncode() == 1


def test_quit_process():
    # when --ignore-sigterm is given, the process will be killed and return code will be -9.

    process = SubProcess(
        "Handle SIGTERM", [sys.executable, str(find_file("handle_sigterm.py", root=HERE).resolve()), "--ignore-sigterm"]
    )

    assert process.execute()
    time.sleep(1.0)  # allow process to start
    assert process.is_running()
    rc = process.quit()
    logger.info(f"After quit() -> {rc = }")
    assert rc == -9

    while process.is_running():
        logger.info(f"Process (PID={process.pid}) is still running...")
        time.sleep(1.0)

    assert process.returncode() == -9

    # when --ignore-sigterm is not given, the process will handle the SIGTERM and exit with 42.

    process = SubProcess("Handle SIGTERM", [sys.executable, str(find_file("handle_sigterm.py", root=HERE).resolve())])

    assert process.execute()
    time.sleep(1.0)  # allow process to start
    assert process.is_running()
    rc = process.quit()
    logger.info(f"After quit() -> {rc = }")
    assert rc == 42

    while process.is_running():
        logger.info(f"Process (PID={process.pid}) is still running...")
        time.sleep(1.0)

    assert process.returncode() == 0  # I would have expected 42 here, don't know why 0


def test_active_process():
    # The empty_process.py should be located in the tests/scripts directory of this project

    stub = SubProcess("Stub Process", [sys.executable, str(find_file("empty_process.py", root=HERE).resolve())])

    # We can set this cmd_port here because we know this from the empty_process.py file
    # In nominal situations, the cmd_port is known from the configuration file of the
    # system (because all processes are known) or communicated to the process manager
    # by the sub-process.

    cmd_port = 5556

    # Execute the sub-process.

    assert stub.execute()

    time.sleep(0.5)  # Give the process time to start up

    assert stub.is_running()
    assert is_active(cmd_port)  # check if the empty_process is active
    assert stub.returncode() is None

    status: str = get_status(cmd_port)
    logger.info(f"ProcessStatus: {status}")

    assert "PID" in status
    assert "UUID" in status
    assert "Up" in status

    time.sleep(1.0)

    logger.info(f"ProcessStatus: {get_status(cmd_port)}")

    procs = list_processes("empty_process", verbose=True)
    logger.info(f"{procs = }")

    assert quit_process(cmd_port)

    time.sleep(0.1)

    # if the sub-process is not in the processes list, it means it has terminated,
    # but since this is running under pytest, the sub-process will be a zombie process
    # until pytest finishes.

    procs = list_processes("empty_process", verbose=True)
    logger.info(f"{procs = }")
    assert not procs
    zombies = list_zombies()
    logger.info(f"{zombies = }")
    assert zombies
    assert stub.is_dead_or_zombie()

    time.sleep(0.1)

    # don't know what the return code will be, sometimes its 0, sometimes its 1 or -15
    _ = stub.quit()  # send a SIGTERM to the sub-process

    logger.info(f"{stub.exc_info = }")

    assert not stub.exists()
    assert not stub.is_running()
    assert not is_active(cmd_port)  # this method takes about 1 second because of the timeout (see send() below)
    assert stub.returncode() == 0


def test_process_no_shell():
    stub = SubProcess("Stub Process", [sys.executable, str(find_file("empty_process.py", root=HERE).resolve())])
    cmd_port = 5556

    assert stub.execute()

    time.sleep(0.5)  # Give the process time to start up

    assert stub.exc_info == {}
    assert is_active(cmd_port)
    assert not stub.is_dead_or_zombie()
    logger.info(capture_rich_output(list_processes("empty")))
    logger.info(ps_egrep("empty"))
    assert quit_process(cmd_port)


def test_process_with_shell():
    stub = SubProcess(
        "Stub Process",
        [sys.executable, str(find_file("empty_process.py", root=HERE).resolve())],
        shell=True,
    )
    cmd_port = 5556

    assert stub.execute()

    time.sleep(0.5)  # Give the process time to start up

    assert stub.exc_info == {}
    assert is_active(cmd_port)
    assert not stub.is_dead_or_zombie()
    logger.info(capture_rich_output(list_processes("empty")))
    logger.info(ps_egrep("empty"))
    assert quit_process(cmd_port)


def test_process_with_children():
    parent = SubProcess(
        "Parent Process",
        [sys.executable, str(find_file("process_with_children.py", root=HERE).resolve())],
    )
    cmd_port = 5557

    assert parent.execute()

    time.sleep(0.5)  # Give the process time to start up

    assert parent.exc_info == {}
    assert is_active(cmd_port)
    assert parent.children()
    print("children", parent.children())
    print("list_processes", list_processes("empty"))
    logger.info(ps_egrep("empty"))
    # assert quit_process(cmd_port)
    print("rc = ", parent.quit())
    print("children", parent.children())
    print("list_processes", list_processes("empty"))


def test_raise_value_error():
    proc = SubProcess("ValueErrorApp", [sys.executable, HERE / "scripts" / "raise_value_error.py"])
    proc.execute()

    time.sleep(1.5)  # the script will raise a ValueError after 1.0s

    assert not proc.is_running()
    assert proc.exc_info == {}
    assert proc.is_dead_or_zombie()
    assert proc.returncode() == 1

    proc.quit()


def test_process_status():
    # Need to provide a prefix here otherwise we will get a duplicate metrics error when a control server is created.

    status = ProcessStatus(metrics_prefix="X372")

    sd = status.as_dict()

    print(sd)

    assert sd["PID"] == os.getpid()
    assert "UUID" in sd


# Helper function to communicate with the empty_process.py


def is_active(port: int) -> bool:
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
        ProcessStatus: status information on the running process.
    """
    return send(port, "Status?")


def quit_process(port: int) -> bool:
    """
    Send a Quit command to the sub-process and returns the response.
    """
    return send(port, "Quit") == "Quiting"


def send(port: int, command: str) -> str:
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
