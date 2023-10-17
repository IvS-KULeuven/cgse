# Provide basic information about the egse logger that is of interest to the developer.
# Do not assume the log_cs is running, this function shall also provide the information
# even if the logger is not running.
#
# usage:
#   $ python -m egse.logger

from egse.env import get_log_file_location

import rich

rich.print(f"Log file location: {get_log_file_location()}")
