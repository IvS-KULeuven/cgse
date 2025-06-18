import multiprocessing
import pickle
import subprocess
import threading
import time
from difflib import SequenceMatcher
from enum import Enum
from pathlib import Path
from typing import Union

import sys
import zmq
from qtpy.QtCore import QLockFile
from qtpy.QtCore import QObject
from qtpy.QtCore import QThread
from qtpy.QtCore import Qt
from qtpy.QtCore import Signal
from qtpy.QtGui import QCloseEvent
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QApplication
from qtpy.QtWidgets import QFrame
from qtpy.QtWidgets import QGridLayout
from qtpy.QtWidgets import QHBoxLayout
from qtpy.QtWidgets import QLabel
from qtpy.QtWidgets import QMainWindow
from qtpy.QtWidgets import QMessageBox
from qtpy.QtWidgets import QScrollArea
from qtpy.QtWidgets import QVBoxLayout, QGroupBox

from egse.confman import ConfigurationManagerProxy, is_configuration_manager_active
from egse.gui import show_info_message
from egse.gui.buttons import ToggleButton, TouchButton
from egse.gui.led import LED, Indic
from egse.observer import Observer, Observable
from egse.plugin import entry_points
from egse.process import ProcessStatus
from egse.procman import LOGGER, StartCommand, StopCommand, StatusCommand
from egse.procman import ProcessManagerProxy
from egse.registry.client import RegistryClient
from egse.resource import get_resource
from egse.setup import Setup
from egse.system import do_every
from egse.zmq_ser import set_address_port

MAX_SLEEP = 10


class ControlServerStatus(Enum):
    """Status of the Control Server of a device."""

    ACTIVE = True  # Control Server active -> LED green
    INACTIVE = False  # Control Server inactive -> LED red
    UNKNOWN = None  # Control Server starting/stopping -> Hourglass


def get_cgse_cmd(device_proxy: str) -> str:
    """Determines the CGSE command for the Control Server of the given device proxy.

    To start/stop any device Control Server or query its status, we need to know its commanding.  These commands
    would be:

        - cgse <service_name> start <device_id> [<device_args>] [--sim]
        - cgse <service_name> stop <device_id>
        - cgse <service_name> status <device_id>

    In this function, we determine - based on the given device proxy - what the corresponding `service_name` is in the
    commands listed above.

    The current implementation (which may have to be changed in the future) is to compare the module name of the given
    device proxy with all `cgse.service` entry points in the `pyproject.toml` files of the installed modules.  The
    entry point of which the value matches the module name best is then selected.

    Args:
        device_proxy (str): Device proxy

    Returns: CGSE command to start/stop the Control Server or to query its status.
    """

    module_name = device_proxy[7:].rsplit(".", 1)[0]
    entry_point_values = []
    for ep in sorted(entry_points("cgse.service"), key=lambda x: x.name):
        entry_point_values.append(ep.value)

    similarity_scores = [
        SequenceMatcher(None, entry_point_value, module_name).ratio() for entry_point_value in entry_point_values
    ]
    best_match_index = similarity_scores.index(max(similarity_scores))
    best_match = entry_point_values[best_match_index].split(":")[-1]

    return f"cgse {best_match}"


def get_cgse_ui(device_proxy: str) -> Union[str, None]:
    """Determines the CGSE command for the UI of the given device proxy.

    To open the UI of any device Control Server, we need to know its commanding. In this function, we determine - based
    on the given proxy - what the corresponding UI command is.

    The current implementation (which may have to be changed in the future) is to compare the module name of the given
    device proxy with all `gui_scripts` entries in the `pyproject.toml` files of the installed modules.  The entry of
    which the name matches the module name best in then selected (when its similarity score is high enough).

    Args:
        device_proxy (str): Device proxy

    Returns: CGSE command to start/stop the UI of the Control Server.
    """

    module_name = device_proxy[7:].rsplit(".", 1)[0]
    entry_point_values = []
    for ep in sorted(entry_points("gui_scripts"), key=lambda x: x.name):
        entry_point_values.append(ep.name)

    similarity_scores = [
        SequenceMatcher(None, entry_point_value, module_name).ratio() for entry_point_value in entry_point_values
    ]
    best_match_index = similarity_scores.index(max(similarity_scores))

    if similarity_scores[best_match_index] > 1 / len(similarity_scores):
        best_match = entry_point_values[best_match_index].split(":")[-1]
        return best_match
    else:
        return None


