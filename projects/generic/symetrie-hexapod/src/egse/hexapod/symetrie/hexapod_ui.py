import logging
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

from PyQt5.QtCore import QEvent
from PyQt5.QtCore import QSize
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QTabWidget
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget

from egse.decorators import deprecate
from egse.gui import show_warning_message
from egse.gui.buttons import ToggleButton
from egse.gui.buttons import TouchButton
from egse.gui.led import LED
from egse.gui.led import ShapeEnum
from egse.observer import Observable
from egse.observer import Observer
from egse.resource import get_resource
from egse.state import UnknownStateError

MODULE_LOGGER = logging.getLogger(__name__)


class VLine(QFrame):
    """Presents a simple Vertical Bar that can be used in e.g. the status bar."""

    def __init__(self):
        super().__init__()
        self.setFrameShape(self.VLine | self.Sunken)


class Container(QWidget):
    """
    An empty container that is used currently as a place-holder for a QWidget that is to be
    implemented.
    """

    def __init__(self, text):
        super().__init__()

        self.hbox = QHBoxLayout()
        self.hbox.setSpacing(0)
        self.hbox.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.hbox)

        self.button = QPushButton(text)
        self.hbox.addWidget(self.button)


class ValidationIcon(QWidget):
    """
    This Icon is used
    """

    def __init__(self):
        super().__init__()

        self._valid = QPixmap(str(get_resource(":/icons/valid.png")))
        self._invalid = QPixmap(str(get_resource(":/icons/invalid.png")))
        self._disabled = QPixmap(str(get_resource(":/icons/unvalid.png")))

        self._label = QLabel()

        self.disable()

        hbox = QHBoxLayout()
        hbox.setSpacing(0)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(self._label)

        self.setLayout(hbox)

    def eventFilter(self, source, event):
        if event.type() == QEvent.FocusOut:
            self.disable()
        return True

    def validate(self):
        self._label.setPixmap(self._valid)

    def invalidate(self):
        self._label.setPixmap(self._invalid)

    def disable(self):
        self._label.setPixmap(self._disabled)
        self._label.setToolTip("No validation was performed.")

    def setToolTip(self, message: str) -> None:
        self._label.setToolTip(message)


