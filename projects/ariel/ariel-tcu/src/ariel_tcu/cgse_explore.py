__all__ = [
    "show_processes",
]

import re

from egse.process import ProcessInfo, get_processes


def show_processes():

    def filter_procs(pi: ProcessInfo):
        pattern = r"tcu_(ui|cs|sim)"

        return re.search(pattern, pi.command)

    return get_processes(filter_procs)