class UiCommand:
    """Command to start the UI for the Control Server for a device."""

    def __init__(self, device_id: str, cmd: str):
        """Initialisation of a UI command.

        Args:
            device_id (str): Device identifier
            cmd (str): Command to open the UI for the Control Server
        """

        self._device_id = device_id
        self._cmd = cmd

    @property
    def device_id(self):
        """Returns the device identifier.

        Returns: Device identifier
        """
        return self._device_id

    @property
    def cmd(self) -> str:
        """Returns the full command to open the UI for the Control Server.

        Returns: Full command to open the UI for the Control Server.
        """
        return self._cmd


class ConfigurationManagerMonitoringWorker(QObject):
    """Monitoring worker for the Configuration Manager."""

    setup_changed_signal = Signal(Setup)
    obsid_changed_signal = Signal(int)

    def __init__(self, parent=None):
        """Initialisation of a monitoring worker for the Configuration Manager.

        This monitoring worker will listen on the monitoring port of the Configuration Manager and send out a signal
        whenever the setup or obsid is changed.
        """

        super(ConfigurationManagerMonitoringWorker, self).__init__(parent)

        self.setup = None  # Previous setup
        self.obsid = None  # Previous obsid

        self.active = False

        self.socket = zmq.Context().socket(zmq.SUB)
        self.connect_socket()

        self.monitoring_info = None

    def connect_socket(self) -> None:
        """Connect the socket to the monitoring port of the Configuration Manager."""

        cm = ConfigurationManagerProxy()

        endpoint = cm.get_endpoint()
        monitoring_port = cm.get_monitoring_port()
        address = set_address_port(endpoint, monitoring_port)

        self.socket.connect(address)
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")

    def start_listening(self) -> None:
        """Start listening to the monitoring port of the Configuration Manager."""

        self.active = True
        self.run()

    def stop_listening(self) -> None:
        """Stop listening to the monitoring port of the Configuration Manager."""

        self.active = False

    def run(self) -> None:
        """Keep on listening on the monitoring port as long as the monitoring worker is active.

        Compare the setup and obsid from the incoming monitoring information from the Configuration Manager with the
        last knows values.  Whenever the setup or obsid has changed, a signal is emitted.
        """

        while self.active:
            pickle_string = self.socket.recv()
            self.monitoring_info = pickle.loads(pickle_string)

            self.check_for_setup_changes()
            self.check_for_obsid_changes()

    def check_for_setup_changes(self) -> None:
        """Checks the incoming monitoring information from the Configuration Manager for changes in the setup.

        If the setup has changed, a signal is emitted.  A change in setup is defined as a change in the setup identifier.
        """

        new_setup = self.monitoring_info["setup"]

        if new_setup != self.setup:
            self.setup = new_setup

            # Due to static type checking the IDE doesn't recognise the `emit` method on a `Signal` object.  This
            # happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a way that static
            # analysers can easily detect.
            # noinspection PyUnresolvedReferences
            self.setup_changed_signal.emit(self.setup)

    def check_for_obsid_changes(self) -> None:
        """Checks the incoming monitoring information from the Configuration Manager for changes in the obsid.

        If the obsid has changes, a signal is emitted.
        """

        new_obsid = self.monitoring_info["obsid"]

        if new_obsid != self.obsid:
            self.obsid = new_obsid

            # Due to static type checking the IDE doesn't recognise the `emit` method on a `Signal` object.  This
            # happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a way that static
            # analysers can easily detect.
            # noinspection PyUnresolvedReferences
            self.obsid_changed_signal.emit(self.obsid)


class CoreServiceMonitoringWorker(QObject):
    """Monitoring worker for the core services."""

    core_service_status_signal = Signal(dict)

    def __init__(self, core_service_name: str, core_service: str, parent=None):
        """Initialisation of a monitoring worker for a core service.

        Args:
            core_service_name (str): Name of the core service
            core_service (str): Core service command to start / stop / query the status with
                                `cgse <core_service> start|stop|status`
        """

        super().__init__(parent)

        self.core_service_name = core_service_name
        self.cs = self.service_type = core_service

        self.active = False
        self.registry_client = RegistryClient()

        self.core_service_is_active = False

    def start_listening(self):
        """Start checking the status of the core service as long as the monitoring worker is active."""

        self.active = True
        self.registry_client.connect()
        self.run()

    def stop_listening(self):
        """Stop checking the status of the core service."""

        self.active = False
        self.registry_client.disconnect()

    def run(self):
        """Keep on checking the status of the core service as long as the monitoring worker is active.

        Whenever the status of the core service has changed, a signal is emitted.  This signal comprises a
        dictionary with the following information:

            - Core service identifier;
            - Boolean indicating whether the core service is active;
        """

        while self.active:
            services = self.registry_client.list_services(service_type=self.service_type)

            # Due to static type checking the IDE doesn't recognise the `emit` method on a `Signal` object.
            # This happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a
            # way that static analysers can easily detect.
            # noinspection PyUnresolvedReferences
            self.core_service_status_signal.emit(
                {"core_service_name": self.core_service_name, "core_service_is_active": len(services) > 0}
            )