class Positioning(QWidget):
    """
    The Positioning widget which allows to manually command the Hexapod to a certain position,
    absolute or relative.
    """

    def __init__(self, view, observable):
        super().__init__()
        self.observable = observable
        self.view = view

        # initialize instance variables used by this class

        self.manual_mode: QGroupBox = None
        self.manual_mode_positions_widget: QFrame = None
        self.manual_mode_positions: List = None

        self.combo_absolute_relative: QComboBox = None

        self.validate_label = None

        self.specific_positions: QGroupBox = None
        self.specific_positions_widget: QFrame = None

        self.init_gui()

    def init_gui(self):
        """Initialize the main user interface for this component."""

        # Setup the Manual Mode GroupBox widget

        hbox = QHBoxLayout()

        self.manual_mode = QGroupBox("Manual Mode")
        self.manual_mode.setLayout(hbox)
        self.manual_mode.setObjectName("ManualModeGroupBox")

        self.manual_mode_positions_widget = self.create_manual_mode_position_widget()

        hbox.addWidget(self.manual_mode_positions_widget)

        # Setup the Specific Positions GroupBox widget

        hbox = QHBoxLayout()

        self.specific_positions = QGroupBox("Specific Positions")
        self.specific_positions.setLayout(hbox)
        self.manual_mode.setObjectName("SpecificPositionsGroupBox")

        self.specific_positions_widget = self.create_specific_positions_widget()

        hbox.addWidget(self.specific_positions_widget)

        # Finally, within the Positions widget, a VBoxLayout holds the manual mode and the
        # specific positions widgets.

        vbox = QVBoxLayout()

        vbox.addWidget(self.manual_mode)
        vbox.addWidget(self.specific_positions)

        self.setLayout(vbox)

    def create_specific_positions_widget(self):
        hbox = QHBoxLayout()

        self.combo_specific_position = QComboBox()
        self.combo_specific_position.addItems(["Position ZERO", "Position RETRACTED"])
        self.combo_specific_position.setMinimumContentsLength(18)
        self.combo_specific_position.adjustSize()

        self.move_to_button = QPushButton("Move To")
        self.move_to_button.setToolTip(
            "Move to the specific position that is selected in the combobox."
            "<ul>"
            "<li><strong>ZERO</strong> moves Tx, Ty, Tz, Rx, Ry, Rz to position 0.0"
            "<li><strong>RETRACTED</strong> moves the hexapod into its smallest height (useful for "
            "loading or storage)"
            "</ul>"
        )
        self.move_to_button.clicked.connect(self.handle_move_to_specific_position)

        hbox.addWidget(self.combo_specific_position)
        hbox.addWidget(self.move_to_button)

        frame = QFrame()
        frame.setObjectName("SpecificPositions")
        frame.setLayout(hbox)

        return frame

    def create_manual_mode_position_widget(self) -> QFrame:
        """Creates the internal frame for the manual mode box."""

        vbox = QVBoxLayout()

        self.manual_mode_positions = [
            [QLabel("X"), QLineEdit(), QLabel("mm")],
            [QLabel("Y"), QLineEdit(), QLabel("mm")],
            [QLabel("Z"), QLineEdit(), QLabel("mm")],
            [QLabel("Rx"), QLineEdit(), QLabel("deg")],
            [QLabel("Ry"), QLineEdit(), QLabel("deg")],
            [QLabel("Rz"), QLineEdit(), QLabel("deg")],
        ]

        for mm_pos in self.manual_mode_positions:
            hbox = QHBoxLayout()
            hbox.addWidget(mm_pos[0])
            hbox.addWidget(mm_pos[1])
            hbox.addWidget(mm_pos[2])
            mm_pos[0].setMinimumWidth(20)
            mm_pos[1].setText("0.0000")
            mm_pos[1].setStyleSheet("QLabel { background-color : LightGray; }")
            mm_pos[1].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            mm_pos[1].setMinimumWidth(50)
            vbox.addLayout(hbox)

        # Add the two buttons, (1) Copy, and (2) Clear

        hbox = QHBoxLayout()

        copy_button = QPushButton("Copy")
        copy_button.setToolTip("Copy the positions from Object [in User].")
        copy_button.clicked.connect(self.handle_copy_positions)

        clear_button = QPushButton("Clear")
        clear_button.setToolTip("Clear the input fields.")
        clear_button.clicked.connect(self.handle_clear_inputs)

        hbox.addWidget(copy_button)
        hbox.addStretch()
        hbox.addWidget(clear_button)

        vbox.addLayout(hbox)

        # Make sure the hboxes defined above stay nicely together when vertically resizing the
        # Frame.

        vbox.addStretch()

        # Add the QComboBox to select either absolute or relative movement

        hbox = QHBoxLayout()

        self.combo_absolute_relative = QComboBox()
        self.combo_absolute_relative.addItems(["Absolute", "Relative object", "Relative user"])
        self.combo_absolute_relative.setMinimumContentsLength(15)
        self.combo_absolute_relative.adjustSize()

        self.move_button = QPushButton("Move")
        self.move_button.setToolTip(
            "When you press this button, the Hexapod will start moving \n"
            "to the position you have given in manual mode above.\n"
            "Depending on the control setting, the movement will be absolute or relative."
        )
        self.move_button.clicked.connect(self.handle_movement)

        hbox.addWidget(self.combo_absolute_relative)
        hbox.addWidget(self.move_button)

        vbox.addLayout(hbox)

        # Add the two buttons, (1) Move, and (2) Validate Movement.

        hbox = QHBoxLayout()

        self.validate_button = QPushButton("Validate Movement...")
        self.validate_button.setToolTip(
            "When you press this button, the Hexapod controller will validate the input position "
            "in manual mode.\n"
            "Depending on the control setting, the movement will be absolute or relative."
        )
        self.validate_button.clicked.connect(self.handle_validate)

        self.validate_label = ValidationIcon()
        self.validate_label.installEventFilter(self.validate_label)

        hbox.addWidget(self.validate_label)
        hbox.addWidget(self.validate_button)

        vbox.addLayout(hbox)

        frame = QFrame()
        frame.setObjectName("ManualPositions")
        frame.setLayout(vbox)

        return frame

    def disable_movement(self):
        self.move_button.setDisabled(True)
        self.move_to_button.setDisabled(True)
        self.validate_button.setDisabled(True)

    def enable_movement(self):
        self.move_button.setEnabled(True)
        self.move_to_button.setEnabled(True)
        self.validate_button.setEnabled(True)

    def set_position_validation_icon(self, error_codes, tooltip: str = None):

        if error_codes:
            self.validate_label.setFocus()
            self.validate_label.invalidate()
            self.validate_label.setToolTip(format_tooltip(tooltip or error_codes))
        else:
            self.validate_label.setFocus()
            self.validate_label.validate()
            self.validate_label.setToolTip("Movement command is valid.")

    def get_manual_inputs(self):
        """Returns the input positions as a list of floats."""
        try:
            pos = [
                float(mm_pos[1].text().replace(",", ".")) for mm_pos in self.manual_mode_positions
            ]
        except ValueError as exc:
            MODULE_LOGGER.error(f"Incorrect manual position input given: {exc}")

            description = "Input errors in manual positions"
            info_text = (
                "Some of the values that you have filled into the manual position fields are "
                "invalid. The fields can only contain floating point numbers, both '.' and ',"
                "' are allowed."
            )
            show_warning_message(description, info_text)

            return None

        return pos

    def handle_move_to_specific_position(self):

        # Check which movement was requested

        selected_text = self.combo_specific_position.currentText()
        if "ZERO" in selected_text:
            action = "goto_zero_position"
            value = 1
        if "RETRACTED" in selected_text:
            action = "goto_retracted_position"
            value = 2

        self.observable.actionObservers({action: value})

    def handle_movement(self):
        # Read out the values in manual mode into an array of floats
        # Users may use comma or point as a decimal delimiter

        pos = self.get_manual_inputs()
        if pos is None:
            return

        # Check which movement was requested

        selected_text = self.combo_absolute_relative.currentText()
        if selected_text == "Absolute":
            movement = "move_absolute"
        elif selected_text == "Relative object":
            movement = "move_relative_object"
        elif selected_text == "Relative user":
            movement = "move_relative_user"

        self.observable.actionObservers({movement: pos})

    def handle_validate(self):
        pos = self.get_manual_inputs()
        if pos is None:
            return

        # Check which movement was requested

        selected_text = self.combo_absolute_relative.currentText()
        if selected_text == "Absolute":
            validation = "check_absolute_movement"
        elif selected_text == "Relative object":
            validation = "check_relative_object_movement"
        elif selected_text == "Relative user":
            validation = "check_relative_user_movement"

        self.observable.actionObservers({validation: pos})

    def handle_copy_positions(self):
        for pos, mm_pos in zip(self.view.user_positions, self.manual_mode_positions):
            mm_pos[1].setText(pos[1].text())

        self.validate_label.disable()
        self.manual_mode_positions_widget.repaint()

    def handle_clear_inputs(self):
        for mm_pos in self.manual_mode_positions:
            mm_pos[1].setText("0.0000")

        self.validate_label.disable()
        self.manual_mode_positions_widget.repaint()


