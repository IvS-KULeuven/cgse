"""
The LED class provides an easy way to use LEDs in your GUIs.
"""
import sys
from enum import IntEnum
from typing import List
from typing import Optional

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QWidget

from egse.decorators import deprecate
from egse.resource import get_resource

SQUARE_COLORS = [
    str(get_resource(":/icons/led-square-grey.svg")),
    str(get_resource(":/icons/led-square-green.svg")),
    str(get_resource(":/icons/led-square-orange.svg")),
    str(get_resource(":/icons/led-square-red.svg")),
]

CIRCLE_COLORS = [
    str(get_resource(":/icons/led-grey.svg")),
    str(get_resource(":/icons/led-green.svg")),
    str(get_resource(":/icons/led-orange.svg")),
    str(get_resource(":/icons/led-red.svg")),
]


class Indic:
    """The color or kind of LED that you want to show."""
    BLACK = OFF = 0
    GREEN = ON = 1
    ORANGE = WARNING = 2
    RED = EMERGENCY = 3


class ShapeEnum(IntEnum):
    """Supported LED shapes."""
    CIRCLE = 0
    SQUARE = 1


class LED(QLabel):
    """A LED Widget that can be used in your GUIs."""
    def __init__(self, parent: Optional[QWidget] = None,
                 size: QSize = QSize(20, 20),
                 shape: ShapeEnum = ShapeEnum.CIRCLE):
        """
        Args:
            parent (QWidget): the parent widget
            size (QSize): the (fixed) size of the LED Widget
            shape (ShapeEnum): the shape of the LED - [circle or square]
        """
        super().__init__(parent)

        self.shape = shape
        self.size = size
        self.color = Indic.OFF

        colors = CIRCLE_COLORS if shape == ShapeEnum.CIRCLE else SQUARE_COLORS
        self.colors: List[QIcon] = [QIcon(x) for x in colors]

        self.setFixedSize(self.size)
        self.setPixmap(self.colors[self.color].pixmap(self.size))

    @deprecate(alternative="set_color")
    def setColor(self, color):
        self.set_color(color)

    def set_color(self, color: int):
        """Set the color and redraw the LED."""
        self.color = color
        self.setPixmap(self.colors[self.color].pixmap(self.size))

    def set_size(self, size: QSize):
        """Set the size and redraw the LED."""
        self.size = size
        self.setFixedSize(self.size)
        self.setPixmap(self.colors[self.color].pixmap(self.size))


# For compatibility where we used to have a class Led instead of LED.

Led = LED


if __name__ == "__main__":

    from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QPushButton

    class Example(QWidget):
        def __init__(self):
            super().__init__()

            self.setGeometry(300, 300, 300, 200)
            self.setWindowTitle("Led widget")

            self.initUI()

        def initUI(self):

            vbox = QVBoxLayout()
            hbox = QHBoxLayout()

            self.leds = [
                LED(shape=ShapeEnum.SQUARE, parent=self),
                LED(shape=ShapeEnum.CIRCLE, parent=self),
                LED(shape=ShapeEnum.SQUARE, parent=self),
                LED(shape=ShapeEnum.CIRCLE, parent=self),
            ]

            for led in self.leds:
                led.set_size(QSize(30, 30))
                hbox.addWidget(led)

            vbox.addStretch(1)
            vbox.addLayout(hbox)
            vbox.addStretch(1)

            hbox = QHBoxLayout()

            self.pb1 = QPushButton("On", self)
            self.pb2 = QPushButton("Warning", self)
            self.pb3 = QPushButton("Emergency", self)
            self.pb4 = QPushButton("Off", self)

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

            for led in self.leds:
                if text == "On":
                    led.set_color(Indic.GREEN)
                elif text == "Warning":
                    led.set_color(Indic.ORANGE)
                elif text == "Emergency":
                    led.set_color(Indic.RED)
                elif text == "Off":
                    led.set_color(Indic.BLACK)

    app = QApplication([])
    ex = Example()
    ex.show()
    sys.exit(app.exec_())