class DeviceMonitoringWorker(QObject):
    """Monitoring worker for the devices."""

    process_status_signal = Signal(dict)

    def __init__(self, device_id: str, device_proxy: str, parent=None):
        """Initialisation of a monitoring worker for a device.

        Args:
            device_id (str): Identifier of the device to monitor
            device_proxy (str): Device proxy
        """

        super().__init__(parent)

        self.device_id = device_id
        self.device_proxy = device_proxy
        self.process_manager: ProcessManagerProxy = ProcessManagerProxy()
        self.active = False
        self.registry_client = RegistryClient()

        self.total_sleep = 0

        self.cs_is_active = False
        self.cs_status = ControlServerStatus.INACTIVE

        self.cgse_cmd = get_cgse_cmd(self.device_proxy)
        self.status_cmd = StatusCommand(device_id=self.device_id, cgse_cmd=self.cgse_cmd)

    def start_listening(self) -> None:
        """Start listening to the output of the CGSE status command."""

        self.active = True
        self.registry_client.connect()
        self.run()

    def stop_listening(self) -> None:
        """Stop listening to the output of the CGSE status command."""

        self.active = False
        self.registry_client.disconnect()

    def run(self) -> None:
        """Keep on checking the status of the device Control Server as long as the monitoring worker is active.

        Execute the CGSE status command to query the status of the device Control Server.  Whenever the status of the
        device Control Server has changed, a signal is emitted.  This signal comprises a dictionary with the following
        information:
            - Device identifier;
            - Boolean indicating whether the Control Server is active;
            - In case the Control Server is active:
                - Whether the device is connected;
                - Whether the Control Server was started in simulator mode (rather than operational mode).
        """

        while self.active:
            if self.cs_status == ControlServerStatus.UNKNOWN:
                time.sleep(0.5)
                self.total_sleep += 0.5

            services = self.registry_client.discover_service(self.device_id)

            cs_is_active_new = not services is None

            if cs_is_active_new != self.cs_is_active or self.total_sleep > MAX_SLEEP:
                self.cs_is_active = cs_is_active_new

                if self.cs_is_active:
                    self.cs_status = ControlServerStatus.ACTIVE
                    status_output = self.process_manager.get_device_process_status(self.status_cmd)

                    # Due to static type checking the IDE doesn't recognise the `emit` method on a `Signal` object.
                    # This happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a
                    # way that static analysers can easily detect.
                    # noinspection PyUnresolvedReferences
                    self.process_status_signal.emit(status_output)

                else:
                    self.cs_status = ControlServerStatus.INACTIVE
                    # Due to static type checking the IDE doesn't recognise the `emit` method on a `Signal` object.
                    # This happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a
                    # way that static analysers can easily detect.
                    # noinspection PyUnresolvedReferences
                    self.process_status_signal.emit({"device_id": self.device_id, "cs_is_active": False})

                self.total_sleep = 0


class LedColor(Enum):
    """Potential colours for the LEDs showing the status of the processes."""

    ACTIVE = Indic.GREEN  # Not for device Control Servers
    ACTIVE_DEVICE_CONNECTED = Indic.GREEN  # Device Control Servers only
    ACTIVE_NO_DEVICE_CONNECTED = Indic.ORANGE  # Device Control Servers only
    INACTIVE = Indic.RED


