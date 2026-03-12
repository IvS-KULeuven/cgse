import inspect
import multiprocessing
import threading
import types
from pathlib import Path
from typing import Union, Any, Callable

import sys
import typer
from PyQt5.QtCore import QLockFile
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QComboBox,
    QLineEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
)

from egse.ariel.tcu import (
    TcuMode,
    NUM_M2MD_AXES,
    NUM_M2MD_POSITIONS,
    NUM_TSM_PROBES_PER_FRAME,
    NUM_TSM_FRAMES,
    AXIS_VELOCITY,
)
from egse.ariel.tcu.tcu import TcuInterface, TcuHex, TcuProxy
from egse.ariel.tcu.tcu_cs import is_tcu_cs_active
from egse.gui import QHLine
from egse.log import logging
from egse.observer import Observable, Observer
from egse.process import ProcessStatus
from egse.resource import get_resource
from egse.response import Failure
from egse.settings import Settings
from egse.system import do_every

MODULE_LOGGER = logging.getLogger(__name__)
TCU_COMPONENTS = ["GENERAL", "M2MD", "TSM", "HK"]
CTRL_SETTINGS = Settings.load("Ariel TCU Controller")

app = typer.Typer()


class TcuUIModel:
    """Model in the MVC pattern that makes the TCU UI application."""

    def __init__(self):
        """Initialisation of the TCU UI Model."""

        # This is used to generate the hex string that is sent to the Arduino, so it can be shown in the TCU UI
        # (Might be discontinued in the future)

        self.tcu_hex = TcuHex()

        # This is used to establish a connection to the TCU and actually send commands to it

        try:
            self.tcu_proxy: TcuProxy[TcuHex, None] = TcuProxy()
        except RuntimeError:
            MODULE_LOGGER.error("Could not connect to Ariel TCU Control Server")
            self.tcu_proxy: Union[TcuProxy, None] = None

    @staticmethod
    def build_dyn_cmds_list() -> dict:
        """Keep track of which dynamic commands have been defined.

        Per component of the TCU, we store a dictionary of the dynamic commands that have been defined for that
        component.  The keys in these dictionaries are the names of the dynamic commands, and the values are the
        functions that implement them.

        Returns:
            Dictionary that stores - per component of the TCU - a dictionary of the dynamic commands that have been
            defined for that component.
        """

        dyn_cmds = {}
        for component in TCU_COMPONENTS:
            dyn_cmds[component] = {}

        for cmd_name, func in inspect.getmembers(TcuInterface, inspect.isfunction):
            if hasattr(func, "target_comp"):
                target_comp = getattr(func, "target_comp")
                dyn_cmds[target_comp][cmd_name] = func

        return dyn_cmds


class TcuUiView(QMainWindow, Observable):
    """View in the MVC pattern that makes the TCU UI application."""

    def __init__(self):
        """Initialisation of the TCU UI View."""

        super(TcuUiView, self).__init__()
        Observable.__init__(self)

        self.setGeometry(300, 300, 500, 300)
        self.setWindowTitle("Telescope Control Unit")

        # Central widget = tabs per component

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

    def build_tabs(self, dyn_cmds: dict, observer):
        """Build the tabs of the TCU UI view.

        For each component of the TCU commanding, a tab is created.  In this tab, you can find:

            - Drop-down menu with the list of available dynamic commands for the component,
            - If applicable: entry for cargo1,
            - If applicable: entry for cargo2,
            - "Run" button,
            - Command string (read-only),
            - Response (read-only).

        Args:
            dyn_cmds (dict): Dictionary that stores - per component of the TCU - a dictionary of the dynamic commands
                             that have been defined for that component.
            observer: Observer that will be notified when a command is run (i.e. when the "Run" button is clicked).
        """

        for tab_name, dyn_cmd_for_tab in dyn_cmds.items():
            tab = TabWidget(dyn_cmd_for_tab)
            tab.add_observer(observer)

            self.tabs.addTab(tab, tab_name)

        # When all tabs have been populated, select the first dynamic command in the drop-down menu in the first tab,
        # to make sure that the correct input parameters are requested (if applicable)

        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.on_tab_changed(0)

    def on_tab_changed(self, _):
        """Takes action when another tab is selected.

        When a new tab has been selected, select the current dynamic command in the drop-down menu in the new tab,
        to make sure that the correct input parameters are requested (if applicable).
        """

        self.tabs.currentWidget().dyn_cmd_drop_down_menu_changed(
            self.tabs.currentWidget().dyn_cmd_drop_down_menu.currentText()
        )


