__all__ = [
    "DEFAULT_SIGNAL_DIR",
    "FileBasedSignaling",
    "create_signal_command_file",
]

import json
import os
import queue
import tempfile
import threading
import time
from pathlib import Path

from egse.log import logger
from egse.system import format_datetime

DEFAULT_SIGNAL_DIR = "/tmp/cgse_signals"


class FileBasedSignaling:
    """
    Thread-safe file-based signaling system for inter-process communication.

    Monitors a directory for JSON command files and queues them for processing
    in the main thread. Commands are automatically removed after being read.

    Usage:
        signaling = FileBasedSignaling("my_service_id")
        signaling.start_monitoring()
        signaling.register_handler('reload', my_reload_function)

        # In your main loop:
        signaling.process_pending_commands()

        # Send commands by creating JSON files:
        echo '{"action": "reload", "params": {}}' > /tmp/cgse_signals/my_service_id_cmd.json

    Thread Safety:
        - File monitoring runs in a background daemon thread
        - Commands are queued and processed with process_pending_commands()
          which should be called from the main thread, main loop.
        - All command handlers execute in the main thread context

    Args:
        service_id: the identifier of your service that shall execute the command.
        signal_dir (str): Directory path to monitor for command files.
            Created if it doesn't exist. Defaults to "/tmp/cgse_signals"

    To trigger actions, create the files in `/tmp/cgse_signals`:

      $ echo "{'action': 'reregister'}" > /tmp/cgse_signals/cm_cs_reregister.json

    """

    def __init__(self, service_id: str, signal_dir=DEFAULT_SIGNAL_DIR):
        logger.info(f"Set up file-based signaling for {service_id} in {signal_dir!s}")

        self.signal_dir: Path = Path(signal_dir)
        self.signal_dir.mkdir(exist_ok=True)
        self.service_id = service_id
        self.running = True
        self.thread = None  # the monitoring thread

        # Queue to pass commands from monitoring thread to main thread
        self.command_queue = queue.Queue()
        self.command_handlers = {}

        # Register some default handlers
        self.register_handler("reregister", self.handle_reregister)
        self.register_handler("reload", self.handle_reload)

    def register_handler(self, action, handler_func):
        """Register a handler function for a specific action."""

        overwrite = True if action in self.command_handlers else False

        self.command_handlers[action] = handler_func
        logger.info(f"Registered handler for action: {action}{' (overwritten)' if overwrite else ''}")

    def start_monitoring(self):
        """
        Start a monitoring thread for signal command file. The thread will put any commands that match
        the service_id on the command queue to be processed by the main loop.
        """
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        return self.thread

    def _monitor_loop(self):
        while self.running:
            for filepath in self.signal_dir.glob(f"{self.service_id}*.json"):
                if filepath.is_file():
                    try:
                        with open(filepath, "r") as fd:
                            command = json.load(fd)
                        # File will only be deleted when json could load it
                        filepath.unlink(missing_ok=True)

                        # Put command in queue for main thread to process
                        self.command_queue.put(
                            {"command": command, "source": str(filepath), "timestamp": format_datetime()},
                        )
                    except Exception as exc:
                        logger.error(f"Error reading command file {filepath!s}: {exc}")

            time.sleep(0.1)

    # Remember that this function needs to be called from the main thread

    def process_pending_commands(self):
        """
        Process the commands that are on the command queue. The registered command handler that
        matches the action will be called with any keyword arguments that are specified in the
        `param` key.

        Call this from your main thread to process signaling commands.
        """

        processed_count = 0

        # Process all pending commands
        while not self.command_queue.empty():
            try:
                command_data = self.command_queue.get_nowait()
                command = command_data["command"]
                action = command.get("action")
                params: dict = command.get("params", {})

                if action in self.command_handlers:
                    logger.info(f"🎯 Processing command in main thread: {action} with {params}")
                    try:
                        self.command_handlers[action](**params)
                        processed_count += 1
                    except Exception as exc:
                        logger.error(f"Error in handler for {action}: {exc}")
                else:
                    logger.warning(f"No handler registered for action: {action}")

                self.command_queue.task_done()

            except queue.Empty:
                break
            except Exception as exc:
                logger.error(f"Error processing command: {exc}")

        return processed_count

    def handle_reregister(self, **params):
        """Default dummy handler for reregistration signals."""
        logger.warning(f"🔄 Re-registering service with params: {params} -> register your own function")

    def handle_reload(self, **params):
        """Default dummy handler for reloading signals."""
        logger.warning(f"⚙️ Reloading config with params: {params} -> register your own function")

    def stop(self):
        """Terminate the monitoring loop thread."""
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1)


def create_signal_command_file(signal_dir: Path, service_id: str, command: dict) -> None:
    """
    Atomically create a signal command file for a specific service.

    Creates a JSON command file using atomic file operations to prevent race
    conditions. The file is first written to a temporary file, then atomically
    renamed to the final destination.

    If the signal_dir doesn't exist, it will be created by this function. The
    signal_dir will not be removed afterward.

    Args:
        signal_dir (Path): Directory where the signal file will be created
        service_id (str): Unique identifier for the target service
        command (dict): Command dictionary containing at least an 'action' key.
                       Will be serialized as JSON with 2-space indentation.

    Returns:
        None

    Raises:
        OSError: If the signal directory is not writable or disk is full
        json.JSONEncodeError: If the command cannot be serialized to JSON
        Exception: Re-raises any other exception after cleaning up temp file

    Example:
        signal_dir = Path("/tmp/myapp_signals")
        create_signal_command_file(
            signal_dir,
            "user-service-8001",
            {"action": "reregister", "params": {"force": True}}
        )
        # Creates: /tmp/myapp_signals/user-service-8001_reregister.json

    Note:
        The final filename format is: {service_id}_{action}.json
        If no 'action' key exists in command, defaults to 'cmd'.
    """
    signal_dir.mkdir(exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(dir=signal_dir, suffix=".tmp")

    try:
        filepath = signal_dir / f"{service_id}_{command.get('action', 'cmd')}.json"

        with os.fdopen(temp_fd, "w") as fd:
            json.dump(command, fd, indent=2)

        Path(temp_path).rename(filepath)

    except Exception as exc:
        Path(temp_path).unlink(missing_ok=True)
        raise exc