class CoreServiceWidget(QGroupBox):
    """Widget to display the status of the core services."""

    def __init__(self, core_service_name: str, parent: QMainWindow):
        """Initialisation of a widget to display the status of the core services.

        Args:
            core_service_name (str): Name of the core service
            parent (QMainWindow): Parent window
        """

        super().__init__()

        self.core_service_name = core_service_name

        self.parent = parent

        layout = QGridLayout()

        index = 0

        # Status LED

        self.status_led = LED(parent=self)
        layout.addWidget(self.status_led, 0, index)
        index += 1

        # Process name

        self.core_service_name_label = QLabel(core_service_name)
        layout.addWidget(self.core_service_name_label, 0, index)
        layout.setColumnStretch(index, 1)  # Push LED and name to the left and buttons to the right
        index += 1

        self.setLayout(layout)

    def set_status_led(self, color: LedColor) -> None:
        """Set the colour of the status LED.

        Args:
            color (LedColor): LED colour
        """

        self.status_led.set_color(color.value)


class DeviceWidget(QGroupBox, Observable):
    """Widget to display the status of a device Control Server, to start and stop it, and to open its UI."""

    def __init__(
        self, device_id: str, device_name: str, device_proxy: str, device_args: Union[list, None], parent: QMainWindow
    ):  # FIXME device_args
        """Initialisation of a device widget.

        Args:
            device_id (str): Device identifier
            device_name (str): Device name
            device_proxy (str): Device proxy
            device_args (Union[str, args]): Device arguments
            parent (QMainWindow): Parent window
        """

        super().__init__()
        Observable.__init__(self)

        self.device_id = device_id
        self.device_args = device_args
        self.is_simulator_mode = False

        self.parent = parent

        self.cgse_cmd = get_cgse_cmd(device_proxy)
        self.ui_cmd = get_cgse_ui(device_proxy)

        layout = QGridLayout()

        index = 0

        # Status LED

        self.status_led = LED(parent=self)
        self.set_status_led(LedColor.INACTIVE)
        layout.addWidget(self.status_led, 0, index)
        index += 1

        # Process name

        self.process_name_label = QLabel(device_name)
        layout.addWidget(self.process_name_label, 0, index)
        layout.setColumnStretch(index, 1)  # Push LED and name to the left and buttons to the right
        index += 1

        # Open UI
        if self.has_ui_option():
            self.ui_button = TouchButton(
                name=f"Open the UI for the {self.device_id} Control Server.",
                status_tip=f"Open the UI for the {self.device_id} Control Server.",
                selected=get_resource(":/icons/user-interface.svg"),
            )
            self.ui_button.setFixedSize(30, 30)
            self.ui_button.clicked.connect(self.open_ui)
            layout.addWidget(self.ui_button, 0, index)
            index += 1

        # Shut down / re-start

        self.start_stop_button = ToggleButton(
            name=f"Start / shut down the {self.device_id} Control Server.",
            status_tip=f"Start / shut down the {self.device_id} Control Server.",
            selected=get_resource(":/icons/start-process-button.svg"),
            not_selected=get_resource(":/icons/stop-process-button.svg"),
            disabled=[get_resource(":/icons/busy.svg"), get_resource(":/icons/busy.svg")],
        )
        self.start_stop_button.clicked.connect(self.start_stop_cs)
        layout.addWidget(self.start_stop_button, 0, index)
        index += 1

        # Operational / simulator mode

        if self.has_sim_option():
            self.simulator_option_button = ToggleButton(
                name=f"Operational vs. simulator mode",
                status_tip=f"Indicate whether you want to start the Control Server in operational or simulator mode.",
                selected=get_resource(":/icons/operational-mode.svg"),
                not_selected=get_resource(":/icons/simulator-mode.svg"),
                disabled=[get_resource(":/icons/simulator-mode.svg"), get_resource(":/icons/operational-mode.svg")],
            )
        else:
            self.simulator_option_button = ToggleButton(
                name=f"Operational mode only",
                status_tip=f"Operational mode only.",
                selected=get_resource(":/icons/operational-mode.svg"),
                not_selected=get_resource(":/icons/operational-mode.svg"),
                disabled=[get_resource(":/icons/operational-mode.svg")],
            )
        self.simulator_option_button.clicked.connect(self.change_cs_start_mode)
        layout.addWidget(self.simulator_option_button, 0, index)
        index += 1

        self.setLayout(layout)

    def has_sim_option(self) -> bool:
        """Checks whether the Control Server can be started in simulator mode.

        Returns: True if the Control Server can be started in simulator mode; False otherwise.
        """

        output = subprocess.check_output(f"{self.cgse_cmd} start --help", shell=True).decode("utf-8")
        return "--sim" in output

    def has_ui_option(self) -> bool:
        """Checks whether the Control Server has a corresponding UI.

        Returns: True if the Control Server has a corresponding UI.
        """

        return self.ui_cmd is not None

    def open_ui(self) -> None:
        """Open the UI."""

        self.notify_observers(UiCommand(device_id=self.device_id, cmd=self.ui_cmd))

    def start_stop_cs(self) -> None:
        """Take action when the start/stop button is clicked."""

        self.start_stop_button.disable()

        if self.start_stop_button.is_selected():
            self.notify_observers(StopCommand(device_id=self.device_id, cgse_cmd=self.cgse_cmd))
        else:
            self.notify_observers(
                StartCommand(
                    device_id=self.device_id,
                    cgse_cmd=self.cgse_cmd,
                    device_args=self.device_args,
                    simulator_mode=self.is_simulator_mode,
                )
            )

    def change_cs_start_mode(self) -> None:
        """Switch from simulator to operational mode, and vice versa."""

        self.is_simulator_mode = not self.is_simulator_mode

    def set_status_led(self, color: LedColor) -> None:
        """Set the colour of the status LED.

        Args:
            color (LedColor): LED colour
        """

        self.status_led.set_color(color.value)