class SpeedSettings(QWidget):

    def __init__(self, view, observable):
        super().__init__()
        self.observable = observable
        self.view = view

        self.set_speed_widget: Optional[QGroupBox] = None
        self.set_speed_widget = self.create_set_speed_widget()

        vbox = QVBoxLayout()

        hbox = QHBoxLayout()
        hbox.addWidget(self.set_speed_widget)
        hbox.addStretch()

        # Add the Fetch and Apply for the Speed to the HBOX here

        vbox_speed = QVBoxLayout()

        fetch_button = QPushButton("Fetch")
        fetch_button.setToolTip("Fetch speed settings from the Controller.")
        fetch_button.clicked.connect(self.handle_fetch_speed_settings)

        apply_button = QPushButton("Apply")
        apply_button.setToolTip("Apply BOTH speed settings to the Controller.")
        apply_button.clicked.connect(self.handle_apply_speed_settings)

        vbox_speed.addWidget(fetch_button)
        vbox_speed.addWidget(apply_button)

        hbox.addLayout(vbox_speed)

        vbox.addLayout(hbox)

        self.setLayout(vbox)

    def create_set_speed_widget(self):
        """Creates the widget for the user set/get speed box."""

        vbox = QVBoxLayout()

        self.user_set_speed = [
            [QLabel("Translation Speed (vt): "), QLineEdit(), QLabel("mm/s")],
            [QLabel("Rotation Speed (vr): "), QLineEdit(), QLabel("°/s")]]

        for speed in self.user_set_speed:
            hbox = QHBoxLayout()
            hbox.addWidget(speed[0])
            hbox.addWidget(speed[1])
            hbox.setSpacing(0)
            hbox.addWidget(speed[2])
            speed[0].setMinimumWidth(150)
            speed[1].setText("0.0000")
            speed[1].setStyleSheet("QLabel { background-color : LightGray; }")
            speed[1].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            speed[1].setFixedWidth(100)
            vbox.addLayout(hbox)

        gbox_set_speed = QGroupBox("Set Speed parameters", self)
        gbox_set_speed.setLayout(vbox)

        return gbox_set_speed

    def get_speed_settings_input(self):

        tr_speed = float(self.user_set_speed[0][1].text())
        rot_speed = float(self.user_set_speed[1][1].text())

        return tr_speed, rot_speed

    def set_speed(self, vt, vr):
        self.user_set_speed[0][1].setText(str(vt))
        self.user_set_speed[1][1].setText(str(vr))
        self.set_speed_widget.repaint()

    def handle_apply_speed_settings(self):

        # Read out the values in the speed settings group

        translation_speed, rotation_speed = self.get_speed_settings_input()

        self.observable.actionObservers({"set_speed": (translation_speed, rotation_speed)})

    def handle_fetch_speed_settings(self):

        self.observable.actionObservers({"fetch_speed": True})


