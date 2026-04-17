"""Shared serialization helpers for JSON-safe payload conversion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from egse.log import logger


def to_json_safe(value: Any) -> Any:
    """Recursively convert values into JSON-serializable structures.

    This helper normalizes controller and service payloads that can contain rich
    Python objects (for example `Path`, nested containers, or custom objects that
    expose `as_dict` / `to_dict`) into plain JSON-safe values.

    Conversion rules:
    - primitives are returned unchanged;
    - `Path` becomes `str(path)`;
    - mappings and iterables are converted recursively;
    - objects with `as_dict()` or `to_dict()` are converted via those methods;
    - remaining values fall back to `str(value)`.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]

    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        try:
            return to_json_safe(as_dict())
        except Exception:
            logger.warning(
                f"as_dict() method of {type(value).__name__} raised an exception during JSON conversion.",
                exc_info=True,
            )

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_json_safe(to_dict())
        except Exception:
            logger.warning(
                f"to_dict() method of {type(value).__name__} raised an exception during JSON conversion.",
                exc_info=True,
            )

    return str(value)
