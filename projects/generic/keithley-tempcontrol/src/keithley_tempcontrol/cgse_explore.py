__all__ = [
    "show_processes",
]

import re

from egse.process import ProcessInfo
from egse.process import get_processes


def show_processes():
    """Returns of list of ProcessInfo data classes for matching processes from this package."""

    def filter_procs(pi: ProcessInfo):
        pattern = r"daq6510"

        return re.search(pattern, pi.command)

    return get_processes(filter_procs)
