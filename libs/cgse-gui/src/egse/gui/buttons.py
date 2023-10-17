import sys
from pathlib import Path
from typing import Optional
from typing import Union

from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QWidget

from egse.resource import get_resource

BUTTON_DISABLED = 0
BUTTON_SELECTED = 1
BUTTON_NOT_SELECTED = 2
BUTTON_NO_CHANGE = 3
BUTTON_ACTIONED = 4


# Use the ToolTouchButton when you do not have a QToolBar to manage your buttons,
# but you have them in a QVBoxLayout or QHBoxLayout. The other TouchButton will not
# properly work if not used in a QToolBar, i.e. the icons will not have the proper size.

class ToolTouchButton(QToolButton):
    def __init__(
            self,
            width: int = 32,
            height: int = 32,
            name: str = None,
            status_tip: str = None,
            selected: Union[str, Path] = None,
            disabled: Union[str, Path] = None,
            parent: Optional[QWidget] = None
    ):
        super().__init__(parent=parent)

        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(name)
        self.setStatusTip(status_tip)

        self.status_tip = status_tip

        self.button_selected = selected
        self.button_disabled = disabled

        self.resource = {
            BUTTON_DISABLED: self.button_disabled,
            BUTTON_SELECTED: self.button_selected,
        }

        self.state = BUTTON_SELECTED
        self.disabled = False

        self.clicked.connect(self.handle_clicked)

    def handle_clicked(self):
        self.repaint()

    def print_clicked(self, *args, **kwargs):
        print(f"clicked: {args=}, {kwargs=}")
        print(f"         {self.text()=}")
        self.repaint()

    def print_pressed(self, *args, **kwargs):
        print(f"pressed: {args=}, {kwargs=}")

    def print_released(self, *args, **kwargs):
        print(f"released: {args=}, {kwargs=}")

    def setDisabled(self, flag: bool = True):
        self.disabled = flag
        super().setDisabled(flag)
        self.setStatusTip(f"{self.status_tip or ''} {'[DISABLED]' if flag else ''}")

    def disable(self):
        self.setDisabled(True)

    def enable(self):
        self.setDisabled(False)

    def hitButton(self, pos: QPoint):
        return self.contentsRect().contains(pos)

    def paintEvent(self, *args, **kwargs):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        self.drawCustomWidget(painter)

        painter.end()

    def drawCustomWidget(self, painter):
        renderer = QSvgRenderer()
        resource = self.resource[self.state if not self.disabled else BUTTON_DISABLED]
        renderer.load(str(resource))
        renderer.render(painter)


class TouchButton(QPushButton):
    def __init__(
            self,
            width: int = 32,
            height: int = 32,
            name: str = None,
            status_tip: str = None,
            selected: Union[str, Path] = None,
            disabled: Union[str, Path] = None,
            parent: Optional[QWidget] = None
    ):
        super().__init__(parent=parent)

        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(name)
        self.setStatusTip(status_tip)

        self.status_tip = status_tip

        self.button_selected = selected
        self.button_disabled = disabled

        self.resource = {
            BUTTON_DISABLED: self.button_disabled,
            BUTTON_SELECTED: self.button_selected,
        }

        self.state = BUTTON_SELECTED
        self.disabled = False

        self.clicked.connect(self.handle_clicked)

    def handle_clicked(self):
        self.repaint()

    def print_clicked(self, *args, **kwargs):
        print(f"clicked: {args=}, {kwargs=}")
        print(f"         {self.text()=}")
        self.repaint()

    def print_pressed(self, *args, **kwargs):
        print(f"pressed: {args=}, {kwargs=}")

    def print_released(self, *args, **kwargs):
        print(f"released: {args=}, {kwargs=}")

    def setDisabled(self, flag: bool = True):
        self.disabled = flag
        super().setDisabled(flag)
        self.setStatusTip(f"{self.status_tip or ''} {'[DISABLED]' if flag else ''}")

    def disable(self):
        self.setDisabled(True)

    def enable(self):
        self.setDisabled(False)

    def hitButton(self, pos: QPoint):
        return self.contentsRect().contains(pos)

    def paintEvent(self, *args, **kwargs):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        self.drawCustomWidget(painter)

        painter.end()

    def drawCustomWidget(self, painter):
        renderer = QSvgRenderer()
        resource = self.resource[self.state if not self.disabled else BUTTON_DISABLED]
        renderer.load(str(resource))
        renderer.render(painter)