class TabWidget(QWidget, Observable):
    """Tab in the TCU UI View."""

    def __init__(self, dyn_cmds: dict):
        """Initialisation of a tab in the TCU UI View.

        In this tab, you can find:

            - Drop-down menu with the list of available dynamic commands for the component,
            - If applicable: entry for cargo1,
            - If applicable: entry for cargo2,
            - "Run" button,
            - Command string (read-only),
            - Response (read-only).

        Args:
            dyn_cmds (dict): Dictionary that stores for one TCU component a dictionary of the dynamic commands
                             that have been defined for that component.
        """

        super().__init__()
        layout = QVBoxLayout(self)

        # Dynamic commands that are available for this component
        # (i.e. the dictionary of dynamic commands that have been defined for this component)

        self.dyn_cmds = dyn_cmds

        # Entries for cargo1 and/or cargo2 (if applicable)
        # We have to define these before we create the drop-down menu with the dynamic commands

        self.cargo1_layout = CargoLayout(1)
        self.cargo2_layout = CargoLayout(2)

        # Drop-down menu with the list of dynamic commands that are available for this component

        self.dyn_cmd_drop_down_menu = QComboBox()

        for cmd_name in self.dyn_cmds:
            self.dyn_cmd_drop_down_menu.addItem(cmd_name)
        self.dyn_cmd_drop_down_menu.currentTextChanged.connect(self.dyn_cmd_drop_down_menu_changed)

        # Button to send the command to the Arduino

        button = QPushButton("Run")
        button.clicked.connect(self.button_clicked)

        # Display the hex string tha is sent to the Arduino

        cmd_string_layout = QHBoxLayout()
        self.cmd_string = QLineEdit()
        self.cmd_string.setReadOnly(True)
        cmd_string_layout.addWidget(QLabel("Command string"))
        cmd_string_layout.addWidget(self.cmd_string)

        # Display the response that is received from the Arduino
        # (after the command has been sent by clicking the "Run" button)

        response_layout = QHBoxLayout()
        self.response = QLineEdit()
        self.response.setReadOnly(True)
        response_layout.addWidget(QLabel("Response"))
        response_layout.addWidget(self.response)

        # Assembly of all components in the tab

        layout.addWidget(self.dyn_cmd_drop_down_menu)  # Drop-down menu with available dynamic commands
        layout.addLayout(self.cargo1_layout)  # Cargo1
        layout.addLayout(self.cargo2_layout)  # Cargo2
        layout.addWidget(button)  # "Run" button
        layout.addWidget(QHLine())  # Horizontal separator
        layout.addLayout(cmd_string_layout)  # Hex string that is sent to the Arduino
        layout.addWidget(QHLine())  # Horizontal separator
        layout.addLayout(response_layout)  # Response that is received from the Arduino

    def dyn_cmd_drop_down_menu_changed(self, dyn_cmd_name):
        """Takes action when another dynamic command has been selected in the drop-down menu.

        Args:
            dyn_cmd_name (str): Name of the dynamic command that has been selected in the drop-down menu.
        """

        # Extract the signature of the selected function (1st item is always `self`)

        signature = inspect.signature(self.dyn_cmds[dyn_cmd_name])
        parameters = signature.parameters

        # `self` + cargo1 + cargo2 (the latter two may have a different name -> extract from signature)

        if len(parameters) == 3:
            self.cargo1_layout.set_visible(True)
            self.cargo1_layout.update_entry(list(parameters.keys())[-2])
            self.cargo2_layout.set_visible(True)
            self.cargo2_layout.update_entry(list(parameters.keys())[-1])

        # `self` + cargo2 (the latter may have a different name -> extract from signature)

        elif len(parameters) == 2:
            self.cargo1_layout.set_visible(False)
            self.cargo2_layout.set_visible(True)
            self.cargo2_layout.update_entry(list(parameters.keys())[-1])

        # `self` (no cargo)

        else:
            self.cargo1_layout.set_visible(False)
            self.cargo2_layout.set_visible(False)

        self.repaint()

    def button_clicked(self):
        """Takes action when the "Run" button is clicked.

        When the "Run" button is clicked, the observer (i.c. TCU UI Controller) is notified.  It will receive a tuple
        with the following information:

            - The tab widget in which the "Run" button has been clicked (needed to be able to fill out the response),
            - The dynamic command that has been selected in the drop-down menu (function),
            - The cargo1 value (if applicable),
            - The cargo2 value (if applicable).

        The TCU UI Controller will make sure that the hex string that is sent to the Arduino and the response that is
        received from the Arduino are displayed in the UI.  It will receive this information from the TCU UI Model.
        """

        self.notify_observers(
            (
                self,  # Tab widget in which the "Run" button has been clicked
                self.dyn_cmds[self.dyn_cmd_drop_down_menu.currentText()],  # Selected dynamic command (as a function)
                self.cargo1_layout.entry.text(),  # Cargo1 entry
                self.cargo2_layout.entry.text(),  # Cargo2 entry
            )
        )


