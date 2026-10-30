"""The `cgse tui` command and the `cgse_tui` script."""

import typer


def tui():
    """Start the terminal user interface with the status of the CGSE services and devices."""
    from cgse_tui.app import CgseTuiApp  # Textual is only imported when the TUI is started

    CgseTuiApp().run()


def main():
    typer.run(tui)


if __name__ == "__main__":
    main()