class ProcessManagerUIModel:
    """Model in the MVC pattern that makes the PM UI application."""

    def __init__(self):
        """Initialisation of the Process Manager UI model."""

        super().__init__()

        try:
            self.process_manager: Union[ProcessManagerProxy, None] = ProcessManagerProxy()
        except ConnectionError:
            LOGGER.error("Could not connect to Process Manager Control Server")
            self.process_manager: Union[ProcessManagerProxy, None] = None

    def is_connected(self) -> bool:
        """Checks whether the Process Manager Control Server is active.

        Checks whether a connection to the Process Manager Control Server has been established.

        Returns: True if a connection to the Process Manager Control Server has been established; False otherwise.
        """

        if not self.process_manager:
            return False

        return self.process_manager.ping() and self.process_manager.is_cs_connected()

    def get_device_ids(self) -> dict:
        """Returns the relevant device identifiers.

        Returns: Dictionary in which the device identifiers are the keys, and the values are a tuple with the device
                 name, the device proxy and the device arguments.
        """

        return self.process_manager.get_device_ids()

    def get_core_services(self) -> dict:
        """Returns the core services.

        Returns: Dictionary with the core service names are the keys, and the values are the core service CGSE commands.
        """

        return self.process_manager.get_core_processes()

    def start_process(self, start_cmd: StartCommand):
        """Start a process with the given start command.

        The process is started on the same machine as the Process Manager.

        Args:
            start_cmd (StartCommand): Command to start the process
        """
        self.process_manager.start_process(start_cmd)

    def stop_process(self, stop_cmd: StopCommand):
        """Stop a process with the given stop command.

        The process was running on the same machine as the Process Manager.

        Args:
            stop_cmd (StopCommand): Command to stop the process
        """

        self.process_manager.stop_process(stop_cmd)


class ProcessManagerUIView(QMainWindow, Observable):
    """View in the MVC pattern that makes the PM UI application."""

    def __init__(self, core_services: dict):
        """Initialisation of the Process Manager UI model with the given core services.

        Args:
            core_services (dict): Dictionary with the core services
        """

        super(ProcessManagerUIView, self).__init__()
        Observable.__init__(self)

        self.setGeometry(300, 300, 1000, 1000)
        self.setWindowTitle("Process Manager")

        self.core_services: dict = core_services
        self.overview_core_services_widget_layout = QVBoxLayout()
        self.overview_core_services_widget = QGroupBox("Core Services", self)

        self.core_service_widgets = {}  # Widgets for the core services
        self.device_widgets = {}  # Widgets for the devices

        self.overview_devices_widget_layout = QVBoxLayout()
        self.overview_devices_widget = QGroupBox("Devices", self)
        self.init_ui()

    def init_ui(self) -> None:
        """Creating the content of the UI."""

        app_frame = QFrame()
        app_frame.setObjectName("AppFrame")

        global_layout = QHBoxLayout()

        vbox_left = QVBoxLayout()
        vbox_right = QVBoxLayout()
        global_layout.addLayout(vbox_left)
        global_layout.addLayout(vbox_right)

        app_frame.setLayout(global_layout)
        scroll = QScrollArea()

        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)

        # Core Services

        self.overview_core_services_widget_layout.addStretch()
        self.overview_core_services_widget.setLayout(self.overview_core_services_widget_layout)

        for core_service in self.core_services.keys():
            core_service_widget = CoreServiceWidget(core_service_name=core_service, parent=self)
            self.overview_core_services_widget_layout.addWidget(core_service_widget)
            self.core_service_widgets[core_service] = core_service_widget

        vbox_left.addWidget(self.overview_core_services_widget)

        # Devices

        self.overview_devices_widget_layout.addStretch()
        self.overview_devices_widget.setLayout(self.overview_devices_widget_layout)

        vbox_right.addWidget(self.overview_devices_widget)

        scroll.setWidget(app_frame)
        self.setCentralWidget(scroll)

    def clear_device_overview(self) -> None:
        """Clears the panel with the overview of the device Control Servers."""

        while self.overview_devices_widget_layout.count():
            widget = self.overview_devices_widget_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()

                if widget := self.overview_devices_widget_layout.takeAt(0).widget():
                    widget.deleteLater()
                self.device_widgets.clear()

    def closeEvent(self, close_event: QCloseEvent) -> None:
        """Takes action when the UI is closed."""

        self.notify_observers(close_event)