class CargoLayout(QHBoxLayout):
    """Layout for the input argument(s) of the dynamic commands."""

    def __init__(self, cargo: int):
        """Initialisation of a layout for the given cargo argument (1 or 2).

        Args:
            cargo (int): Number of the cargo argument (1 or 2).
        """

        super().__init__()

        # Label for the argument ("cargo1" / "cargo2", depending on the input, as default)

        self.label = QLabel(f"cargo{cargo}")

        # By default, the entry is a QLineEdit

        self.entry = QLineEdit()

        self.addWidget(self.label)
        self.addWidget(self.entry)

    def update_entry(self, cargo_name: str):
        """Update the entry for the input argument with the given name.

        Updating the entry entails:

            - Updating the label with the name of the input argument,
            - Replacing the entry with the appropriate widget (this can be a line edit, a combo box, etc.).

        Args:
            cargo_name (str): Name of the input argument.
        """

        # Update the name of the input argument

        self.label.setText(cargo_name)

        # The `axis` argument is only used for M2MD commands, to denote the axis that should be commanded
        # -> Use a drop-down menu instead of the default QLineEdit

        if cargo_name == "axis":
            self.replace_entry_with_axis()

        # The `tcu_mode` argument is only used to change the TCU mode
        # -> Use a drop-down menu instead of the default QLineEdit

        elif cargo_name == "tcu_mode":
            self.replace_with_tcu_mode()

        # The `position` argument is only used for `sw_rs_xx_sw_rise` and `sw_rs_xx_sw_fall`, to denote the position
        # that should be commanded
        # -> Use a drop-down menu instead of the default QLineEdit (read the number of positions from the settings)

        elif cargo_name == "position":
            self.replace_with_int_combo_box(1, NUM_M2MD_POSITIONS)

        # The `probe` argument is only used for `tsm_adc_value_xx_currentn`, `tsm_adc_value_xx_biasn`,
        # `tsm_adc_value_xx_currentp`, and `tsm_adc_value_xx_biasp`
        # -> Use a drop-down menu instead of the default QLineEdit (read the number of probes from the settings)

        elif cargo_name == "probe":
            self.replace_with_int_combo_box(1, NUM_TSM_FRAMES * NUM_TSM_PROBES_PER_FRAME)

        elif cargo_name == "speed":
            self.replace_with_axis_speed_combo_box()

        # By default, the entry is a QLineEdit

        else:
            self.replace_with_line_edit()

    def replace_with_line_edit(self):
        """Replaces the entry with a QLineEdit (if it's not a QLineEdit already)."""

        if not isinstance(self.entry, QLineEdit):
            # Remove the current entry

            self.removeWidget(self.entry)
            self.entry.hide()
            self.entry.deleteLater()

            # Replace it with a QLineEdit

            self.entry = QLineEdit()
            self.insertWidget(1, self.entry)

    def replace_entry_with_axis(self):
        """Replaces the entry with an AxisComboBox (if it's not an AxisComboBox already)."""

        if not isinstance(self.entry, AxisComboBox):
            # Remove the current entry

            self.removeWidget(self.entry)
            self.entry.hide()
            self.entry.deleteLater()

            # Replace it with an AxisComboBox

            self.entry = AxisComboBox()
            self.insertWidget(1, self.entry)

    def replace_with_tcu_mode(self):
        """Replaces the entry with a TcuModeComboBox (if it's not a TcuModeComboBox already)."""

        if not isinstance(self.entry, TcuModeComboBox):
            # Remove the current entry

            self.removeWidget(self.entry)
            self.entry.hide()
            self.entry.deleteLater()

            # Replace it with a TcuModeComboBox

            self.entry = TcuModeComboBox()
            self.insertWidget(1, self.entry)

    def replace_with_int_combo_box(self, min_value: int, max_value: int):
        """Replaces the entry with an IntComboBox (if it's not an IntComboBox already).

        Args:
            min_value (int): Minimum value of the IntComboBox.
            max_value (int): Maximum value of the IntComboBox.
        """

        # Remove the current entry

        self.removeWidget(self.entry)
        self.entry.hide()
        self.entry.deleteLater()

        # Replace it with an IntComboBox

        self.entry = IntComboBox(min_value, max_value)
        self.insertWidget(1, self.entry)

    def replace_with_axis_speed_combo_box(self):
        """Replaces the entry with an AxisSpeedComboBox (if it's not an AxisSpeedComboBox already)."""

        if not isinstance(self.entry, AxisSpeedComboBox):
            # Remove the current entry

            self.removeWidget(self.entry)
            self.entry.hide()
            self.entry.deleteLater()

            # Replace it with an AxisSpeedComboBox

            self.entry = AxisSpeedComboBox()
            self.insertWidget(1, self.entry)

    def set_visible(self, visible: bool):
        """Changes the visibility of the label and the entry.

        Args:
            visible (bool): Indicates whether the label and the entry should be visible or not.
        """

        self.label.setVisible(visible)
        self.entry.setVisible(visible)


