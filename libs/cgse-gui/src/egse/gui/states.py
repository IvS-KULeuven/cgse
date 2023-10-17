import random
import sys
from typing import List
from typing import Optional
from typing import Union

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QGroupBox
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidget

from .led import Indic
from .led import LED
from .led import ShapeEnum


class States(QGroupBox):

    def __init__(self, states: List[List],
                 title: Optional[str] = "States",
                 shape: ShapeEnum = ShapeEnum.CIRCLE,
                 parent: QWidget = None):
        """
        Args:
            states (List[List]): description and default LED color for all states
            shape (ShapeEnum): the shape of the LEDs
            parent (QWidget): the parent widget
        """
        super().__init__(parent)

        self.leds = []

        vbox = QVBoxLayout()

        for state in states:
            description, default = state

            self.leds.append([led := LED(shape=shape, parent=parent), default, description])

            led.set_color(default)

            # Create a hbox where the led and the label is added, then add this hbox to the
            # states vbox.

            hbox = QHBoxLayout()
            hbox.addWidget(led)
            hbox.addWidget(QLabel(description))

            # Add the corresponding hbox to the states vbox

            vbox.addLayout(hbox)

        # Make sure the hboxes stay nicely together when vertically resizing the Frame.

        vbox.addStretch()

        self.setTitle(title)
        self.setLayout(vbox)

    def __len__(self):
        return len(self.leds)

    def set_states(self, states: Union[List, int]):

        if isinstance(states, int):
            # States can take True or False in which case the default color will be used or
            # Indic.OFF

            count = len(self.leds)

            # Reverse the bit order to match the states with the bits in the states integer

            states = [int(x) for x in f"{states:0{count}b}"[::-1]]
            for led, state in zip(self.leds, states):
                led[0].set_color(led[1] if state else Indic.OFF)

        else:
            # State can take different values
            for led, state in zip(self.leds, states):
                if isinstance(state, bool):
                    color = led[1] if state else Indic.OFF
                else:
                    color = state
                led[0].set_color(color)

    def reset_states(self):
        for led in self.leds:
            led[0].set_color(led[1])


if __name__ == "__main__":

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()

            main = QWidget()
            vbox = QVBoxLayout()

            self.states = States([
                ["Active [G]", Indic.GREEN],
                ["Danger [O]", Indic.ORANGE],
                ["Error  [R]", Indic.RED],
            ], shape=ShapeEnum.CIRCLE)

            update_button = QPushButton("Update States")
            update_button.clicked.connect(lambda: self.update_states())

            reset_button = QPushButton("Reset States")
            reset_button.clicked.connect(self.reset_states)

            set_button = QPushButton("Set States to random value")
            set_button.clicked.connect(
                lambda: self.update_states(random.choice(range(8))))

            hbox = QHBoxLayout()
            hbox.addWidget(update_button)
            hbox.addWidget(reset_button)
            hbox.addWidget(set_button)

            vbox.addWidget(self.states)
            vbox.addLayout(hbox)

            main.setLayout(vbox)
            self.setCentralWidget(main)

        def update_states(self, states: int = None):
            if states is None:
                new_states = [random.choice([Indic.GREEN, Indic.BLACK, Indic.RED, Indic.ORANGE])
                              for _ in range(len(self.states))]
                print(new_states)
            else:
                new_states = states
                print(f"{states:03b}")

            self.states.set_states(new_states)

        def reset_states(self):
            self.states.reset_states()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
