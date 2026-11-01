"""The dialog to select the columns of the overview table."""

from __future__ import annotations

from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer
from textual.widgets import SelectionList
from textual.widgets import Static
from textual.widgets.selection_list import Selection

from cgse_tui.screens.columns import COLUMNS
from cgse_tui.screens.columns import DEFAULT_COLUMNS
from cgse_tui.screens.columns import REQUIRED_COLUMNS


class ColumnSelectScreen(ModalScreen[None]):
    """A list of the columns with a checkbox, a change is applied to the overview right away.

    Args:
        selected: keys of the columns that are shown now.
        on_change: called with the keys of the selected columns after every change.
    """

    DEFAULT_CSS = """
    ColumnSelectScreen {
        align: center middle;
    }
    ColumnSelectScreen #dialog {
        width: 80;
        max-width: 100%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 0 1;
    }
    ColumnSelectScreen #columns {
        height: 1fr;
        border: none;
    }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("o", "dismiss", "Close"),
        ("a", "select_all", "All"),
        ("n", "select_none", "None"),
        ("d", "select_defaults", "Defaults"),
    ]

    def __init__(self, selected, on_change: Callable[[list[str]], None]):
        super().__init__()
        self._selected = set(selected)
        self._on_change = on_change

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("Columns of the overview (space toggles a column)", id="title")
            yield SelectionList[str](
                *(
                    Selection(
                        Text.assemble(f"{column.label:<14}", (column.description, "dim")),
                        column.key,
                        column.key in self._selected,
                    )
                    for column in COLUMNS
                    if column.key not in REQUIRED_COLUMNS
                ),
                id="columns",
            )
        yield Footer()

    @property
    def selection_list(self) -> SelectionList:
        return self.query_one("#columns", SelectionList)

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        self._on_change(list(event.selection_list.selected))

    def action_select_all(self) -> None:
        self.selection_list.select_all()

    def action_select_none(self) -> None:
        self.selection_list.deselect_all()

    def action_select_defaults(self) -> None:
        selection_list = self.selection_list
        selection_list.deselect_all()
        for key in DEFAULT_COLUMNS:
            if key not in REQUIRED_COLUMNS:
                selection_list.select(key)