class ProcessManagerUIController(Observer):
    """Controller in the MVC pattern that makes the PM UI application."""

    def __init__(self, model: ProcessManagerUIModel, view: ProcessManagerUIView):
        """Initialisation of the Controller for the Process Manager GUI.

        Args:
            model (ProcessManagerUIModel): Process Manager UI model
            view (ProcessManagerUIView): Process Manager UI view
        """

        super().__init__()

        self.model = model
        self.view = view

        # Monitoring the Configuration Manager -> setup + obsid

        self.configuration_manager_monitoring_thread = QThread(self.view)
        self.configuration_manager_monitoring_worker = ConfigurationManagerMonitoringWorker()
        self.configuration_manager_monitoring_worker.moveToThread(self.configuration_manager_monitoring_thread)
        # Due to static type checking the IDE doesn't recognise the `connect` method on a `Signal` object.  This
        # happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a way that static
        # analysers can easily detect.
        # noinspection PyUnresolvedReferences
        self.configuration_manager_monitoring_worker.setup_changed_signal.connect(self.on_setup_changed_signal)
        # noinspection PyUnresolvedReferences
        self.configuration_manager_monitoring_thread.started.connect(
            self.configuration_manager_monitoring_worker.start_listening
        )
        self.configuration_manager_monitoring_thread.start()

        # Monitoring the Core Services

        self.core_services = self.model.get_core_services()
        self.core_service_monitoring_workers = {}
        self.core_service_monitoring_threads = {}

        self.start_core_service_monitoring()

        # Monitoring the devices
        # -> Start doing so when the setup changes

        self.device_ids = {}

        self.device_monitoring_threads = {}
        self.device_monitoring_workers = {}

    def on_setup_changed_signal(self, setup: Setup) -> None:
        """Reaction to a change in the setup.

        This method is called when a new setup is loaded in the Configuration Manager and executes the following steps:
            - Based on the old list of devices (from the previous setup):
                - Stop monitoring the devices;
                - Remove the device widgets from the layout;
            - Update the list of devices (based on the new setup);
            - Based on the updated list of devices:
                - Start monitoring the devices;
                - Add the device widgets to the layout.

        Args:
            setup (Setup): New setup that was loaded in the Configuration Manager
        """

        LOGGER.info(f"Updating the list of devices in the PM UI, based on setup {setup.get_id()}")

        # Stop monitoring the current devices (if any) -> based on the previous setup
        self.stop_device_monitoring()

        # Remove the current device widgets from the layout -> based on the previous setup
        self.view.clear_device_overview()

        # Update the list of devices, based on the new setup
        self.device_ids = self.model.get_device_ids()

        # Start monitoring the new devices -> based on the new setup
        self.start_device_monitoring()

    def on_device_status_signal(self, device_info: dict) -> None:
        """Reaction to a change in the status of a device.

        Args:
            device_info (dict): Information about a device
        """

        device_id = device_info["device_id"]
        cs_is_active = device_info["cs_is_active"]

        try:
            if cs_is_active:
                device_is_connected = device_info["device_is_connected"]
                is_simulator_mode = device_info["is_simulator_mode"]
                if device_is_connected:
                    self.view.device_widgets[device_id].set_status_led(LedColor.ACTIVE_DEVICE_CONNECTED)
                else:
                    self.view.device_widgets[device_id].set_status_led(LedColor.ACTIVE_NO_DEVICE_CONNECTED)
                self.view.device_widgets[device_id].simulator_option_button.set_selected(is_simulator_mode)
                self.view.device_widgets[device_id].simulator_option_button.disable()
                self.view.device_widgets[device_id].start_stop_button.set_selected(False)
                self.view.device_widgets[device_id].start_stop_button.enable()

            else:
                self.view.device_widgets[device_id].set_status_led(LedColor.INACTIVE)
                self.view.device_widgets[device_id].simulator_option_button.enable()
                self.view.device_widgets[device_id].simulator_option_button.set_selected(True)
                self.view.device_widgets[device_id].is_simulator_mode = False
                self.view.device_widgets[device_id].start_stop_button.set_selected(True)
                self.view.device_widgets[device_id].start_stop_button.enable()

            self.view.device_widgets[device_id].start_stop_button.enable()
        except KeyError:
            pass

    def on_core_service_status_signal(self, core_service_info: dict) -> None:
        """Reaction to a change in the status of a core service.

        Args:
            core_service_info (dict): Information about a core service
        """

        core_service = core_service_info["core_service_name"]
        cs_is_active = core_service_info["core_service_is_active"]

        try:
            if cs_is_active:
                self.view.core_service_widgets[core_service].set_status_led(LedColor.ACTIVE)
            else:
                self.view.core_service_widgets[core_service].set_status_led(LedColor.INACTIVE)
        except KeyError:
            pass

    def stop_configuration_manager_monitoring(self) -> None:
        """Stop monitoring the Configuration Manager."""

        self.configuration_manager_monitoring_worker.stop_listening()
        self.configuration_manager_monitoring_thread.quit()
        self.configuration_manager_monitoring_thread.wait()

    def start_core_service_monitoring(self):
        """Start monitoring the core services."""

        for core_service_name, core_service_cmd in self.model.get_core_services().items():
            core_service_monitoring_thread = QThread(self.view)
            core_service_monitoring_worker = CoreServiceMonitoringWorker(core_service_name, core_service_cmd)
            core_service_monitoring_worker.moveToThread(core_service_monitoring_thread)
            # Due to static type checking the IDE doesn't recognise the `connect` method on a `Signal` object.  This
            # happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a way that static
            # analysers can easily detect.
            # noinspection PyUnresolvedReferences
            core_service_monitoring_worker.core_service_status_signal.connect(self.on_core_service_status_signal)
            # noinspection PyUnresolvedReferences
            core_service_monitoring_thread.started.connect(core_service_monitoring_worker.start_listening)
            core_service_monitoring_thread.start()

            self.core_service_monitoring_threads[core_service_name] = core_service_monitoring_thread
            self.core_service_monitoring_workers[core_service_name] = core_service_monitoring_worker

    def stop_core_service_monitoring(self):
        """Stop monitoring the core services."""

        for core_service in self.model.get_core_services():
            self.core_service_monitoring_workers[core_service].stop_listening()
            self.core_service_monitoring_threads[core_service].quit()
            self.core_service_monitoring_threads[core_service].wait()

        self.core_service_monitoring_workers.clear()
        self.core_service_monitoring_threads.clear()

    def start_device_monitoring(self):
        """Start monitoring the devices and add them to the UI.

        This method is called when the setup changes.  We assume that the following steps have already been executed:
            - We stopped monitoring the devices that were listed in the previous setup:
            - We removed the corresponding device widgets from the layout;
            - We updated the list of devices to monitor (in `self.device_ids`) based on the new setup.

        This method does the following:
            - Start monitoring the devices that are listed in the new setup;
            - Add the new device widgets to the layout.
        """

        for device_id, (device_name, device_proxy, device_args) in self.device_ids.items():
            device_monitoring_thread = QThread(self.view)  # TODO
            device_monitoring_worker = DeviceMonitoringWorker(device_id, device_proxy)
            device_monitoring_worker.moveToThread(device_monitoring_thread)
            # Due to static type checking the IDE doesn't recognise the `connect` method on a `Signal` object.  This
            # happens because `Signal` is a special descriptor in `PyQt` and doesn't expose `emit` in a way that static
            # analysers can easily detect.
            # noinspection PyUnresolvedReferences
            device_monitoring_worker.process_status_signal.connect(self.on_device_status_signal)
            # noinspection PyUnresolvedReferences
            device_monitoring_thread.started.connect(device_monitoring_worker.start_listening)
            device_monitoring_thread.start()

            self.device_monitoring_threads[device_id] = device_monitoring_thread
            self.device_monitoring_workers[device_id] = device_monitoring_worker

            # Add the new device widgets

            device_widget = DeviceWidget(device_id, device_name, device_proxy, device_args, self.view)
            device_widget.add_observer(self)
            self.view.device_widgets[device_id] = device_widget
            self.view.overview_devices_widget_layout.addWidget(device_widget)

    def stop_device_monitoring(self):
        """Stop monitoring the devices and remove them from the UI."""

        if len(self.device_ids) > 0:
            for device_id in self.device_ids.keys():
                self.device_monitoring_workers[device_id].stop_listening()
                self.device_monitoring_threads[device_id].quit()
                self.device_monitoring_threads[device_id].wait()

        self.device_monitoring_workers.clear()
        self.device_monitoring_threads.clear()

    def update(self, changed_object) -> None:
        """Updates the state of the controller upon notification from an observable."""

        # Closure of the UI

        if isinstance(changed_object, QCloseEvent):
            # Stop monitoring the Configuration Manager
            self.stop_configuration_manager_monitoring()

            # Stop monitoring the Core Services
            self.stop_core_service_monitoring()

            # Stop monitoring the devices
            self.stop_device_monitoring()

        # Start button in one of the widgets has been clicked

        elif isinstance(changed_object, StartCommand):
            self.model.start_process(changed_object)
            self.device_monitoring_workers[changed_object.device_id].cs_status = ControlServerStatus.UNKNOWN

        # Stop button in one of the widgets has been clicked

        elif isinstance(changed_object, StopCommand):
            self.model.stop_process(changed_object)
            self.device_monitoring_workers[changed_object.device_id].cs_status = ControlServerStatus.UNKNOWN

        # UI button in one of the widgets has been clicked

        elif isinstance(changed_object, UiCommand):
            subprocess.call(changed_object.cmd, shell=True)

    def do(self, actions):
        """Execute the given actions upon notification from an observable."""

        pass