class ToggleButton(QCheckBox):
    def __init__(
            self,
            width: int = 32,
            height: int = 32,
            name: str = None,
            status_tip: str = None,
            selected: Union[str, Path] = None,
            not_selected: Union[str, Path] = None,
            no_change: Union[str, Path] = None,
            disabled: Union[str, Path, list] = None,
            tristate: bool = False,
            parent: Optional[QWidget] = None
    ):
        super().__init__(parent=parent)

        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        self.setTristate(tristate)
        self.setText(name)
        self.setStatusTip(status_tip)

        self.status_tip = status_tip

        self.max_states = 3 if tristate else 2

        self.button_selected = selected
        self.button_not_selected = not_selected
        self.no_change = no_change
        if isinstance(disabled, list):
            # this assumed we do not change the states definition anymore!
            self.button_disabled = [0, *disabled]
        else:
            self.button_disabled = [0, disabled, disabled, disabled]

        self.resource = {
            BUTTON_DISABLED: self.button_disabled,
            BUTTON_SELECTED: self.button_selected,
            BUTTON_NOT_SELECTED: self.button_not_selected,
            BUTTON_NO_CHANGE: self.no_change,
        }

        self.state = BUTTON_SELECTED
        self.disabled = False

        self.clicked.connect(self.handle_clicked)

    def __str__(self):
        return f"ToggleButton: name={self.text()}, tristate={self.isTristate()}, selected={self.is_selected()}"

    def handle_clicked(self):
        self.state = 1 if self.state == self.max_states else self.state + 1
        self.repaint()

    def setDisabled(self, flag: bool = True):
        self.disabled = flag
        super().setDisabled(flag)
        self.setStatusTip(f"{self.status_tip or ''} {'[DISABLED]' if flag else ''}")

    def disable(self):
        self.setDisabled(True)

    def enable(self):
        self.setDisabled(False)

    def is_selected(self):
        return self.state == BUTTON_SELECTED

    def set_selected(self, on: bool = True):
        self.state = BUTTON_SELECTED if on else BUTTON_NOT_SELECTED
        self.repaint()

    def hitButton(self, pos: QPoint):
        return self.contentsRect().contains(pos)

    def paintEvent(self, *args, **kwargs):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        self.drawCustomWidget(painter)
        painter.end()

    def drawCustomWidget(self, painter):
        renderer = QSvgRenderer()
        if not self.disabled:
            resource = self.resource[self.state]
        else:
            resource = self.resource[BUTTON_DISABLED][self.state]
        renderer.load(str(resource))
        renderer.render(painter)


if __name__ == "__main__":

    from PyQt5.QtWidgets import QMainWindow
    from PyQt5.QtWidgets import QFrame
    from PyQt5.QtWidgets import QVBoxLayout


    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.resize(200, 200)

            self.container = QFrame()
            self.container.setObjectName("Container")
            self.layout = QVBoxLayout()

            # button_selected = get_resource(":/icons/cs-connected.svg")
            # button_not_selected = get_resource(":/icons/cs-not-connected.svg")
            # button_no_change = get_resource(":/icons/cs-connected-alert.svg")
            # button_disabled = get_resource(":/icons/cs-connected-disabled.svg")

            button_selected = get_resource(":/icons/start-button.svg")
            button_not_selected = get_resource(":/icons/stop-button.svg")
            button_no_change = get_resource(":/icons/plugged.svg")
            button_disabled = [
                get_resource(":/icons/start-button-disabled.svg"),
                get_resource(":/icons/stop-button-disabled.svg"),
                get_resource(":/icons/plugged-disabled.svg"),
            ]

            self.toggle = ToggleButton(
                name="CS-CONNECT",
                status_tip="connect-disconnect hexapod control server",
                selected=button_selected,
                not_selected=button_not_selected,
                no_change=button_no_change,
                disabled=button_disabled,
                tristate=True,
            )

            self.touch = TouchButton(
                name="HOME",
                status_tip="Perform a homing operation",
                selected=get_resource(":/icons/home.svg"),
                disabled=get_resource(":/icons/home-disabled.svg"),
            )

            self.layout.addWidget(self.toggle, Qt.AlignCenter, Qt.AlignCenter)
            self.layout.addWidget(self.touch, Qt.AlignCenter, Qt.AlignCenter)
            self.layout.addWidget(pb := QPushButton("disable"))
            self.container.setLayout(self.layout)
            self.setCentralWidget(self.container)

            self.pb = pb
            self.pb.setCheckable(True)
            self.pb.clicked.connect(self.toggle_disable)

            self.toggle.clicked.connect(self.print_clicked)
            self.touch.clicked.connect(self.print_clicked)

            # Use the following for further debugging

            # self.toggle.stateChanged.connect(self.print_state_changed)
            # self.toggle.pressed.connect(self.print_pressed)
            # self.toggle.released.connect(self.print_released)

            # self.touch.pressed.connect(self.print_pressed)
            # self.touch.released.connect(self.print_released)

            self.statusBar()

        def toggle_disable(self, checked: bool):
            self.toggle.disable() if checked else self.toggle.enable()
            self.touch.disable() if checked else self.touch.enable()
            self.pb.setText("enable" if checked else "disable")

        def print_state_changed(self, *args, **kwargs):
            sender = self.sender()
            print(f"stateChanged: {args=}, {kwargs=}")
            print(f"              {sender.isChecked()=} {sender.checkState()=}")

        def print_clicked(self, *args, **kwargs):
            sender = self.sender()
            print(f"clicked: {args=}, {kwargs=}")
            print(f"         {sender.state=}")
            print(f"         {sender.text()=}")

        def print_pressed(self, *args, **kwargs):
            print(f"pressed: {args=}, {kwargs=}")

        def print_released(self, *args, **kwargs):
            print(f"released: {args=}, {kwargs=}")



    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())