class CoordinateSystems(QWidget):
    """This Widget allow to set the User and Object coordinate systems."""

    def __init__(self, view, observable):
        super().__init__()
        self.observable = observable
        self.view = view

        # initialize instance variables used by this class

        self.user_coordinates_system_widget: QGroupBox = None
        self.user_coordinates_system: List = None

        self.object_coordinates_system_widget: QGroupBox = None
        self.object_coordinates_system: List = None

        self.init_gui()

    def init_gui(self):
        """Initialize the main interface for this component."""

        vbox = QVBoxLayout()

        self.user_coordinates_system_widget = self.create_user_coordinates_system_widget()
        self.object_coordinates_system_widget = self.create_object_coordinates_system_widget()

        # The double arrow buttons are used to copy parameters from user to object coordinate
        # system or vice versa.

        copy_right_icon = QIcon(str(get_resource(":/icons/double-right-arrow.svg")))
        copy_right_button = QPushButton()
        copy_right_button.setIcon(copy_right_icon)
        copy_right_button.setToolTip("Copy User coordinates to Object coordinates")
        copy_right_button.clicked.connect(self.on_copy_right)

        copy_left_icon = QIcon(str(get_resource(":/icons/double-left-arrow.svg")))
        copy_left_button = QPushButton()
        copy_left_button.setIcon(copy_left_icon)
        copy_left_button.setToolTip("Copy Object coordinates to User coordinates")
        copy_left_button.clicked.connect(self.on_copy_left)

        vbox_icons = QVBoxLayout()
        vbox_icons.addStretch()
        vbox_icons.addWidget(copy_left_button)
        vbox_icons.addWidget(copy_right_button)
        vbox_icons.addStretch()

        hbox = QHBoxLayout()

        hbox.addWidget(self.user_coordinates_system_widget)
        hbox.addLayout(vbox_icons)
        hbox.addWidget(self.object_coordinates_system_widget)

        vbox.addLayout(hbox)

        apply_button = QPushButton("Apply")
        apply_button.setToolTip("Apply the Coordinates Systems to the Controller.")
        apply_button.clicked.connect(self.handle_apply_coordinates_systems)

        fetch_button = QPushButton("Fetch")
        fetch_button.setToolTip("Fetch the Coordinates Systems from the Controller.")
        fetch_button.clicked.connect(self.handle_fetch_coordinates_systems)

        hbox = QHBoxLayout()
        hbox.addWidget(fetch_button)
        hbox.addStretch()
        hbox.addWidget(apply_button)
        vbox.addLayout(hbox)

        vbox.addStretch(1)

        self.setLayout(vbox)

    def set_coordinates_systems(self, user_cs, object_cs):
        for usr, value in zip(self.user_coordinates_system, user_cs):
            usr[1].setText(str(value))
        for obj, value in zip(self.object_coordinates_system, object_cs):
            obj[1].setText(str(value))
        self.object_coordinates_system_widget.repaint()
        self.user_coordinates_system_widget.repaint()

    def create_user_coordinates_system_widget(self) -> QWidget:
        """Creates the widget for the user coordinates system box."""

        vbox = QVBoxLayout()

        self.user_coordinates_system = [
            [QLabel("X"), QLineEdit(), QLabel("mm")],
            [QLabel("Y"), QLineEdit(), QLabel("mm")],
            [QLabel("Z"), QLineEdit(), QLabel("mm")],
            [QLabel("Rx"), QLineEdit(), QLabel("deg")],
            [QLabel("Ry"), QLineEdit(), QLabel("deg")],
            [QLabel("Rz"), QLineEdit(), QLabel("deg")],
        ]

        for mm_pos in self.user_coordinates_system:
            hbox = QHBoxLayout()
            hbox.addWidget(mm_pos[0])
            hbox.addWidget(mm_pos[1])
            hbox.addWidget(mm_pos[2])
            mm_pos[0].setMinimumWidth(20)
            mm_pos[1].setText("0.0000")
            mm_pos[1].setStyleSheet("QLabel { background-color : LightGray; }")
            mm_pos[1].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            mm_pos[1].setMinimumWidth(50)
            vbox.addLayout(hbox)

        # Make sure the hboxes defined above stay nicely together when vertically resizing the
        # Frame.

        # vbox.addStretch()

        gbox_user_coordinates_system = QGroupBox("User Coordinate System", self)
        gbox_user_coordinates_system.setLayout(vbox)
        gbox_user_coordinates_system.setToolTip("The User Coordinate System.")

        return gbox_user_coordinates_system

    def create_object_coordinates_system_widget(self) -> QWidget:
        """Creates the widget for the object coordinates system box."""

        vbox = QVBoxLayout()

        self.object_coordinates_system = [
            [QLabel("X"), QLineEdit(), QLabel("mm")],
            [QLabel("Y"), QLineEdit(), QLabel("mm")],
            [QLabel("Z"), QLineEdit(), QLabel("mm")],
            [QLabel("Rx"), QLineEdit(), QLabel("deg")],
            [QLabel("Ry"), QLineEdit(), QLabel("deg")],
            [QLabel("Rz"), QLineEdit(), QLabel("deg")],
        ]

        for mm_pos in self.object_coordinates_system:
            hbox = QHBoxLayout()
            hbox.addWidget(mm_pos[0])
            hbox.addWidget(mm_pos[1])
            hbox.addWidget(mm_pos[2])
            mm_pos[0].setMinimumWidth(20)
            mm_pos[1].setText("0.0000")
            mm_pos[1].setStyleSheet("QLabel { background-color : LightGray; }")
            mm_pos[1].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            mm_pos[1].setMinimumWidth(50)
            vbox.addLayout(hbox)

        # Make sure the hboxes defined above stay nicely together when vertically resizing the
        # Frame.

        # vbox.addStretch()

        gbox_object_coordinates_system = QGroupBox("Object Coordinate System", self)
        gbox_object_coordinates_system.setLayout(vbox)
        gbox_object_coordinates_system.setToolTip("The Object Coordinate System.")

        return gbox_object_coordinates_system

    def on_copy_right(self, icon):
        for usr, obj in zip(self.user_coordinates_system, self.object_coordinates_system):
            obj[1].setText(usr[1].text())
        self.object_coordinates_system_widget.repaint()

    def on_copy_left(self, icon):
        for usr, obj in zip(self.user_coordinates_system, self.object_coordinates_system):
            usr[1].setText(obj[1].text())
        self.user_coordinates_system_widget.repaint()

    def get_coordinates_systems_inputs(self):
        """Returns the values from the user and object coordinates systems as a tuple of two
        lists of floats.

        Returns:
            A tuple containing two lists of floats, the first list for the user coordinates
            system, the second list for the object coordinates system.
        """
        try:
            user_cs = [
                float(pos[1].text().replace(",", ".")) for pos in self.user_coordinates_system
            ]
            object_cs = [
                float(pos[1].text().replace(",", ".")) for pos in self.object_coordinates_system
            ]
        except ValueError as exc:
            MODULE_LOGGER.error(
                f"Incorrect manual input given for user or object coordinates " f"system: {exc}"
            )

            description = "Input errors for coordinates systems"
            info_text = (
                "Some of the values that you have filled into the fields for the coordinates "
                "systems are invalid. The fields can only contain floating point numbers,  "
                "both '.' and ',' are allowed."
            )
            show_warning_message(description, info_text)

            return None, None

        return user_cs, object_cs

    def handle_apply_coordinates_systems(self):

        # Read out the values in manual mode into an array of floats
        # Users may use comma or point as a decimal delimiter

        user_cs, object_cs = self.get_coordinates_systems_inputs()
        if user_cs is None:
            return

        self.observable.actionObservers({"configure_coordinates_systems": (user_cs, object_cs)})

    def handle_fetch_coordinates_systems(self):

        self.observable.actionObservers({"fetch_coordinates_systems": True})


class ActuatorStates(QWidget):
    """This Widget allows to view the state of all six actuators."""
    def __init__(self, labels: List[str] = None):
        super().__init__()

        # initialize instance variables used by this class

        self.status_labels = labels
        self.leds: List[List] = []

        vbox = QVBoxLayout()
        vbox.addWidget(QLabel("Actuator States"))
        vbox.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.create_states_widget = self.create_states()
        vbox.addWidget(self.create_states_widget)
        self.setLayout(vbox)

    def create_states(self):
        vbox = QVBoxLayout()

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(""))

        for actuator_index in range(1, 7):

            actuator_number = QLabel(str(actuator_index))
            actuator_number.setAlignment(Qt.AlignHCenter)
            actuator_number.setMinimumSize(20, 20)
            actuator_number.setMaximumSize(20, 20)
            # LED(self, size=QSize(20, 20), shape=ShapeEnum.SQUARE)
            hbox.addWidget(actuator_number)
            hbox.setSpacing(2)
        vbox.addLayout(hbox)

        for state in self.status_labels:
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel(state))
            actuator_leds = [
                LED(self, size=QSize(20, 20), shape=ShapeEnum.SQUARE)
                for _ in range(6)
            ]
            for led in actuator_leds:
                hbox.addWidget(led)
                hbox.setSpacing(2)
            self.leds.append(actuator_leds)
            vbox.addLayout(hbox)

        create_states = QGroupBox()
        create_states.setLayout(vbox)

        return create_states

    def set_states(self, states: List):

        # States is a List of Lists, each inside list contains a dict with the states and
        # another list with the states.

        # zip(*states) will transpose the states

        for leds, new_states in zip(self.leds, zip(*states)):
            for led, state in zip(leds, new_states):
                led.set_color(state)

    def reset_states(self):
        pass


