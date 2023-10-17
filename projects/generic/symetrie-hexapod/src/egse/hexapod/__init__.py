"""
The Hexapod package provides the components to interact with the PUNA Hexapod of
Symétrie, i.e.

* The Hexapod commanding concept with Command, and CommandProtocol
* The client server access through Proxy and ControlServer
* The interface to the hardware controller: HexapodController and its simulator

This package also contains the Hexapod GUI which can be used to monitor the
hexapod positions in different reference frames and apply simple movements.

"""


class HexapodError(Exception):
    """A Hexapod specific error."""
    pass


# These are the classes and function that we would like to export. This is mainly
# to simplify import statements in scripts. The user can now use the following:
#
#    >>> from egse.hexapod import HexapodProxy
#
# while she previously had to import the class as follows:
#
#    >>> from egse.hexapod.hexapodProxy import HexapodProxy
#

__all__ = [
    'HexapodError',
]
