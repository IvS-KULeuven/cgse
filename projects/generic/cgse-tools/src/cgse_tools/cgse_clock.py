from datetime import datetime

import rich
import typer
from textual.app import App
from textual.app import ComposeResult
from textual.widgets import Digits

app = typer.Typer()


class ClockApp(App):
    CSS = """
    Screen {
        align: center middle;
        &:inline {
            border: none;
            height: 3;
            Digits {
                color: $success;
            }
        }
    }
    #clock {
        width: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Digits("", id="clock")

    def on_ready(self) -> None:
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self) -> None:
        clock = datetime.now().time()
        self.query_one(Digits).update(f"{clock:%T}")


@app.command()
def clock():
    """Showcase for running an in-line Textual App. """

    ClockApp().run(inline=True)

    rich.print("After in-line mode, you continue where you left off!")