class AxisComboBox(QComboBox):
    def __init__(self):
        """Initialisation of a drop-down menu for the M2MD axes."""

        super().__init__()

        for axis in range(1, NUM_M2MD_AXES + 1):
            self.addItem(f"M2MD axis {axis}")
        self.setEditable(False)

    def text(self):
        """Converts the selected text to a valid input argument for the dynamic command."""

        return self.currentText()[-1]


class TcuModeComboBox(QComboBox):
    def __init__(self):
        """Initialisation of a drop-down menu for the TCU mode."""

        super().__init__()

        for tcu_mode in TcuMode:
            self.addItem(tcu_mode.name)
        self.setEditable(False)

    def text(self):
        """Converts the selected text to a valid input argument for the dynamic command."""

        return TcuMode[self.currentText()].value


class IntComboBox(QComboBox):
    def __init__(self, min_value: int, max_value: int):
        """Initialisation of a drop-down menu for a range of integers.

        Args:
            min_value (int): Minimum value in the drop-down menu.
            max_value (int): Maximum value in the drop-down menu.
        """

        super().__init__()

        self.addItems([str(x) for x in range(min_value, max_value + 1)])
        self.setEditable(False)

    def text(self):
        """Converts the selected text to a valid input argument for the dynamic command."""

        return int(self.currentText())


class AxisSpeedComboBox(QComboBox):
    def __init__(self):
        """Initialisation of a drop-down menu for the axis speed."""

        super().__init__()

        for speed in AXIS_VELOCITY:
            self.addItem(f"{speed}Hz")

        self.setEditable(False)

    def text(self):
        """Converts the selected text to a valid input argument for the dynamic command.

        The selected text is of the form "XHz", where X is the axis speed in Hz.  This has to be converted into a hex
        string that represents this axis speed.

        Returns:
            Axis speed in hex string format.
        """

        return AXIS_VELOCITY[int(self.currentText()[:-2])]