def format_tooltip(value: Union[str, Dict, List] = None) -> str:
    if value is None:
        return ""

    from rich.console import Console

    console = Console(width=60, force_terminal=False, force_jupyter=False)
    with console.capture() as capture:
        console.print(value)

    return capture.get()


class HexapodUIModel:
    def __init__(self, connection_type: str, device):
        self._connection_type = connection_type
        self._device = device

    @property
    def connection_type(self):
        return self._connection_type

    @property
    def device(self):
        return self._device

    def is_simulator(self):
        return self.device.is_simulator()

    def is_cs_connected(self):
        return self.device.is_cs_connected() if self.connection_type == "proxy" else False

    def is_device_connected(self):
        return self.device.is_connected()

    @deprecate(alternative="reconnect_device")
    def reconnect(self):
        self.reconnect_device()

    def reconnect_device(self):
        self.device.reconnect()
        return self.device.is_connected()

    def reconnect_cs(self):
        self.device.reconnect_cs()
        return self.device.is_cs_connected()

    def disconnect(self):
        self.device.disconnect()

    def disconnect_cs(self):
        self.device.disconnect_cs()

    def has_commands(self):
        if self.connection_type == "proxy":
            return self.device.has_commands()
        return True

    def load_commands(self):
        if self.connection_type == "proxy":
            self.device.load_commands()

    def get_states(self):
        try:
            _, states = self.device.get_general_state()
        except TypeError:
            states = None
        return states

    def configure_coordinates_systems(self, user_cs, object_cs):
        return self.device.configure_coordinates_systems(*user_cs, *object_cs)

    def get_coordinates_systems(self):
        response = self.device.get_coordinates_systems()
        user_cs = response[:6]
        object_cs = response[6:]
        return user_cs, object_cs

    def get_user_positions(self):
        return self.device.get_user_positions()

    def get_machine_positions(self):
        return self.device.get_machine_positions()

    def get_actuator_length(self):
        return self.device.get_actuator_length()

    def get_actuator_states(self):
        states = self.device.get_actuator_state()
        states = [x[1] for x in states]
        return states

    def get_speed(self):
        raise NotImplementedError

    def activate_control_loop(self):
        self.device.activate_control_loop()

    def deactivate_control_loop(self):
        self.device.deactivate_control_loop()

    def check_absolute_movement(self, pos):
        rc, rc_dict = self.device.check_absolute_movement(*pos)
        MODULE_LOGGER.debug(rc)
        MODULE_LOGGER.debug(rc_dict)
        return rc_dict

    def check_relative_object_movement(self, pos):
        rc, rc_dict = self.device.check_relative_object_movement(*pos)
        MODULE_LOGGER.debug(rc)
        MODULE_LOGGER.debug(rc_dict)
        return rc_dict

    def check_relative_user_movement(self, pos):
        rc, rc_dict = self.device.check_relative_user_movement(*pos)
        MODULE_LOGGER.debug(rc)
        MODULE_LOGGER.debug(rc_dict)
        return rc_dict

    def move_absolute(self, pos):
        self.device.move_absolute(*pos)

    def move_relative_object(self, pos):
        self.device.move_relative_object(*pos)

    def move_relative_user(self, pos):
        self.device.move_relative_user(*pos)

    def goto_zero_position(self):
        self.device.goto_zero_position()

    def goto_retracted_position(self):
        self.device.goto_retracted_position()

    def set_speed(self, tr_speed, rot_speed):
        self.device.set_speed(tr_speed, rot_speed)

    def homing(self):
        self.device.homing()

    def clear_error(self):
        self.device.clear_error()

    def reset(self):
        self.device.reset()

    def stop(self):
        self.device.stop()


