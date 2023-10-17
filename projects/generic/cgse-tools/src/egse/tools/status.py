import textwrap

import rich
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.widgets import Static, Label


class StatusApp(App):
    """A Textual app to present status information."""

    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Static(get_log_cs_status())
        yield Static(get_sm_cs_status())
        yield Label(get_cm_cs_status())
        yield Footer()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark


def get_log_cs_status():

    from egse.logger import send_request

    response = send_request("status")

    if response.get("status") == "ACK":
        text = textwrap.dedent(
            f"""\
            Log Manager:
                Status: [green]active[/]
                Level [grey50](file)[/]: {response.get('file_logger_level')}
                Level [grey50](stdout)[/]: {response.get('stream_logger_level')}
                Log file location: {response.get('file_logger_location')}
            """
        )
    else:
        text = "Log Manager Status: [red]not active"

    return text


def get_cm_cs_status():

    from egse.confman import get_status
    return Text.from_markup(get_status())


def get_sm_cs_status():

    from egse.storage import get_status
    return Text.from_markup(get_status())


def main():
    from rich import print

    try:
        # importing 'egse' only will not cause an import error because this package installs
        # 'egse.tools'
        import egse.confman
        import egse.tools
    except ImportError as exc:
        print(
            textwrap.dedent(
                f"""\
                [red]ERROR: Import error on the egse module.[/red] You must have the CGSE package
                installed in the Python environment you are running this tool from.
                """
            ),
        flush=True)
        print(exc)
        return

    app = StatusApp()
    app.run()

if __name__ == "__main__":
    main()
