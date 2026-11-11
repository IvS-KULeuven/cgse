"""The dialog to filter the log lines in the detail screen of the logger, see `cgse_tui.screens.logtail.LogFilter`."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import Button
from textual.widgets import Checkbox
from textual.widgets import Footer
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import SelectionList
from textual.widgets import Static
from textual.widgets.selection_list import Selection

from cgse_tui.screens.logtail import LEVEL_STYLES
from cgse_tui.screens.logtail import LEVELS
from cgse_tui.screens.logtail import LogFilter

FIELDS = (
    ("process", "Process", "e.g. cm_cs, sm_cs or !pm_cs"),
    ("module", "Logger/module", "logger name or module, e.g. egse.hexapod, !egse.zmq"),
    ("message", "Message", "words in the message"),
    ("since", "From", "HH:MM[:SS], YYYY-MM-DD HH:MM, or a time ago: 15m, 2h"),
    ("until", "To", "same as From, empty is now"),
)
"""The text fields of the dialog: the attribute of `LogFilter`, the label and the placeholder."""


class LogFilterScreen(ModalScreen[LogFilter | None]):
    """Levels to select and text fields; `enter` in a field or Apply returns the new filter, `esc` returns None.

    Args:
        log_filter: the filter that is applied now.
        processes: the process names in the received records, suggested in the Process field.
        modules: the logger names and modules in the received records, suggested in the Logger/module field.
    """

    DEFAULT_CSS = """
    LogFilterScreen {
        align: center middle;
    }
    LogFilterScreen #dialog {
        width: 90;
        max-width: 100%;
        height: auto;
        max-height: 100%;
        border: thick $primary;
        background: $surface;
        padding: 0 1;
    }
    LogFilterScreen #levels {
        height: auto;
        border: none;
        margin-bottom: 1;
    }
    LogFilterScreen .field {
        height: auto;
    }
    LogFilterScreen .field {
        margin-bottom: 1;
    }
    LogFilterScreen .field Label {
        width: 15;
    }
    LogFilterScreen .field Input {
        width: 1fr;
        background: $boost;
    }
    LogFilterScreen Checkbox {
        border: none;
        padding: 0;
    }
    LogFilterScreen #hide-debug {
        margin-bottom: 1;
    }
    LogFilterScreen #error {
        color: $error;
        height: auto;
    }
    LogFilterScreen #buttons {
        height: auto;
        align-horizontal: right;
        margin-bottom: 1;
    }
    LogFilterScreen #buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "apply", "Apply"),
        ("ctrl+r", "clear", "Clear all"),
    ]

    def __init__(self, log_filter: LogFilter, processes: Iterable[str] = (), modules: Iterable[str] = ()):
        super().__init__()
        self._filter = log_filter
        self._suggestions = {"process": sorted(set(processes)), "module": sorted(set(modules))}

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Filter the log lines (space toggles a level, no level selected shows all)", id="title")
            yield SelectionList[str](
                *(
                    Selection(Text(level, LEVEL_STYLES.get(level, "")), level, level in self._filter.levels)
                    for level in LEVELS
                ),
                id="levels",
            )
            for name, label, placeholder in FIELDS:
                suggestions = self._suggestions.get(name)
                with Horizontal(classes="field"):
                    yield Label(label)
                    yield Input(
                        getattr(self._filter, name),
                        placeholder=placeholder,
                        id=name,
                        compact=True,
                        suggester=SuggestFromList(suggestions, case_sensitive=False) if suggestions else None,
                    )
            yield Checkbox("Dim the other lines instead of hiding them", self._filter.dim, id="dim", compact=True)
            yield Checkbox(
                "Hide the DEBUG lines, also when dimmed (d in the log)",
                self._filter.hide_debug,
                id="hide-debug",
                compact=True,
            )
            yield Static(id="error")
            with Horizontal(id="buttons"):
                yield Button("Clear all", id="clear", compact=True)
                yield Button("Apply", id="apply", variant="primary", compact=True)
        yield Footer()

    def current_filter(self) -> LogFilter:
        return dataclasses.replace(  # keeps what the dialog doesn't show, e.g. the loggers selected in a tree
            self._filter,
            levels=frozenset(self.query_one("#levels", SelectionList).selected),
            **{name: self.query_one(f"#{name}", Input).value.strip() for name, _, _ in FIELDS},
            dim=self.query_one("#dim", Checkbox).value,
            hide_debug=self.query_one("#hide-debug", Checkbox).value,
        )

    def action_apply(self) -> None:
        log_filter = self.current_filter()
        try:
            log_filter.validate()
        except ValueError as exc:
            self.query_one("#error", Static).update(str(exc))
            return
        self.dismiss(log_filter)

    def action_clear(self) -> None:
        """Clears the levels and the text fields; the checkboxes stay as they are."""
        self.query_one("#levels", SelectionList).deselect_all()
        for name, _, _ in FIELDS:
            self.query_one(f"#{name}", Input).value = ""
        self.query_one("#error", Static).update("")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_apply()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "apply":
            self.action_apply()
        else:
            self.action_clear()