def main():
    """Main method to launch the Process Manager GUI."""

    lock_file = QLockFile(str(Path("~/pm_ui.app.lock").expanduser()))

    multiprocessing.current_process().name = "pm_ui"
    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(str(get_resource(":/icons/pm_ui.svg"))))

    if lock_file.tryLock(100):
        process_status = ProcessStatus()

        timer_thread = threading.Thread(target=do_every, args=(10, process_status.update))
        timer_thread.daemon = True
        timer_thread.start()

        # Check whether the Process Manager CS is running
        # (show a warning in a pop-up window if it's not)

        try:
            with ProcessManagerProxy():
                if not is_configuration_manager_active():
                    description = "Could not connect to Configuration Manager"
                    into_text = (
                        "The GUI will start, but without listed processes. "
                        "Please, check if the Configuration Manager is running and start the server if needed."
                        # "Otherwise, check if the correct HOSTNAME for the Configuration Manager is set in the "
                        # "Settings.yaml "
                        # "configuration file."
                        "The Process Manager GUI will have to be re-started after that."
                    )

                    show_info_message(description, into_text)

        except ConnectionError:
            description = "Could not connect to Process Manager Control Server"

            into_text = (
                "The GUI will start, but the connection button will show a disconnected state. "
                "Please, check if the Control Server is running and start the server if needed. "
                "Otherwise, check if the correct HOSTNAME for the control server is set in the "
                "Settings.yaml "
                "configuration file."
            )

            show_info_message(description, into_text)
            return

        # Create the Process Manager GUI, following the MVC-model

        model = ProcessManagerUIModel()
        core_services = model.get_core_services()
        view = ProcessManagerUIView(core_services)
        controller = ProcessManagerUIController(model, view)
        view.add_observer(controller)

        view.show()

        return app.exec_()
    else:
        error_message = QMessageBox()
        error_message.setIcon(QMessageBox.Warning)
        error_message.setWindowTitle("Error")
        error_message.setText("The Process Manager (PM) GUI application is already running!")
        error_message.setStandardButtons(QMessageBox.Ok)

        return error_message.exec()


if __name__ == "__main__":
    sys.exit(main())
