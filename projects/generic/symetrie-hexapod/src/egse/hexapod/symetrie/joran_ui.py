"""
A Graphical User Interface for monitoring and commanding the Symétrie JORAN Hexapod.

Start the GUI from your terminal as follows:

    joran_ui [--type proxy|direct|simulator]

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
from pathlib import Path
from typing import List

multiprocessing.current_process().name = "joran_ui"

import pyqtgraph as pg
from PyQt5.QtCore import QDateTime, QLockFile
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget
from prometheus_client import start_http_server

from egse.gui import show_warning_message
from egse.gui.led import Indic
from egse.gui.states import States
from egse.gui.stripchart import StripChart
from egse.hexapod.symetrie.hexapod_ui import ActuatorStates
from egse.hexapod.symetrie.hexapod_ui import HexapodUIController
from egse.hexapod.symetrie.hexapod_ui import HexapodUIModel
from egse.hexapod.symetrie.hexapod_ui import HexapodUIView
from egse.hexapod.symetrie.joran import JoranController
from egse.hexapod.symetrie.joran import JoranProxy
from egse.hexapod.symetrie.joran_protocol import JoranSimulator
from egse.process import ProcessStatus
from egse.resource import get_resource
from egse.settings import Settings
from egse.system import do_every

MODULE_LOGGER = logging.getLogger(__name__)

# Status LEDs define the number of status leds (length of the list), the description and the
# default color when the LED is on.

STATUS_LEDS = [
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

# The index of the Control LED

CONTROL_ONOFF = 2

ACTUATOR_STATE_LABELS = [
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

SPECIFIC_POSITIONS = ["Position ZERO", "Position RETRACTED"]

GUI_SETTINGS = Settings.load("JORAN GUI")


class TemperatureLog(QWidget):
    """This Widget allows to view the temperature value of all six actuators."""
    def __init__(self, temp: List[str] = None):
        super().__init__()

        self.stripchart = None

        self.temperatures = temp

        # Switch to using white background and black foreground for pyqtgraph stripcharts

        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")

        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Temperature values in C"))
        vbox.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.create_temperature_stripchart_widget = self.create_temperature_stripchart()
        vbox.addWidget(self.create_temperature_stripchart_widget)

        self.create_temperature_box_widget = self.create_temperature_box()
        vbox.addWidget(self.create_temperature_box_widget)

        self.setLayout(vbox)

    def create_temperature_box(self):
        vbox = QVBoxLayout()
        vbox.setSpacing(0)

        for box in range(6):
            wbox = QHBoxLayout()
            wbox.setSpacing(0)
            wbox.addWidget(QLabel(f"Temp.{box + 1}: "))
            wbox.setSpacing(0)
            editbox = QLineEdit()
            editbox.setReadOnly(True)
            editbox.setFixedSize(80, 20)
            wbox.setSpacing(0)
            wbox.addWidget(editbox)
            wbox.setSpacing(0)
            vbox.addLayout(wbox)
            vbox.setSpacing(0)

        create_temperature_box = QGroupBox()
        create_temperature_box.setLayout(vbox)

        return create_temperature_box

    def create_temperature_stripchart(self):
        self.stripchart = StripChart(
            labels={"left": ("measure", "C"), "bottom": ("Time", "d hh:mm:ss")}
        )
        self.stripchart.setInterval(60 * 60 * 12)  # 12h of data
        self.stripchart.set_yrange(0, 40)

        vbox = QVBoxLayout()
        vbox.addStretch(1)
        vbox.addWidget(self.stripchart)

        create_temperature_stripchart = QGroupBox()
        create_temperature_stripchart.setLayout(vbox)

        return create_temperature_stripchart


class JoranUIView(HexapodUIView):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hexapod JORAN Controller")

        self.actuator_states = ActuatorStates(labels=ACTUATOR_STATE_LABELS)

        self.temperature_log = TemperatureLog()

        self.temperature_values = self.temperature_log.create_temperature_box_widget
        self.temperature_values = self.temperature_values.findChildren(QLineEdit)
        for temp in range(len(self.temperature_values)):
            self.temperature_values[temp].setText("0.00")

        self.temperature_stripchart = self.temperature_log.create_temperature_stripchart_widget
        self.temperature_stripchart = self.temperature_stripchart.findChildren(StripChart)
        self.temperature_stripchart = self.temperature_stripchart[0]

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

        self.states = States(STATUS_LEDS)

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

    def updatePositions(self, user_positions, machine_positions, actuator_lengths):

        if user_positions is None:
            MODULE_LOGGER.warning("no userPositions passed into updatePositions(), returning.")
            return

        for upos in range(len(self.user_positions)):
            try:
                self.user_positions[upos][1].setText(f"{user_positions[upos]:10.4f}")
            except IndexError:
                MODULE_LOGGER.error(f"IndexError in user_positions, upos = {upos}")

        if machine_positions is None:
            MODULE_LOGGER.warning("no machinePositions passed into updatePositions(), returning.")
            return

        for mpos in range(len(self.mach_positions)):
            self.mach_positions[mpos][1].setText(f"{machine_positions[mpos]:10.4f}")

        if actuator_lengths is None:
            MODULE_LOGGER.warning("no actuatorLengths passed into updatePositions(), returning.")
            return

        for idx, alen in enumerate(self.actuator_lengths):
            alen[1].setText(f"{actuator_lengths[idx]:10.4f}")

    def updateStates(self, states):

        if states is None:
            return

        self.updateControlButton(states[CONTROL_ONOFF])
        self.states.set_states(states)

    def updateControlButton(self, flag):

        self.control.set_selected(on=flag)

    def updateTemperature(self, temp):
        if temp is None:
            MODULE_LOGGER.warning("no temperature passed into updateTemperature(), returning.")
            return
        else:
            #TODO: How to add the 6 temperature values to the stripchart?
            value = temp[0]
            self.temperature_stripchart.update(QDateTime.currentMSecsSinceEpoch(), value)
            for t in range(len(self.temperature_values)):
                self.temperature_values[t].setText(f"{temp[t]:10.4f}")


class JoranUIModel(HexapodUIModel):
    def __init__(self, connection_type: str):

        if connection_type == "proxy":
            device = JoranProxy()
        elif connection_type == "direct":
            device = JoranController()
            device.connect()
        elif connection_type == "simulator":
            device = JoranSimulator()
        else:
            raise ValueError(
                f"Unknown type of Hexapod implementation passed into the model: {connection_type}"
            )

        super().__init__(connection_type, device)

        if device is not None:
            MODULE_LOGGER.debug(f"Hexapod initialized as {device.__class__.__name__}")

    def get_speed(self):
        speed_settings = self.device.get_speed()
        return speed_settings["vt"], speed_settings["vr"]

    def get_temperature(self):
        temp = self.device.get_temperature()
        return temp


class JoranUIController(HexapodUIController):
    def __init__(self, model: JoranUIModel, view: JoranUIView):
        super().__init__(model, view)

    def update_values(self):

        super().update_values()

        # Add here any updates to JORAN specific widgets

        temp = self.model.get_temperature()
        self.view.updateTemperature(temp)


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
    lock_file = QLockFile(str(Path("~/joran_ui.app.lock").expanduser()))

    styles_location = get_resource(":/styles/default.qss")
    app_logo = get_resource(":/icons/logo-joran.svg")

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
            proxy = JoranProxy()
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

        view = JoranUIView()
        model = JoranUIModel(args.type)
        JoranUIController(model, view)

        view.show()

        return app.exec_()
    else:
        error_message = QMessageBox()
        error_message.setIcon(QMessageBox.Warning)
        error_message.setWindowTitle("Error")
        error_message.setText("The Joran GUI application is already running!")
        error_message.setStandardButtons(QMessageBox.Ok)

        return error_message.exec()


if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

    sys.exit(main())
