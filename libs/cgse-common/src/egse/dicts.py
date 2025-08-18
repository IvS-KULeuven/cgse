"""
This module provides convenience functions to inspect and compare dictionaries when debugging.
"""

__all__ = [
    "flatten_dict",
    "log_differences",
    "log_key_differences",
]
import logging

from rich.table import Table

from egse.log import logger
from egse.system import capture_rich_output
from egse.system import flatten_dict


def log_differences(dict_1, dict_2, log_level: int = logging.INFO):
    """
    Takes two flattened dictionaries and compares them. This function only compares those
    keys that are common to both dictionaries. The key-value pairs that are unique to one
    of the dictionaries are ignored. To inspect if there are keys unique to one dictionary,
    use the [log_key_differences()](dicts.md#egse.dicts.log_key_differences) function.

    The differences are logged in a Rich Table at level=INFO.

    Example:
        ```text
        >>> d1 = { "A": 1, "B": 2, "C": 3 }
        >>> d2 = { "A": 1, "B": 5, "C": 3 }
        >>> log_differences(d1, d2)

        2025-02-28 09:20:51,639:         MainProcess:    INFO:   37:__main__            :Value Differences

        ┏━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
        ┃ Name ┃ old value ┃ new value ┃
        ┡━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
        │ B    │ 2         │ 5         │
        └──────┴───────────┴───────────┘
        ```
    """

    all_keys = dict_1.keys() & dict_2.keys()

    if mismatched := {key for key in all_keys if dict_1[key] != dict_2[key]}:
        table = Table("Name", "old value", "new value", title="Value Differences", title_justify="left")

        for name in sorted(mismatched):
            table.add_row(name, str(dict_1[name]), str(dict_2[name]))

        logger.log(log_level, capture_rich_output(table))
    else:
        logger.log(
            log_level, f"No differences between the two flattened dictionaries, {len(all_keys)} values compared."
        )


def log_key_differences(dict_1, dict_2, log_level: int = logging.INFO):
    """
    Takes two dictionaries and compares the top-level keys. The differences are logged in a Rich Table at level=INFO.
    Keys that are present on both dictionaries are not logged.

    Example:
        ```text
        >>> d1 = {"A": 1, "B": 2, "C": 3}
        >>> d2 = {"B": 2, "C": 3, "D": 4}
        >>> log_key_differences(d1, d2)
        2025-02-28 09:08:29,916:         MainProcess:    INFO:   60:__main__            :Key differences
        ┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
        ┃ Dictionary 1 ┃ Dictionary 2 ┃
        ┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
        │ A            │              │
        │              │ D            │
        └──────────────┴──────────────┘
        ```
    """
    s1 = set(dict_1)
    s2 = set(dict_2)

    not_in_s2 = s1 - s2
    not_in_s1 = s2 - s1

    if not not_in_s1 and not not_in_s2:
        logger.log(log_level, "Both dictionaries contains the same keys.")

    table = Table("Dictionary 1", "Dictionary 2", title="Key differences", title_justify="left")

    for key in not_in_s2:
        table.add_row(str(key), "")

    for key in not_in_s1:
        table.add_row("", str(key))

    logger.log(log_level, capture_rich_output(table))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    d1 = {
        "A": 1,
        "B": 2,
        "C": 3,
    }

    d2 = {
        "B": 2,
        "C": 3,
        "D": 4,
    }

    d3 = {
        "A": 1,
        "B": 5,
        "C": 3,
    }

    log_differences(d1, d2, logging.DEBUG)
    log_key_differences(d1, d2, logging.DEBUG)

    log_differences(d1, d3, logging.DEBUG)
