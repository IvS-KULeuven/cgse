"""The Details panel of the hexapods (PUNA, ZONDA, JORAN) in the CGSE TUI (`cgse tui`).

Registered in the entry-point group `cgse.tui.details` with the `cgse_object` of the control servers. The TUI calls
`details()` every second with the last status report and the values of the last monitoring message. Only Rich is
used here, this module doesn't depend on the TUI.
"""

from __future__ import annotations

import math
from typing import Any

from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

AXES = (("X", "mm"), ("Y", "mm"), ("Z", "mm"), ("Rx", "deg"), ("Ry", "deg"), ("Rz", "deg"))


def _number(value: Any) -> Text:
    """A position or length with 4 decimals; "–" when not known, NaN in red."""
    if value is None:
        return Text("–", justify="right")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return Text(str(value), justify="right")
    if math.isnan(value):
        return Text("NaN", style="red", justify="right")
    return Text(f"{value + 0.0:.4f}", justify="right")  # + 0.0 shows -0.0 as 0.0000


def _values(values: Any, count: int = 6) -> list:
    if not isinstance(values, (list, tuple)):
        try:
            values = list(values)  # e.g. a numpy array
        except TypeError:
            values = []
    return (list(values) + [None] * count)[:count]


def positions(machine: Any, user: Any) -> Table:
    """The position in the machine and in the user coordinate system, per axis."""
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("Axis", style="bold")
    table.add_column("Machine", justify="right")
    table.add_column("User", justify="right")
    table.add_column("Unit", style="dim")
    for (axis, unit), mach, usr in zip(AXES, _values(machine), _values(user)):
        table.add_row(axis, _number(mach), _number(usr), unit)
    return table


def actuators(lengths: Any) -> Table:
    """The length of the six actuators."""
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("Actuator", style="bold")
    table.add_column("Length", justify="right")
    for index, length in enumerate(_values(lengths), start=1):
        table.add_row(str(index), _number(length))
    return table


def details(report: dict[str, Any], live: dict[str, Any]) -> dict[str, RenderableType]:
    """The positions and actuator lengths: the live values of the monitoring message, else those of the report.

    A hexapod that is not connected has no positions, they are shown as "–".
    """
    values = report.get("details") if isinstance(report.get("details"), dict) else {}
    values = {**values, **live}
    return {
        "Position": positions(values.get("mach"), values.get("user")),
        "Actuators": actuators(values.get("alength")),
    }
