"""
This module provides convenience functions to inspect and compare dictionaries when debugging.
"""
__all__ = [
    "flatten_dict",
    "log_differences",
    "log_key_differences",
]
import logging

from egse.system import capture_rich_output
from egse.system import flatten_dict
from rich.table import Table

LOGGER = logging.getLogger(__name__)


def log_differences(dict_1, dict_2):
    """
    Takes two flattened dictionaries and compares them. The differences are logged in a Rich Table at level=INFO.
    """

    all_keys = dict_1.keys() & dict_2.keys()

    if mismatched := {key for key in all_keys if dict_1[key] != dict_2[key]}:

        table = Table("Name", "old value", "new value", title="Value Differences", title_justify="left")

        for name in sorted(mismatched):
            table.add_row(name, str(dict_1[name]), str(dict_2[name]))

        LOGGER.info(capture_rich_output(table))
        # rich.print(table)
    else:
        LOGGER.info(f"No differences between the two flattened dictionaries, {len(all_keys)} values compared.")


def log_key_differences(dict_1, dict_2):
    """
    Takes two dictionaries and compares the top-level keys. The differences are logged in a Rich Table at level=INFO.
    Keys that are present on both dictionaries are not logged.
    """
    s1 = set(dict_1)
    s2 = set(dict_2)

    not_in_s2 = s1 - s2
    not_in_s1 = s2 - s1

    if not not_in_s1 and not not_in_s2:
        LOGGER.info("Both dictionaries contains the same keys.")

    table = Table("Dictionary 1", "Dictionary 2", title="Key differences", title_justify="left")

    for key in not_in_s2:
        table.add_row(str(key), "")

    for key in not_in_s1:
        table.add_row("", str(key))

    LOGGER.info(capture_rich_output(table))


if __name__ == '__main__':

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

    log_differences(d1, d2)
    log_key_differences(d1, d2)
