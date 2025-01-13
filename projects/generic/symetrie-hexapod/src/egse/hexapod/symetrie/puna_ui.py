"""
A Graphical User Interface for monitoring and commanding the Symétrie Hexapod.

Start the GUI from your terminal as follows:

    puna_ui [--type proxy|direct|simulator]

This GUI is based on the SYM_positioning application from Symétrie. The intent
is to provide operators a user interface which is platform independent, but
familiar.

The application is completely written in Python/Qt5 and can therefore run on any
platform that supports Python and Qt5.

"""
import argparse
import logging
import multiprocessing
import sys
import threading
from enum import IntEnum
from pathlib import Path

from PyQt5.QtCore import QLockFile

from egse.hexapod.symetrie import ControllerFactory
from egse.hexapod.symetrie import ProxyFactory
from egse.hexapod.symetrie import get_hexapod_controller_pars
from egse.hexapod.symetrie.punaplus import PunaPlusController
from egse.hexapod.symetrie.punaplus import PunaPlusProxy

multiprocessing.current_process().name = "puna_ui"

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from prometheus_client import start_http_server

from egse.gui import show_warning_message
from egse.gui.led import Indic
from egse.gui.states import States
from egse.hexapod.symetrie.hexapod_ui import ActuatorStates
from egse.hexapod.symetrie.hexapod_ui import HexapodUIController
from egse.hexapod.symetrie.hexapod_ui import HexapodUIModel
from egse.hexapod.symetrie.hexapod_ui import HexapodUIView
from egse.hexapod.symetrie.puna import PunaSimulator
from egse.process import ProcessStatus
from egse.resource import get_resource
from egse.settings import Settings
from egse.system import do_every

MODULE_LOGGER = logging.getLogger(__name__)


class DeviceControllerType(IntEnum):
    ALPHA = 0
    ALPHA_PLUS = 1


DCT = DeviceControllerType


# Status LEDs define the number of status leds (length of the list), the description and the
# default color when the LED is on.

STATUS_LEDS_ALPHA = [
    ["Error", Indic.RED],  # bit 0
    ["System Initialized", Indic.GREEN],  # bit 1
    ["In position", Indic.GREEN],  # bit 2
    ["Amplifier enabled", Indic.GREEN],  # bit 3
    ["Homing done", Indic.GREEN],  # bit 4
    ["Brake on", Indic.GREEN],  # bit 5
    ["Emergency stop", Indic.ORANGE],  # bit 6
    ["Warning FE", Indic.ORANGE],  # bit 7
    ["Fatal FE", Indic.RED],  # bit 8
    ["Actuator Limit Error", Indic.RED],  # bit 9
    ["Amplifier Error", Indic.RED],  # bit 10
    ["Encoder error", Indic.RED],  # bit 11
    ["Phasing error", Indic.RED],  # bit 12
    ["Homing error", Indic.RED],  # bit 13
    ["Kinematic error", Indic.RED],  # bit 14
    ["Abort input error", Indic.RED],  # bit 15
    ["R/W memory error", Indic.RED],  # bit 16
    ["Temperature error", Indic.RED],  # bit 17
    ["Homing done (virtual)", Indic.ORANGE],  # bit 18
    ["Encoders power off", Indic.ORANGE],  # bit 19
    ["Limit switches power off", Indic.ORANGE],  # bit 20
    ["Reserved", Indic.BLACK],  # bit 21
    ["Reserved", Indic.BLACK],  # bit 22
    ["Reserved", Indic.BLACK],  # bit 23
]

STATUS_LEDS_ALPHA_PLUS = [
    ["Error", Indic.RED],  # bit 0
    ["System Initialized", Indic.GREEN],  # bit 1
    ["Control On", Indic.GREEN],  # bit 2
    ["In Position", Indic.GREEN],  # bit 3
    ["Motion Task Running", Indic.GREEN],  # bit 4
    ["Home Task Running", Indic.GREEN],  # bit 5
    ["Home Complete", Indic.GREEN],  # bit 6
    ["Home Virtual", Indic.GREEN],  # bit 7
    ["Phase Found", Indic.GREEN],  # bit 8
    ["Brake on", Indic.GREEN],  # bit 9
    ["Motion Restricted", Indic.RED],  # bit 10
    ["Power on Encoders", Indic.GREEN],  # bit 11
    ["Power on Limit switches", Indic.GREEN],  # bit 12
    ["Power on Drives", Indic.GREEN],  # bit 13
    ["Emergency Stop", Indic.RED],  # bit 14
]

STATUS_LEDS = {
    DCT.ALPHA: STATUS_LEDS_ALPHA,
    DCT.ALPHA_PLUS: STATUS_LEDS_ALPHA_PLUS
}