class TcuUiController(Observer):
    """Controller in the MVC pattern that makes the TCU UI application."""

    def __init__(self, model: TcuUIModel, view: TcuUiView):
        """Initialisation of the TCU UI Controller."""

        super().__init__()

        self.model = model
        self.view = view

        self.view.build_tabs(self.model.build_dyn_cmds_list(), self)

    def do(self, actions):
        # Abstract method from the Observer class, which we do not need here
        pass

    def update(self, changed_object):
        """Updates the TCU UI when the "Run" button is clicked in one of the tabs.

        In this context, updating means:

            - Generating the command string that will be sent to the Arduino and display it in the TCU UI View,
            - Sending the command to the Arduino and display the response in the TCU UI View.
        """

        origin_tab, func, cargo1, cargo2 = changed_object

        signature = inspect.signature(func)
        args = ()
        kwargs = {}

        parameters = signature.parameters

        if len(parameters) == 3:
            cargo1_name = list(parameters.keys())[-2]
            kwargs[cargo1_name] = cargo1

        if len(parameters) >= 2:
            cargo2_name = list(parameters.keys())[-1]
            kwargs[cargo2_name] = cargo2

        # Generate the command string + display

        cmd_string = call_unbound(func, self.model.tcu_hex, *args, **kwargs)
        origin_tab.cmd_string.setText(cmd_string.decode())

        # Execute the command + display the response

        if self.model.tcu_proxy:
            response = call_unbound(func, self.model.tcu_proxy, *args, **kwargs)

            if isinstance(response, Failure):
                origin_tab.response.setStyleSheet("background-color: red;")
                origin_tab.response.setText(str(response.cause))

            else:
                if hasattr(response, "decode") and callable(getattr(response, "decode")):
                    response = response.decode()

                origin_tab.response.setText(str(response))

        elif is_tcu_cs_active():
            self.model.tcu_proxy = TcuProxy()


def call_unbound(func: Callable, instance: object, *args: Any, **kwargs: Any) -> Any:
    """Executes the given function on the given instance with the given arguments.

    This helper handles three cases:

    1. `func` is already a bound method (has `__self__`) -> Call it directly.
    2. Prefer looking up the attribute on `instance` with `getattr(instance, func.__name__)`.
       This lets Python perform normal Method Resolution Order (MRO) so overrides on the instance's class or proxy
       wrappers are returned as bound methods.
    3. If look-up fails (no such attribute on the instance), fall back to binding the original function to `instance`
       using `types.MethodType` (this may call the base/class implementation).

    Args:
        func (Callable): Function (dynamic command) to execute.
        instance (object): Instance on which to execute the function.
        *args: Optional positional arguments for the function.
        **kwargs: Optional keyword arguments for the function.

    Returns:
        Any: Result of the function execution.
    """

    # Case 1: already bound -> call directly

    if getattr(func, "__self__", None) is not None:
        return func(*args, **kwargs)

    # Case 2: preferred lookup on the instance so Python performs normal MRO (Method Resolution Order) and returns
    # the appropriate bound method (honours overrides / proxy behaviour).

    try:
        bound = getattr(instance, func.__name__)
        return bound(*args, **kwargs)
    except AttributeError:
        # Case 3: Fall-back to binding the original function to the instance. This will create a bound method that
        # directly calls the function as if it were defined on the instance.

        bound = types.MethodType(func, instance)
        return bound(*args, **kwargs)


# def call_method_hex(instance: TcuHex, func: Callable, *args, **kwargs) -> Any:
#     """Executes the given dynamic command for the given TCU interface.
#
#     Args:
#         instance (TcuHex): TCU interface for which to execute the given dynamic command.
#         func (Callable): Dynamic command to execute.
#         *args: Optional positional arguments for the dynamic command.
#         **kwargs: Optional keyword arguments for the dynamic command.
#
#     Returns:
#        Response received from the TCU interface.
#     """
#
#     wrapper = instance.handle_dynamic_command(func)
#     result = wrapper(*args, **kwargs)
#
#     return result


@app.command()
def main():
    multiprocessing.current_process().name = "tcu_ui"
    lock_file = QLockFile(str(Path("~/tcu_ui.app.lock").expanduser()))

    tcu_app = QApplication(["-stylesheet", str(get_resource(":/styles/default.qss"))])
    # app_logo = get_resource(":/icons/logo-tcu.svg")
    # app.setWindowIcon(QIcon(str(app_logo)))

    if lock_file.tryLock(100):
        process_status = ProcessStatus()

        timer_thread = threading.Thread(target=do_every, args=(10, process_status.update))
        timer_thread.daemon = True
        timer_thread.start()

        # Create the TCU UI, following the MVC-model

        model = TcuUIModel()
        view = TcuUiView()
        controller = TcuUiController(model, view)
        view.add_observer(controller)

        view.show()

        return tcu_app.exec_()
    else:
        error_message = QMessageBox()
        error_message.setIcon(QMessageBox.Warning)
        error_message.setWindowTitle("Error")
        error_message.setText("The TCU GUI application is already running!")
        error_message.setStandardButtons(QMessageBox.Ok)

        return error_message.exec()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format=Settings.LOG_FORMAT_FULL)

    sys.exit(app())
