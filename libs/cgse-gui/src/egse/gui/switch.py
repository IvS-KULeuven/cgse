#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
A Switch button widget.
"""
import logging
import sys

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QWidget

from egse.config import find_dir
from egse.resource import get_resource

logger = logging.getLogger(__name__)


class Indic:
    ON = 0
    OFF = 1


class Switch(QWidget):

    def __init__(self, parent):
        super().__init__(parent)

        self.state = Indic.OFF

        self.setMinimumSize(QSize(40, 40))
        self.setMaximumSize(QSize(40, 40))

        self.states = ["switch-on.svg", "switch-off.svg"]

    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        self.drawCustomWidget(painter)
        painter.end()

    def drawCustomWidget(self, painter):
        renderer = QSvgRenderer()
        renderer.load(str(get_resource(f":/icons/{self.states[self.state]}")))
        renderer.render(painter)

    def setState(self, state):
        self.state = state
        self.repaint()


if __name__ == "__main__":

    from PyQt5.QtWidgets import QApplication, QVBoxLayout, QHBoxLayout, QPushButton

    class Example(QWidget):
        def __init__(self):
            super().__init__()

            self.setGeometry(300, 300, 300, 200)
            self.setWindowTitle("Switch widget")

            self.initUI()

        def initUI(self):

            vbox = QVBoxLayout()
            hbox = QHBoxLayout()

            self.switch = Switch(self)

            hbox.addWidget(self.switch)
            vbox.addStretch(1)
            vbox.addLayout(hbox)
            vbox.addStretch(1)

            hbox = QHBoxLayout()

            self.pb1 = QPushButton("On", self)
            self.pb2 = QPushButton("Off", self)

            hbox.addWidget(self.pb1)
            hbox.addWidget(self.pb2)

            vbox.addLayout(hbox)

            self.pb1.clicked.connect(self.onClick)
            self.pb2.clicked.connect(self.onClick)

            self.setLayout(vbox)

        def onClick(self):

            sender = self.sender()
            text = sender.text()

            print(text)
            if text == "On":
                self.switch.setState(Indic.ON)
            elif text == "Off":
                self.switch.setState(Indic.OFF)

    app = QApplication([])
    ex = Example()
    ex.show()
    sys.exit(app.exec_())
