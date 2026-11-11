"""A view of many log records that only renders the lines that are visible, for the log screen.

A `RichLog` renders every line when it is written, about 0.4 ms a line: tens of thousands of records of a busy hour
would block the screen for seconds. This view keeps the records and a list of rows (a row is a line of a record, or a
part of it when the long lines are wrapped), and renders a row when it is shown, like the `Log` widget of Textual.
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from typing import Any
from typing import NamedTuple

from rich.text import Text
from textual.cache import LRUCache
from textual.containers import ScrollableContainer
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from cgse_tui.screens.logtail import format_record

Include = Callable[[dict[str, Any]], "bool | None"]
"""Tells how a record is shown: True normal, False dimmed, None not at all."""


class Row(NamedTuple):
    record: int
    """The index of the record."""
    line: int
    """The line of the record, a message can have more lines."""
    start: int
    """The first character of the line in the row, not 0 for the next rows of a wrapped line."""
    dimmed: bool


def _line_lengths(record: dict[str, Any]) -> list[int]:
    """The lengths of the lines of the record as `format_record()` writes it, without rendering it."""
    prefix = 8 + 1 + 8 + 1 + len(str(record.get("process", ""))) + 1 + len(str(record.get("name", ""))) + 1
    lines = str(record.get("message", "")).split("\n")
    return [prefix + len(lines[0]), *(len(line) for line in lines[1:])]


class RecordView(ScrollView, can_focus=True):
    """The log records, one line each (more for a message of more lines), coloured by level.

    The keys of a scrollable container scroll the view, `w` wraps the long lines or cuts them off again (the default;
    `left` and `right` scroll a long line).
    """

    DEFAULT_CSS = """
    RecordView {
        background: $surface;
        color: $text;
        overflow: scroll;
    }
    """

    BINDINGS = [*ScrollableContainer.BINDINGS, ("w", "toggle_wrap", "Wrap")]

    def __init__(self, *, id: str | None = None, classes: str | None = None):
        super().__init__(id=id, classes=classes)
        self.wrap = False
        self._records: list[dict[str, Any]] = []
        self._shown: list[tuple[int, bool]] = []
        """The records that are shown, as (index, dimmed)."""
        self._rows: list[Row] = []
        self._width = 0
        self._wrapped_at = 0
        """The width the rows were wrapped at."""
        self._lines: LRUCache[tuple[int, bool], list[Text]] = LRUCache(1024)
        self._strips: LRUCache[Row, Strip] = LRUCache(2048)
        self.on_scroll: Callable[[], None] | None = None
        """Called when the view scrolled, e.g. to show whether it follows the new records."""

    @property
    def follows(self) -> bool:
        """True when the view is at the end: new records appended with `scroll_end` keep it there."""
        return self.is_vertical_scroll_end

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if self.on_scroll is not None:
            self.on_scroll()

    @property
    def records(self) -> list[dict[str, Any]]:
        return self._records

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def plain_lines(self) -> list[str]:
        """The rows as text, e.g. for the tests."""
        return [self._row_text(row).plain for row in self._rows]

    def clear(self) -> None:
        self._records, self._shown, self._rows, self._width = [], [], [], 0
        self._lines.clear()
        self._strips.clear()
        self.virtual_size = Size(0, 0)
        self.scroll_to(0, 0, animate=False, immediate=True)
        self.refresh()

    def append(self, records: Iterable[dict[str, Any]], include: Include, scroll_end: bool = False) -> int:
        """Adds the records, shown as `include` tells; returns the number of records shown normally."""
        start = len(self._records)
        self._records.extend(records)
        shown = self._select(range(start, len(self._records)), include)
        self._shown.extend(shown)
        self._add_rows(shown)
        if scroll_end:
            self.scroll_end(animate=False, immediate=True, x_axis=False)
        return sum(1 for _, dimmed in shown if not dimmed)

    def show(self, include: Include) -> int:
        """Shows the records again as `include` tells, e.g. after a change of the filter; the view stays at the same
        record when it is still shown. Returns the number of records shown normally."""
        top = self._top_record()
        self._shown = self._select(range(len(self._records)), include)
        self._rebuild(top)
        return sum(1 for _, dimmed in self._shown if not dimmed)

    def drop_oldest(self, count: int) -> int:
        """Removes the oldest records; the view stays at the same record, or at the end when it follows. Returns the
        number of records that are still shown normally."""
        if count <= 0:
            return sum(1 for _, dimmed in self._shown if not dimmed)
        follows = self.follows
        top = self._top_record()
        del self._records[:count]
        self._shown = [(index - count, dimmed) for index, dimmed in self._shown if index >= count]
        self._lines.clear()  # the caches are by index
        self._rebuild(None if top is None else max(0, top - count))
        if follows:
            self.scroll_end(animate=False, immediate=True, x_axis=False)
        return sum(1 for _, dimmed in self._shown if not dimmed)

    def _select(self, indexes: Iterable[int], include: Include) -> list[tuple[int, bool]]:
        shown = []
        for index in indexes:
            decision = include(self._records[index])
            if decision is not None:
                shown.append((index, not decision))
        return shown

    def _add_rows(self, shown: list[tuple[int, bool]]) -> None:
        width = self._wrapped_at if self.wrap else 0
        rows = self._rows
        for index, dimmed in shown:
            for line, length in enumerate(_line_lengths(self._records[index])):
                self._width = max(self._width, length)
                if width:
                    rows.extend(Row(index, line, start, dimmed) for start in range(0, max(length, 1), width))
                else:
                    rows.append(Row(index, line, 0, dimmed))
        self.virtual_size = Size(width or self._width, len(rows))
        self.refresh()

    def _rebuild(self, top: int | None) -> None:
        self._rows = []
        self._width = 0
        self._wrapped_at = self._wrap_width()
        self._strips.clear()  # the rows of a wrapped line depend on the width
        self._add_rows(self._shown)
        y = next((y for y, row in enumerate(self._rows) if top is not None and row.record >= top), None)
        self.scroll_to(0, y if y is not None else self.max_scroll_y, animate=False, immediate=True)

    def _top_record(self) -> int | None:
        y = round(self.scroll_y)
        return self._rows[y].record if 0 <= y < len(self._rows) else None

    def _wrap_width(self) -> int:
        return max(20, self.scrollable_content_region.width or self.size.width)

    def action_toggle_wrap(self) -> None:
        """Wraps the long lines, or cuts them off; the view stays at the same record."""
        self.wrap = not self.wrap
        self._rebuild(self._top_record())

    def notify_style_update(self) -> None:
        super().notify_style_update()
        self._strips.clear()

    def on_resize(self) -> None:
        if self.wrap and self._wrap_width() != self._wrapped_at:
            self._rebuild(self._top_record())

    def _row_text(self, row: Row) -> Text:
        key = (row.record, row.dimmed)
        lines = self._lines.get(key)
        if lines is None:
            text = format_record(self._records[row.record])
            if row.dimmed:
                text = Text(text.plain, "dim")
            lines = list(text.split("\n", allow_blank=True))
            self._lines[key] = lines
        line = lines[row.line] if row.line < len(lines) else Text()
        return line[row.start : row.start + self._wrapped_at] if self.wrap else line

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        width = self.scrollable_content_region.width
        rich_style = self.rich_style
        index = scroll_y + y
        if index >= len(self._rows):
            return Strip.blank(width, rich_style)
        row = self._rows[index]
        strip = self._strips.get(row)
        if strip is None:
            text = self._row_text(row).copy()
            text.stylize_before(rich_style)
            strip = Strip(text.render(self.app.console), text.cell_len)
            self._strips[row] = strip
        return strip.crop_extend(scroll_x, scroll_x + width, rich_style).apply_offsets(scroll_x, index)
