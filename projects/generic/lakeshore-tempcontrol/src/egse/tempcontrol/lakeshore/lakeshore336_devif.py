from egse.command import ClientServerCommand


class LakeShore336Command(ClientServerCommand):
    """ Commands for the Lakeshore336 temperature controller.

    A Command is basically a string that is sent to a device and for which the device returns a response.  The command
    string can contain placeholders that will be filled when the command is called.  The arguments that are given, will
    be filled into the formatted string.  Arguments can be positional or keyword arguments, not both.
    """

    def get_cmd_string(self, *args, **kwargs) -> str:
        """ Returns the formatted command string with the given positional and/or keyword arguments filled out.

        Args:
            *args: Positional arguments that are needed to construct the command string
            **kwargs: Keyword arguments that are needed to construct the command string
        """

        out = super().get_cmd_string(*args, **kwargs)
        return out + "\n"

class LakeShore336Error(Exception):

    """ Base exception for all LakeShore336 errors."""

    pass