class HexapodUIController(Observer):
    def __init__(self, model: HexapodUIModel, view):
        self._model = model
        self._view = view
        self._view.addObserver(self)

        self.states_capture_timer = None
        self.timer_interval = 200
        self.create_timer()

        try:
            if self.model.is_device_connected():
                mode = self.model.connection_type.capitalize()
                if self.model.is_simulator():
                    mode = f"{mode} [Simulator]"
                self.view.update_status_bar(mode=mode)

                self.view.check_device_action()
            else:
                self.view.uncheck_device_action()

            if self.model.is_cs_connected():
                self.view.check_cs_action()
            else:
                self.view.uncheck_cs_action()

            MODULE_LOGGER.info(f"{self.model.is_device_connected()=}, {self.model.is_cs_connected()=}")

            if model.connection_type in ["direct", "simulator"]:
                view.disable_cs_action()

            if self.has_connection():
                self.view.set_connection_state("connected")
                self.start_timer()
            else:
                self.view.set_connection_state("disconnected")
                self.stop_timer()
        except NotImplementedError:
            MODULE_LOGGER.warning(
                "There was no connection to the control server during startup, "
                "GUI starts in disconnected mode."
            )
            self.view.uncheck_cs_action()
            self.view.uncheck_device_action()
            self.view.set_connection_state("disconnected")

    def has_connection(self):
        """
        Returns True if the controller has a connection to the device. This takes into account
        that the control server might be disabled when the controller is directly connected to
        the device or to a simulator.
        """
        if self.view.is_cs_action_enabled():
            return bool(self.model.is_device_connected() and self.model.is_cs_connected())
        else:
            return bool(self.model.is_device_connected())

    @property
    def model(self):
        return self._model

    @property
    def view(self):
        return self._view

    def create_timer(self):
        """Create a Timer that will update the States every second."""

        self.states_capture_timer = QTimer()
        # This is only needed when the Timer needs to run in another Thread
        # self.states_capture_timer.moveToThread(self)
        self.states_capture_timer.timeout.connect(self.update_values)
        self.states_capture_timer.setInterval(self.timer_interval)

    def start_timer(self):
        self.states_capture_timer.start()

    def stop_timer(self):
        self.states_capture_timer.stop()

    def update_values(self):
        """Updates the common view widgets."""

        if not self.has_connection():
            self.view.set_connection_state("disconnected")
            self.stop_timer()

            if not self.model.is_device_connected():
                self.view.disable_device_action()
            if not self.model.is_cs_connected():
                self.view.uncheck_cs_action()

            return

        states = self.model.get_states()

        if states:
            self.view.updateStates(states)

        actuator_states = self.model.get_actuator_states()
        self.view.update_actuator_states(actuator_states)

        upos = self.model.get_user_positions()
        mpos = self.model.get_machine_positions()
        alen = self.model.get_actuator_length()

        # the updatePositions() checks for None, no need to do that here

        self.view.updatePositions(upos, mpos, alen)

    def update(self, changed_object):

        text = changed_object.text()

        if text == "STOP":
            self.model.stop()

        if text == "INFO":
            self.help_window.show()

        if text == "DEVICE-CONNECT":
            print(f"Pressed {text}")

            if changed_object.is_selected():
                MODULE_LOGGER.debug("Reconnecting the Hexapod model.")
                if self.model.reconnect_device():
                    self.view.set_connection_state("connected")
                    if not self.model.has_commands():
                        self.model.load_commands()
                    self.start_timer()
                else:
                    self.view.device_connection.set_selected(False)
            else:
                MODULE_LOGGER.debug("Disconnecting the Hexapod model.")
                self.stop_timer()
                self.model.disconnect()
                self.view.set_connection_state("disconnected")
            return

        if text == "CS-CONNECT":
            if changed_object.is_selected():
                MODULE_LOGGER.debug("Reconnecting the Hexapod Control Server.")
                self.model.reconnect_cs()
                if not self.model.has_commands():
                    self.model.load_commands()
                self.start_timer()
                if self.model.is_device_connected() and self.model.is_cs_connected():
                    self.view.set_connection_state("connected")
                    self.view.device_connection.enable()
            else:
                MODULE_LOGGER.debug("Disconnecting the Hexapod Control Server.")
                self.stop_timer()
                self.model.disconnect_cs()
                self.view.device_connection.disable()
                self.view.set_connection_state("disconnected")

        if text == "CONTROL":
            if changed_object.is_selected():
                self.model.activate_control_loop()
            else:
                self.model.deactivate_control_loop()

        if text == "HOMING":
            self.model.homing()

        if text == "CLEAR-ERRORS":
            self.model.clear_error()

        if text == "Reset":
            # FIXME: This causes a problem in the GUI EventLoop as the reset waits for 30 seconds
            #        before it finishes. This will hang the EventLoop for 30 seconds with a spinning
            #        wheel. Do we need to run the hexapod commands (or some) in a separate thread?
            #        Other commands like move to position will also take some time and cause the GUI
            #        to apear hanging...
            #
            #        It is known that time.sleep() should not be used in GUI applications.
            #        Use QTimer.singleShot() instead.

            self.model.reset()

    def do(self, actions):

        for action, value in actions.items():
            MODULE_LOGGER.debug(f"do {action} with {value}")
            if action == "move_absolute":
                self.model.move_absolute(value)
                self.view.update_status_bar(message=f"command: {action}{value}")
            elif action == "move_relative_object":
                self.model.move_relative_object(value)
                self.view.update_status_bar(message=f"command: {action}{value}")
            elif action == "move_relative_user":
                self.model.move_relative_user(value)
                self.view.update_status_bar(message=f"command: {action}{value}")
            elif action == "check_absolute_movement":
                rc_dict = self.model.check_absolute_movement(value)
                self.view.update_status_bar(message=f"command: {action}{value}")
                self.view.positioning.set_position_validation_icon(rc_dict)
            elif action == "check_relative_object_movement":
                rc_dict = self.model.check_relative_object_movement(value)
                self.view.update_status_bar(message=f"command: {action}{value}")
                self.view.positioning.set_position_validation_icon(rc_dict)
            elif action == "check_relative_user_movement":
                rc_dict = self.model.check_relative_user_movement(value)
                self.view.update_status_bar(message=f"command: {action}{value}")
                self.view.positioning.set_position_validation_icon(rc_dict)
            elif action == "set_speed":
                tr_speed, rot_speed = value
                MODULE_LOGGER.info(f"Set speed: {tr_speed=}, {rot_speed=}")
                self.model.set_speed(tr_speed, rot_speed)
            elif action == "fetch_speed":
                tr_speed, rot_speed = self.model.get_speed()
                self.view.set_speed(tr_speed, rot_speed)
            elif action == "goto_zero_position":
                self.model.goto_zero_position()
            elif action == "goto_retracted_position":
                self.model.goto_retracted_position()
            elif action == "configure_coordinates_systems":
                self.model.configure_coordinates_systems(*value)
            elif action == "fetch_coordinates_systems":
                user_cs, object_cs = self.model.get_coordinates_systems()
                self.view.set_coordinates_systems(user_cs, object_cs)
            else:
                MODULE_LOGGER.warning(f"Unknown action {action}")


