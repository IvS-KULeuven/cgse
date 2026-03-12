from datetime import datetime
from datetime import timezone

import typer
from textual.app import App
from textual.app import ComposeResult
from textual.widgets import Digits, Label
from textual.containers import Horizontal

app = typer.Typer()


class ClockApp(App):
    CSS = """
    Screen {
        align: center middle;
        &:inline {
            border: none;
            height: 5;
            Digits {
                color: $success;
            }
        }
    }
    Horizontal {
        align: center middle;
    }
    #clock {
        width: auto;
    }
    """

    def __init__(self, utc: bool):
        super().__init__()
        self.utc = utc

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Digits("", id="clock")
            yield Label(" [green]UTC[/]" if self.utc else " [green]LT[/]")

    def on_ready(self) -> None:
        self.update_clock()
        self.set_interval(1, self.update_clock)

    def update_clock(self) -> None:
        if self.utc:
            clock = datetime.now(tz=timezone.utc).time()
        else:
            clock = datetime.now().time()

        self.query_one(Digits).update(f"{clock:%T}")


@app.command()
def clock(utc: bool = False):
    """Showcase for running an in-line Textual App."""

    ClockApp(utc).run(inline=True)

    # rich.print("After in-line mode, you continue where you left off!")