# The index of the Control LED

CONTROL_ONOFF = {
    DCT.ALPHA: 3,
    DCT.ALPHA_PLUS: 2
}

ACTUATOR_STATE_LABELS_ALPHA = [
    "In position",
    "Control loop on servo motors active",
    "Homing done",
    "Input “Home switch”",
    "Input “Positive limit switch”",
    "Input “Negative limit switch”",
    "Brake control output",
    "Following error (warning)",
    "Following error",
    "Actuator out of bounds error",
    "Amplifier error",
    "Encoder error",
    "Phasing error (brushless engine only)",
]

ACTUATOR_STATE_LABELS_ALPHA_PLUS = [
    "Error: ",
    "Control On: ",
    "In Position: ",
    "Motion Task Running: ",
    "Home task running: ",
    "Home complete: ",
    "Phase found: ",
    "Brake on: ",
    "Home HW input: ",
    "Negative HW limit switch: ",
    "Positive HW limit switch: ",
    "SW limit reached: ",
    "Following Error: ",
    "Drive fault: ",
    "Encoder error: ",
]

ACTUATOR_STATE_LABELS = {
    DCT.ALPHA: ACTUATOR_STATE_LABELS_ALPHA,
    DCT.ALPHA_PLUS: ACTUATOR_STATE_LABELS_ALPHA_PLUS
}

GUI_SETTINGS = Settings.load("PUNA GUI")


class PunaUIView(HexapodUIView):
    def __init__(self, device_controller_type: DCT, device_id: str):
        super().__init__()

        self.dct = device_controller_type

        if self.dct == DCT.ALPHA:
            title = f"Hexapod PUNA Controller (Alpha) – {device_id}"
        else:
            title = f"Hexapod PUNA Controller (Alpha+) – {device_id}"

        self.setWindowTitle(title)
        self.actuator_states = ActuatorStates(labels=ACTUATOR_STATE_LABELS[self.dct])

        self.init_gui()

    def init_gui(self):

        # The main frame in which all the other frames are located, the outer Application frame

        app_frame = QFrame()
        app_frame.setObjectName("AppFrame")

        # The left part which shows the states and positions

        status_frame = QFrame()
        status_frame.setObjectName("StatusFrame")

        # The right part which has tabs that allow settings, movements, maintenance etc.

        tabs_frame = QFrame()
        tabs_frame.setObjectName("TabsFrame")

        # The states of the Hexapod (contains all the leds)

        states_frame = QFrame()
        states_frame.setObjectName("StatesFrame")

        # The user, machine positions and actuator lengths

        positions_frame = QFrame()
        positions_frame.setObjectName("PositionsFrame")

        hbox = QHBoxLayout()
        vbox_left = QVBoxLayout()
        vbox_right = QVBoxLayout()

        self.create_toolbar()
        self.create_status_bar()

        self.states = States(STATUS_LEDS[self.dct])

        user_positions_widget = self.create_user_position_widget()
        mach_positions_widget = self.create_machine_position_widget()
        actuator_length_widget = self.create_actuator_length_widget()

        vbox_right.addWidget(user_positions_widget)
        vbox_right.addWidget(mach_positions_widget)
        vbox_right.addWidget(actuator_length_widget)

        positions_frame.setLayout(vbox_right)

        vbox_left.addWidget(self.states)

        states_frame.setLayout(vbox_left)

        hbox.addWidget(states_frame)
        hbox.addWidget(positions_frame)

        status_frame.setLayout(hbox)

        tabbed_widget = self.create_tabbed_widget()

        hbox = QHBoxLayout()
        hbox.addWidget(tabbed_widget)
        tabs_frame.setLayout(hbox)

        hbox = QHBoxLayout()
        hbox.addWidget(status_frame)
        hbox.addWidget(tabs_frame)

        app_frame.setLayout(hbox)

        self.setCentralWidget(app_frame)

    def update_status_bar(self, message=None, mode=None, timeout=2000):
        if message:
            self.statusBar().showMessage(message, msecs=timeout)
        if mode:
            self.mode_label.setStyleSheet(
                f"border: 0; " f"color: {'red' if 'Simulator' in mode else 'black'};"
            )
            self.mode_label.setText(f"mode: {mode}")
        self.statusBar().repaint()

    def updatePositions(self, userPositions, machinePositions, actuatorLengths):

        if userPositions is None:
            MODULE_LOGGER.warning("no userPositions passed into updatePositions(), returning.")
            return

        for upos in range(len(self.user_positions)):
            try:
                self.user_positions[upos][1].setText(f"{userPositions[upos]:10.4f}")
            except IndexError:
                MODULE_LOGGER.error(f"IndexError in user_positions, upos = {upos}")

        if machinePositions is None:
            MODULE_LOGGER.warning("no machinePositions passed into updatePositions(), returning.")
            return

        for mpos in range(len(self.mach_positions)):
            self.mach_positions[mpos][1].setText(f"{machinePositions[mpos]:10.4f}")

        if actuatorLengths is None:
            MODULE_LOGGER.warning("no actuatorLengths passed into updatePositions(), returning.")
            return

        for idx, alen in enumerate(self.actuator_lengths):
            alen[1].setText(f"{actuatorLengths[idx]:10.4f}")

    def updateStates(self, states):

        if states is None:
            return

        self.updateControlButton(states[CONTROL_ONOFF[self.dct]])
        self.states.set_states(states)

    def updateControlButton(self, flag):

        self.control.set_selected(on=flag)


