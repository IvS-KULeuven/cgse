"""A log view that follows the new lines, or keeps its position when the user scrolled up.

Used for the log pane of the overview and the log panel of the logger's detail screen.
"""

from __future__ import annotations

import collections
from collections.abc import Iterable

from rich.console import RenderableType
from textual.containers import ScrollableContainer
from textual.widgets import RichLog

FOLLOW_HINT = "scrolled, end to follow"
"""Shown by the screens while the view doesn't follow the new lines."""


class FollowingLog(RichLog):
    """A `RichLog` that follows the new lines while the view is at the end. Scrolled up, the view stays at the same
    lines, also when the oldest lines are removed (`max_lines`). With the focus, the keys of a scrollable container
    scroll it, `end` follows again, and `w` wraps the long lines or cuts them off again (the default, the log keeps its
    cadence; `left` and `right` scroll a long line).

    Subclasses show whether the view follows in `show_follow_state()`, called when it may have changed.
    """

    BINDINGS = [*ScrollableContainer.BINDINGS, ("w", "toggle_wrap", "Wrap")]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wrap", False)
        super().__init__(*args, **kwargs)
        self._written: collections.deque[tuple[int, RenderableType]] = collections.deque(maxlen=self.max_lines)
        """What `write_lines()` wrote, with the number of its first line, to write it again with or without wrapping.
        The number counts from the first line ever written, also when the oldest lines were removed."""

    @property
    def follows(self) -> bool:
        """True when the view is at the end, and new lines scroll it."""
        return self.is_vertical_scroll_end

    def write_lines(self, lines: Iterable[RenderableType]) -> None:
        """Appends the lines, following them when the view is at the end, otherwise keeping it at the same lines."""
        self._write_lines(lines, follow=self.follows)  # before the writes: a write scrolls to the end after a refresh
        self.show_follow_state()

    def _write_lines(self, lines: Iterable[RenderableType], follow: bool) -> None:
        start_line = self._start_line  # the number of lines removed at the top, private in RichLog
        for line in lines:
            self._written.append((self._start_line + len(self.lines), line))
            self.write(line, scroll_end=follow)
        removed = self._start_line - start_line
        if not follow and removed > 0:
            self.scroll_to(y=max(0, self.scroll_y - removed), animate=False, immediate=True)

    def clear(self):
        self._written.clear()
        return super().clear()

    def action_toggle_wrap(self) -> None:
        """Wraps the long lines, or cuts them off, and writes all lines again. Scrolled up, the view stays at the same
        line; at the end it keeps following."""
        follow = self.follows
        top = self._start_line + round(self.scroll_y)
        written = list(self._written)
        index = max((i for i, (first, _) in enumerate(written) if first <= top), default=0)
        self.wrap = not self.wrap
        self.clear()
        self.scroll_to(x=0, animate=False, immediate=True)
        self._write_lines((line for _, line in written), follow)
        if not follow and written:
            self.scroll_to(y=self._written[index][0] - self._start_line, animate=False, immediate=True)
        self.show_follow_state()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        self.show_follow_state()

    def show_follow_state(self) -> None:
        """Called when the view may have started or stopped following, e.g. after a scroll."""
