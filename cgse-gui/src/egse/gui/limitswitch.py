"""
The LED class provides an easy way to use LEDs in your GUIs.
"""
import sys
from enum import IntEnum
from typing import Dict
from typing import Optional

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QWidget

from egse.resource import get_resource


class Indic(IntEnum):
    ALL_GREEN = 0
    EL_MINUS = 1
    EL_PLUS = 2
    ALL_RED = 3

    @classmethod
    def from_state(cls, state: int):
        return Indic((state & 0b1100) >> 2)


LIMIT_SWITCH = {
    Indic(0): get_resource(":/icons/limit-switch-all-green.svg"),
    Indic(1): get_resource(":/icons/limit-switch-el-.svg"),
    Indic(2): get_resource(":/icons/limit-switch-el+.svg"),
    Indic(3): get_resource(":/icons/limit-switch-all-red.svg"),
}


class LimitSwitch(QLabel):
    """A LED Widget that can be used in your GUIs."""
    def __init__(
            self, parent: Optional[QWidget] = None, size: QSize = QSize(20, 20),
    ):
        """
        Args:
            parent (QWidget): the parent widget
            size (QSize): the (fixed) size of the LED Widget
        """
        super().__init__(parent)

        self.size = size
        self.state = Indic(0)
        self.limit_switch: Dict[Indic, QIcon] = {k: QIcon(str(v)) for k, v in LIMIT_SWITCH.items()}

        self.setFixedSize(self.size)
        self.setPixmap(self.limit_switch[self.state].pixmap(self.size))

    def set_state(self, state: Indic):
        if state is None:
            return
        self.state = state
        self.setPixmap(self.limit_switch[state].pixmap(self.size))

    def set_size(self, size: QSize):
        """Set the size and redraw the LED."""
        self.size = size
        self.setFixedSize(self.size)
        self.setPixmap(self.limit_switch[self.state].pixmap(self.size))


if __name__ == "__main__":

    from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QPushButton

    class Example(QWidget):
        def __init__(self):
            super().__init__()

            self.setGeometry(300, 300, 300, 200)
            self.setWindowTitle("Limit Switch widget")

            self.initUI()

        def initUI(self):

            vbox = QVBoxLayout()
            hbox = QHBoxLayout()

            self.limit_switches = [
                LimitSwitch(parent=self, size=QSize(10, 10)),
                LimitSwitch(parent=self, size=QSize(20, 20)),
                LimitSwitch(parent=self, size=QSize(30, 30)),
                LimitSwitch(parent=self, size=QSize(40, 40)),
            ]

            for limit_switch in self.limit_switches:
                hbox.addWidget(limit_switch)

            vbox.addStretch(1)
            vbox.addLayout(hbox)
            vbox.addStretch(1)

            hbox = QHBoxLayout()

            self.pb1 = QPushButton("All Green", self)
            self.pb2 = QPushButton("EL-", self)
            self.pb3 = QPushButton("EL+", self)
            self.pb4 = QPushButton("All Red", self)

            hbox.addWidget(self.pb1)
            hbox.addWidget(self.pb2)
            hbox.addWidget(self.pb3)
            hbox.addWidget(self.pb4)

            vbox.addLayout(hbox)

            self.pb1.clicked.connect(self.onClick)
            self.pb2.clicked.connect(self.onClick)
            self.pb3.clicked.connect(self.onClick)
            self.pb4.clicked.connect(self.onClick)

            self.setLayout(vbox)

        def onClick(self):

            sender = self.sender()
            text = sender.text()

            for ls in self.limit_switches:
                if text == "All Green":
                    state = 0b0000
                    ls.set_state(Indic.from_state(state))
                elif text == "EL-":
                    state = 0b0100
                    ls.set_state(Indic.from_state(state))
                elif text == "EL+":
                    state = 0b1000
                    ls.set_state(Indic.from_state(state))
                elif text == "All Red":
                    state = 0b1100
                    ls.set_state(Indic.from_state(state))

    app = QApplication([])
    ex = Example()
    ex.show()
    sys.exit(app.exec_())