class PunaUIModel(HexapodUIModel):
    def __init__(self, connection_type):

        hostname, port, dev_id, dev_name, _ = get_hexapod_controller_pars()
        if connection_type == "proxy":
            device = ProxyFactory().create(dev_name, device_id=dev_id)
        elif connection_type == "direct":
            device = ControllerFactory().create(dev_name, device_id=dev_id)
            device.connect()
        elif connection_type == "simulator":
            device = PunaSimulator()
        else:
            raise ValueError(
                f"Unknown type of Hexapod implementation passed into the model: {connection_type}"
            )

        super().__init__(connection_type, device)

        self._device_id = dev_id

        if device is not None:
            MODULE_LOGGER.debug(f"Hexapod initialized as {device.__class__.__name__}")

    @property
    def device_id(self):
        return self._device_id

    def get_device_controller_type(self) -> DCT:
        return DCT.ALPHA_PLUS if isinstance(self.device, (PunaPlusProxy, PunaPlusController)) else DCT.ALPHA

    def get_speed(self):
        vt, vr, vt_min, vr_min, vt_max, vr_max = self.device.get_speed()
        return vt, vr


class PunaUIController(HexapodUIController):
    def __init__(self, model: PunaUIModel, view: PunaUIView):
        super().__init__(model, view)

    def update_values(self):

        super().update_values()

        # Add here any updates to PUNA specific widgets


def parse_arguments():
    """
    Prepare the arguments that are specific for this application.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--type",
        dest="type",
        action="store",
        choices={"proxy", "simulator", "direct"},
        help="Specify Hexapod implementation you want to connect to.",
        default="proxy",
    )
    parser.add_argument(
        "--profile",
        default=False,
        action="store_true",
        help="Enable info logging messages with method profile information.",
    )
    return parser.parse_args()


def main():
    lock_file = QLockFile(str(Path("~/puna_ui.app.lock").expanduser()))

    styles_location = get_resource(":/styles/default.qss")
    app_logo = get_resource(":/icons/logo-puna.svg")

    args = list(sys.argv)
    args[1:1] = ["-stylesheet", str(styles_location)]
    app = QApplication(args)
    app.setWindowIcon(QIcon(str(app_logo)))

    if lock_file.tryLock(100):

        process_status = ProcessStatus()

        timer_thread = threading.Thread(target=do_every, args=(10, process_status.update))
        timer_thread.daemon = True
        timer_thread.start()

        start_http_server(GUI_SETTINGS.METRICS_PORT)

        args = parse_arguments()

        if args.profile:
            Settings.set_profiling(True)

        if args.type == "proxy":
            *_, device_id, device_name, _ = get_hexapod_controller_pars()
            factory = ProxyFactory()
            proxy = factory.create(device_name, device_id=device_id)
            if not proxy.ping():
                description = "Could not connect to Hexapod Control Server"
                info_text = (
                    "The GUI will start, but the connection button will show a disconnected state. "
                    "Please check if the Control Server is running and start the server if needed. "
                    "Otherwise, check if the correct HOSTNAME for the control server is set in the "
                    "Settings.yaml "
                    "configuration file."
                )

                show_warning_message(description, info_text)

        model = PunaUIModel(args.type)
        view = PunaUIView(model.get_device_controller_type(), model.device_id)
        PunaUIController(model, view)

        view.show()

        return app.exec_()
    else:
        error_message = QMessageBox()
        error_message.setIcon(QMessageBox.Warning)
        error_message.setWindowTitle("Error")
        error_message.setText("The Puna GUI application is already running!")
        error_message.setStandardButtons(QMessageBox.Ok)

        return error_message.exec()


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

    sys.exit(main())
