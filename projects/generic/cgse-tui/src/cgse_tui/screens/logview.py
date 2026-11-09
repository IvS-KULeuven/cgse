"""A log view that follows the new lines, or keeps its position when the user scrolled up.

Used for the log pane of the overview and the log panel of the logger's detail screen.
"""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import RenderableType
from textual.containers import ScrollableContainer
from textual.widgets import RichLog

FOLLOW_HINT = "scrolled, end to follow"
"""Shown by the screens while the view doesn't follow the new lines."""


class FollowingLog(RichLog):
    """A `RichLog` that follows the new lines while the view is at the end. Scrolled up, the view stays at the same
    lines, also when the oldest lines are removed (`max_lines`). With the focus, the keys of a scrollable container
    scroll it, `end` follows again.

    Subclasses show whether the view follows in `show_follow_state()`, called when it may have changed.
    """

    BINDINGS = ScrollableContainer.BINDINGS

    @property
    def follows(self) -> bool:
        """True when the view is at the end, and new lines scroll it."""
        return self.is_vertical_scroll_end

    def write_lines(self, lines: Iterable[RenderableType]) -> None:
        """Appends the lines, following them when the view is at the end, otherwise keeping it at the same lines."""
        follow = self.follows  # before the writes: a write scrolls to the end only after a refresh
        start_line = self._start_line  # the number of lines removed at the top, private in RichLog
        for line in lines:
            self.write(line, scroll_end=follow)
        removed = self._start_line - start_line
        if not follow and removed > 0:
            self.scroll_to(y=max(0, self.scroll_y - removed), animate=False, immediate=True)
        self.show_follow_state()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        self.show_follow_state()

    def show_follow_state(self) -> None:
        """Called when the view may have started or stopped following, e.g. after a scroll."""