class HexapodUIView(QMainWindow, Observable):
    def __init__(self):
        super().__init__()

        self.setGeometry(300, 300, 300, 200)

        self.mode_label = QLabel("")
        self.user_positions = None

        # Widget for Manual Positioning, Configuration TAB

        self.positioning = None
        self.configuration = None

        self.coordinate_systems: CoordinateSystems = None
        self.speed_settings = None

        # Widget for the Advanced TAB

        self.actuator_states = None

        # Widget fot the temperature log TAB

        self.temperature_log = None

    def on_click(self, icon: Union[QIcon, bool]):

        sender = self.sender()

        MODULE_LOGGER.log(0, f"type(sender) = {type(sender)}")
        MODULE_LOGGER.log(0, f"sender.text() = {sender.text()}")
        MODULE_LOGGER.log(0, f"sender.isCheckable() = {sender.isCheckable()}")
        MODULE_LOGGER.log(0, f"sender.isChecked() = {sender.isChecked()}")
        MODULE_LOGGER.log(0, f"type(icon) = {type(icon)}")

        # This will trigger the update() method on all the observers

        self.notifyObservers(sender)

    def create_status_bar(self):

        self.statusBar().setStyleSheet("border: 0; background-color: #FFF8DC;")
        self.statusBar().setStyleSheet("QStatusBar::item {border: none;}")
        self.statusBar().addPermanentWidget(VLine())
        self.statusBar().addPermanentWidget(self.mode_label)

    def create_toolbar(self):

        # The Switch On/OFF is in this case used for the Control ON/OFF action.

        self.control = ToggleButton(
            name="CONTROL",
            status_tip="enable-disable the control loop on the servo motors",
            selected=get_resource(":/icons/switch-on.svg"),
            not_selected=get_resource(":/icons/switch-off.svg"),
            disabled=get_resource(":/icons/switch-disabled.svg")
        )
        self.control.clicked.connect(self.on_click)

        # The Home action is used to command the Homing to the Hexapod.

        self.homing = TouchButton(
            name="HOMING",
            status_tip="perform a homing operation",
            selected=get_resource(":/icons/home.svg"),
            disabled=get_resource(":/icons/home-disabled.svg"),
        )
        self.homing.clicked.connect(self.on_click)

        # The Clear action is used to command the ClearErrors to the Hexapod.

        self.clear_errors = TouchButton(
            name="CLEAR-ERRORS",
            status_tip="clear the error list on the controller",
            selected=get_resource(":/icons/erase.svg"),
            disabled=get_resource(":/icons/erase-disabled.svg"),
        )
        self.clear_errors.clicked.connect(self.on_click)

        # The Reconnect action is used to reconnect to the control server

        self.cs_connection = ToggleButton(
            name="CS-CONNECT",
            status_tip="connect-disconnect hexapod control server.",
            selected=get_resource(":/icons/cs-connected.svg"),
            not_selected=get_resource(":/icons/cs-not-connected.svg"),
            disabled=get_resource(":/icons/cs-connected-disabled.svg")
        )
        self.cs_connection.clicked.connect(self.on_click)

        # The Reconnect action is used to reconnect the device

        self.device_connection = ToggleButton(
            name="DEVICE-CONNECT",
            status_tip="connect-disconnect the hexapod controller",
            selected=get_resource(":/icons/plugged.svg"),
            not_selected=get_resource(":/icons/unplugged.svg"),
            disabled=get_resource(":/icons/plugged-disabled.svg")
        )
        self.device_connection.clicked.connect(self.on_click)


        # The STOP button is used to immediately stop the current motion

        stop_button = QIcon(str(get_resource(":/icons/stop.svg")))

        self.stop_action = QAction(stop_button, "STOP", self)
        self.stop_action.setToolTip("STOP Movement")
        self.stop_action.triggered.connect(self.on_click)

        # The HELP button is used to show the on-line help in a browser window

        help_button = QIcon(str(get_resource(":/icons/info.svg")))

        self.help_action = QAction(help_button, "INFO", self)
        self.help_action.setToolTip("Browse the on-line documentation")
        self.help_action.triggered.connect(self.on_click)

        # spacer widget to help with aligning STOP button to the right

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.toolbar = self.addToolBar("MainToolbar")
        self.toolbar.addWidget(self.control)
        self.toolbar.addWidget(self.homing)
        self.toolbar.addWidget(self.clear_errors)
        self.toolbar.addWidget(self.device_connection)
        self.toolbar.addWidget(self.cs_connection)
        self.toolbar.addWidget(spacer)
        self.toolbar.addAction(self.stop_action)
        self.toolbar.addAction(self.help_action)

        return self.toolbar

    def create_user_position_widget(self):

        vbox_labels = QVBoxLayout()
        vbox_values = QVBoxLayout()
        vbox_units = QVBoxLayout()
        hbox = QHBoxLayout()

        self.user_positions = [
            [QLabel("X"), QLabel(), QLabel("mm")],
            [QLabel("Y"), QLabel(), QLabel("mm")],
            [QLabel("Z"), QLabel(), QLabel("mm")],
            [QLabel("Rx"), QLabel(), QLabel("deg")],
            [QLabel("Ry"), QLabel(), QLabel("deg")],
            [QLabel("Rz"), QLabel(), QLabel("deg")],
        ]

        for upos in self.user_positions:
            vbox_labels.addWidget(upos[0])
            vbox_values.addWidget(upos[1])
            upos[1].setStyleSheet("QLabel { background-color : LightGrey; }")
            upos[1].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            upos[1].setMinimumWidth(80)
            vbox_units.addWidget(upos[2])

        # Make sure the labels stay nicely together when vertically resizing the Frame.
        vbox_labels.addStretch(1)
        vbox_values.addStretch(1)
        vbox_units.addStretch(1)

        hbox.addLayout(vbox_labels)
        hbox.addLayout(vbox_values)
        hbox.addLayout(vbox_units)

        # Make sure the leds and labels stay nicely together when horizontally resizing the Frame.
        hbox.addStretch(1)

        gbox_positions = QGroupBox("Object [in User]", self)
        gbox_positions.setLayout(hbox)
        gbox_positions.setToolTip(
            "The position of the Object Coordinate System in the User Coordinate System."
        )

        return gbox_positions

    def create_machine_position_widget(self):

        vbox_labels = QVBoxLayout()
        vbox_values = QVBoxLayout()
        vbox_units = QVBoxLayout()
        hbox = QHBoxLayout()

        self.mach_positions = [
            [QLabel("X"), QLabel(), QLabel("mm")],
            [QLabel("Y"), QLabel(), QLabel("mm")],
            [QLabel("Z"), QLabel(), QLabel("mm")],
            [QLabel("Rx"), QLabel(), QLabel("deg")],
            [QLabel("Ry"), QLabel(), QLabel("deg")],
            [QLabel("Rz"), QLabel(), QLabel("deg")],
        ]

        for mpos in self.mach_positions:
            vbox_labels.addWidget(mpos[0])
            vbox_values.addWidget(mpos[1])
            mpos[1].setStyleSheet("QLabel { background-color : LightGrey; }")
            mpos[1].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            mpos[1].setMinimumWidth(80)
            vbox_units.addWidget(mpos[2])

        # Make sure the labels stay nicely together when vertically resizing the Frame.
        vbox_labels.addStretch(1)
        vbox_values.addStretch(1)
        vbox_units.addStretch(1)

        hbox.addLayout(vbox_labels)
        hbox.addLayout(vbox_values)
        hbox.addLayout(vbox_units)

        # Make sure the leds and labels stay nicely together when horizontally resizing the Frame.
        hbox.addStretch(1)

        gbox_positions = QGroupBox("Platform [in Machine]", self)
        gbox_positions.setLayout(hbox)
        gbox_positions.setToolTip(
            "The position of the Platform Coordinate System in the Machine Coordinate System."
        )

        return gbox_positions

    def create_actuator_length_widget(self):

        vbox_labels = QVBoxLayout()
        vbox_values = QVBoxLayout()
        vbox_units = QVBoxLayout()
        hbox = QHBoxLayout()

        self.actuator_lengths = [
            [QLabel("L1"), QLabel(), QLabel("mm")],
            [QLabel("L2"), QLabel(), QLabel("mm")],
            [QLabel("L3"), QLabel(), QLabel("mm")],
            [QLabel("L4"), QLabel(), QLabel("mm")],
            [QLabel("L5"), QLabel(), QLabel("mm")],
            [QLabel("L6"), QLabel(), QLabel("mm")],
        ]

        for alength in self.actuator_lengths:
            vbox_labels.addWidget(alength[0])
            vbox_values.addWidget(alength[1])
            alength[1].setStyleSheet("QLabel { background-color : LightGrey; }")
            alength[1].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            alength[1].setMinimumWidth(80)
            vbox_units.addWidget(alength[2])

        # Make sure the labels stay nicely together when vertically resizing the Frame.
        vbox_labels.addStretch(1)
        vbox_values.addStretch(1)
        vbox_units.addStretch(1)

        hbox.addLayout(vbox_labels)
        hbox.addLayout(vbox_values)
        hbox.addLayout(vbox_units)

        # Make sure the leds and labels stay nicely together when horizontally resizing the Frame.
        hbox.addStretch(1)

        gbox_lengths = QGroupBox("Actuator Length", self)
        gbox_lengths.setLayout(hbox)

        return gbox_lengths

    def create_tabbed_widget(self):

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.setMovable(False)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)

        self.positioning = Positioning(self, self)
        self.tabs.addTab(self.positioning, "Positions")
        self.coordinate_systems = CoordinateSystems(self, self)
        self.speed_settings = SpeedSettings(self, self)
        self.configuration = QWidget()
        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.addWidget(self.coordinate_systems)
        vbox.addWidget(self.speed_settings)
        self.configuration.setLayout(vbox)
        self.tabs.addTab(self.configuration, "Configuration")
        self.tabs.currentChanged.connect(self.reload_settings_for_tab)

        # Actuator states are initialised in the sub-class because the states are different
        # for the Alpha and Aplha+ controllers

        self.tabs.addTab(self.actuator_states, "Advanced State")

        self.tabs.addTab(self.temperature_log, "Temperature Log")

        return self.tabs

    def reload_settings_for_tab(self, tab_idx):
        MODULE_LOGGER.info(f"Reload for tab: {tab_idx}")
        if self.configuration is self.tabs.widget(tab_idx):
            self.coordinate_systems.handle_fetch_coordinates_systems()
            self.speed_settings.handle_fetch_speed_settings()

    def set_coordinates_systems(self, user_cs, object_cs):
        self.coordinate_systems.set_coordinates_systems(user_cs, object_cs)

    def set_speed(self, vt, vr):
        self.speed_settings.set_speed(vt, vr)

    def is_cs_action_enabled(self):
        return self.cs_connection.isEnabled()

    def disable_cs_action(self):
        self.cs_connection.disable()

    def enable_cs_action(self):
        self.cs_connection.enable()

    def check_cs_action(self):
        self.cs_connection.set_selected()

    def uncheck_cs_action(self):
        self.cs_connection.set_selected(False)

    def disable_device_action(self):
        self.device_connection.disable()

    def enable_device_action(self):
        self.device_connection.enabled()

    def check_device_action(self):
        self.device_connection.set_selected()

    def uncheck_device_action(self):
        self.device_connection.set_selected(False)

    def set_connection_state(self, state):
        # enable or disable all actions that involve a device or cs connection
        # don't change the action buttons for the device nor the cs, that is handled
        # in the caller because it might be a device connection loss that causes this state
        # or a control server, or both...

        MODULE_LOGGER.info(f"{state=}")

        if state == "connected":
            self.control.enable()
            self.homing.enable()
            self.clear_errors.enable()
            self.positioning.enable_movement()
        elif state == "disconnected":
            self.control.disable()
            self.homing.disable()
            self.clear_errors.disable()
            self.positioning.disable_movement()
        else:
            raise UnknownStateError(
                f"Unknown State ({state}), expected 'connected' or 'disconnected'."
            )

    def update_actuator_states(self, states):
        if states is None:
            return

        self.actuator_states.set_states(states)
