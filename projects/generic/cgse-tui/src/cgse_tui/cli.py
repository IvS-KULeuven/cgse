"""The `cgse tui` command and the `cgse_tui` script."""

import typer


def tui():
    """Start the terminal user interface with the status of the CGSE services and devices.

    All log messages are written to `cgse_tui.log` in the CGSE log file location.
    """
    from pathlib import Path

    from egse.env import get_log_file_location

    from cgse_tui.app import CgseTuiApp  # Textual is only imported when the TUI is started
    from cgse_tui.logs import LOG_FILE_NAME

    CgseTuiApp(log_file=Path(get_log_file_location()).expanduser() / LOG_FILE_NAME).run()


def main():
    typer.run(tui)


if __name__ == "__main__":
    main()
