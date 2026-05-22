"""Helpers for converting metric payloads to Influx/QuestDB line protocol."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from typing import Mapping


def to_line_protocol(payload: Mapping[str, Any]) -> str | None:
    """Convert a DataPoint-style payload to a line protocol string.

    The payload is expected to contain:
    - measurement (required)
    - fields (required, at least one valid value)
    - tags (optional)
    - time (optional: Unix seconds or ISO-8601 string)
    """

    measurement = payload.get("measurement", "")
    if not measurement:
        return None

    fields = payload.get("fields") or {}
    tags = payload.get("tags") or {}
    timestamp = payload.get("time")

    def _esc(value: str) -> str:
        return value.replace(",", "\\,").replace("=", "\\=").replace(" ", "\\ ")

    def _field_val(value: object) -> str | None:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return f"{value}i"
        if isinstance(value, float):
            if not math.isfinite(value):
                return None
            return repr(value)
        if isinstance(value, str):
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return None

    meas_escaped = str(measurement).replace(",", "\\,").replace(" ", "\\ ")
    parts = [meas_escaped]
    if tags:
        tag_str = ",".join(
            f"{_esc(str(key))}={_esc(str(value))}" for key, value in sorted(tags.items()) if value is not None
        )
        if tag_str:
            parts.append("," + tag_str)

    field_parts = []
    for key, value in fields.items():
        if value is None:
            continue
        field_value = _field_val(value)
        if field_value is not None:
            field_parts.append(f"{_esc(str(key))}={field_value}")

    if not field_parts:
        return None

    lp = "".join(parts) + " " + ",".join(field_parts)

    if timestamp is not None:
        if isinstance(timestamp, (int, float)):
            lp += f" {int(timestamp * 1_000_000_000)}"
        elif isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                lp += f" {int(dt.timestamp() * 1_000_000_000)}"
            except ValueError:
                pass

    return lp
