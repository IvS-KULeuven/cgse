"""
This module defines Mixin classes that can be used for adding methods and properties to
classes without strict inheritance.

Be careful, some of the Mixin classes require certain attributes to be defined in the
outer subclass. Read the docstrings carefully to understand what is needed.
"""

import contextlib
import enum
import functools
import inspect
import logging
import string
from typing import Callable
from typing import Dict

from egse.command import ClientServerCommand
from egse.command import CommandError
from egse.command import CommandExecution
from egse.protocol import DynamicCommandProtocol
from egse.protocol import get_function

LOGGER = logging.getLogger(__name__)

__all__ = [
    "add_lf",
    "add_cr_lf",
    "dynamic_command",
    "DynamicCommandMixin",
]

# ----- Mixin for dynamic commanding ---------------------------------------------------------------

COMMAND_TYPES = {
    "read": "__read_command",
    "write": "__write_command",
    "query": "__query_command",
    "transaction": "__transaction_command",
}
STX = "\x02"  # start-of-text
ETX = "\x03"  # end-of-text
EOT = "\x04"  # end-of-transmission
LINE_FEED = "\x0A"
CARRIAGE_RETURN = "\x0D"


def add_etx(cmd_string: str):
    """
    Add an end-of-text ETX (ASCII code 0x03) to the command string.

    Args:
        cmd_string: the unprocessed command string

    Returns:
        The command string with the ETX character appended.
    """
    return cmd_string if cmd_string.endswith(ETX) else cmd_string + ETX


def add_eot(cmd_string: str):
    """
    Add an end-of-transmission EOT (ASCII code 0x04) to the command string.

    Args:
        cmd_string: the unprocessed command string

    Returns:
        The command string with the EOT character appended.
    """
    return cmd_string if cmd_string.endswith(EOT) else cmd_string + EOT


def add_lf(cmd_string: str):
    """ Add a line feed to the given command string, if not added yet.

    Args:
        - cmd_string: Command string.

    Returns: Given command string with a line feed appended (if not present yet).
    """

    if not cmd_string.endswith(LINE_FEED):

        cmd_string += LINE_FEED

    return cmd_string


def add_cr_lf(cmd_string: str):
    """ Add a carriage return and line feed to the given command string, if not added yet.

    Args:
        - cmd_string: Command string.

    Returns: Given command string with a carriage return and line feed appended (if not present yet).
    """

    if not cmd_string.endswith(CARRIAGE_RETURN + LINE_FEED):

        cmd_string += CARRIAGE_RETURN + LINE_FEED

    return cmd_string


def expand_kwargs(kwargs: Dict):
    """Expand keyword arguments and their values as 'key=value' separated by spaces."""
    return " ".join(f"{k}={v}" for k, v in kwargs.items())


def dynamic_command(
        *,
        cmd_type: str,  # required keyword-only argument
        cmd_string: str = None,
        process_response: Callable = None,
        process_cmd_string: Callable = None,
        process_kwargs: Callable = None,
        use_format: bool = False,
        pre_cmd: Callable = None,
        post_cmd: Callable = None,
):
    """Convert an interface method into a dynamic command.

    The arguments define the type of command and how the response shall be processed.

    The command types 'write', 'query', and 'transaction' must be accompanied by a `cmd_string`
    argument that defines the formatting of the eventual command string that will be passed to
    the transport functions. The `cmd_string` is a template string that contains `$`-based
    substitutions for the function arguments. When you specify the `use_format=True` keyword,
    the `cmd_string` will be formatted using the format() function instead of the template
    substitution. The format option is less secure, but provides the functionality to format
    the arguments.

    A template string looks like:

        cmd_string="CREATE:SENS:TEMP ${name} ${type} default=${default}"

    The same `cmd_string` as a format option:

        cmd_string="CREATE:SENS:TEMP {name} {type} default={default:0.4f}"
        use_format=True

    The process_response and process_cmd_string keywords allow you to specify a pure function to
    process the response before it is returned, and to process the cmd_string before it is sent
    to the transport function.

    The `pre_cmd` and `post_cmd` keywords specify a callable/function to be executed before and/or
    after the actual command was executed (i.e. send to the device). These functions are called
    with specific keyword arguments that allow additional device interaction and response processing.
    The `pre_cmd` function is called with the keyword argument `transport=` which passes the device
    transport. This allows the function to interact with the device again through the methods defined
    by the DeviceTransport interface. The `pre_cmd` function must not return anything.
    The `post_cmd` function is called with the keyword arguments `transport=` and `response=`.
    The response argument contains the response from the command that was previously sent to the
    device. The `post_cmd` function can use this response to parse its content and act against
    this content, although possible, it is usually not a good idea to alter the content of the
    response argument. The `post_cmd` function shall return (i.e. pass through) the response.

    This decorator can add the following static attributes to the method:

    * __dynamic_interface
    * __read_command, __write_command, __query_command, __transaction_command
    * __cmd_string
    * __process_response
    * __process_cmd_string
    * __use_format
    * __pre_cmd
    * __post_cmd

    Args:
        cmd_type (str): one of 'read', 'write', 'query', or 'transaction' [required keyword]
        cmd_string (str): format string for the generation of the instrument command
        process_response (Callable): function to process the response
        process_cmd_string (Callable): function to process the command string after substitution
        process_kwargs (Callable): function to expand the kwargs after substitution
        use_format (bool): use string formatting instead of string templates
        pre_cmd (Callable): the function to execute before the command is executed
        post_cmd (Callable): the function to execute after the command is executed
    """

    # Perform some checks on required arguments

    if cmd_type not in COMMAND_TYPES:
        raise ValueError(f"Unknown type passed into dynamic command decorator: {type=}")

    if cmd_type in ('write', 'query', 'transaction') and cmd_string is None:
        raise ValueError(f"No cmd_string was provided for {cmd_type=}.")

    def func_wrapper(func: Callable):
        """Adds the different static attributes."""

        setattr(func, "__dynamic_interface", True)

        setattr(func, COMMAND_TYPES[cmd_type], True)

        if cmd_string is not None:
            setattr(func, "__cmd_string", cmd_string)

        if process_response is not None:
            setattr(func, "__process_response", process_response)

        if process_cmd_string is not None:
            setattr(func, "__process_cmd_string", process_cmd_string)

        if process_kwargs is not None:
            setattr(func, "__process_kwargs", process_kwargs)

        if use_format:
            setattr(func, "__use_format", True)

        if pre_cmd is not None:
            setattr(func, "__pre_cmd", pre_cmd)

        if post_cmd is not None:
            setattr(func, "__post_cmd", post_cmd)

        return func

    return func_wrapper


class DynamicCommandMixin:
    """
    This Mixin class defines the functionality to dynamically call specific instrument commands
    from methods that are defined in the Interface classes for device Controllers.

    The mixin uses the `self.transport` instance variables that shall be defined by the
    Controller subclass. The `self.transport` shall be a DeviceTransport object providing the
    methods to read, write, and query an instrument.

    !!! note
        This mixin overrides the `__getattribute__` method!

    !!! note
        This mixin class shall only be inherited from a Controller class that defines the
        `self.transport` attribute.
    """

    def __init__(self):
        if not hasattr(self, "transport"):
            raise AttributeError("Transport was not defined in sub-class of DynamicInterfaceMixin")

    @staticmethod
    def create_command_string(func: Callable, template_str: str, *args, **kwargs):
        """
        Creates a command string that is understood by the instrument. This can be an SCPI
        command or a specific proprietary command string. The `cmd_str` can contain placeholders
        similar to what is used in string formatting.

        As an example, we have a function with two positional arguments 'a', and 'b' and one keyword
        argument flag:

            def func(a, b, flag=True):
                pass

        We have the following template string: `CREATE:FUN:${a} ${b} [${flag}]`.

        When we call the function as follows: `func("TEMP", 23)`, we would then expect
        the returned string to be "CREATE:FUN:TEMP 23 [True]"

            DynamicCommandMixin.create_command_string(func, template, "TEMP", 23)

        Args:
            func (Callable): a function or method that provides the signature
            template_str (str): a template for the command
            args (tuple): positional arguments that will be used in the command string
            kwargs (dict): keywords arguments that will be used in the command string
        """
        try:
            process_kwargs = getattr(func, "__process_kwargs")
        except AttributeError:
            process_kwargs = expand_kwargs

        template = string.Template(template_str)

        sig = inspect.signature(func)
        try:
            bound = sig.bind(*args, **kwargs)
        except TypeError as exc:
            raise CommandError(
                f"Arguments {args}, {kwargs} do not match function signature for "
                f"{func.__name__}{sig}") from exc

        variables = {}
        for idx, par in enumerate(sig.parameters.values()):
            # if the argument is of signature '**kwargs' then expand the kwargs
            if par.kind == inspect.Parameter.VAR_KEYWORD:
                variables[par.name] = process_kwargs(bound.arguments[par.name])
                continue

            # otherwise, use the argument value or the default
            try:
                variables[par.name] = bound.arguments[par.name]
            except KeyError:
                variables[par.name] = par.default

        if hasattr(func, "__use_format"):
            cmd_string = template_str.format(**variables)
        else:
            variables = {
                k: v.value if isinstance(v, enum.Enum) else v
                for k, v in variables.items()
            }
            cmd_string = template.safe_substitute(variables)

        try:
            process_cmd_string = getattr(func, "__process_cmd_string")
            cmd_string = process_cmd_string(cmd_string)
        except AttributeError:
            pass

        return cmd_string

    def handle_dynamic_command(self, attr):
        """
        Creates a command wrapper calling the appropriate transport methods that are associated
        with the interface definition as passed into this method with the attr argument.

        Args:
            attr: The interface method that is decorated as a dynamic_command.

        Returns:
            Command wrapper with the read or write command, depending on the decorators used
            for that method in the corresponding Interface class.

        Raises:
            AttributeError: If the command is not listed in the YAML file and/or
            has not been listed.
        """

        @functools.wraps(attr)
        def command_wrapper(*args, **kwargs):
            """Generates command strings and executes the transport functions."""
            try:
                cmd_str = getattr(attr, "__cmd_string")
                cmd_str = self.create_command_string(attr, cmd_str, *args, **kwargs)
            except AttributeError:
                cmd_str = None

            response = None

            with contextlib.suppress(AttributeError):
                getattr(attr, "__pre_cmd")(transport=self.transport,
                                           function_name=attr.__name__, cmd_str=cmd_str, args=args, kwargs=kwargs)

            if hasattr(attr, "__write_command"):
                self.transport.write(cmd_str)
            elif hasattr(attr, "__read_command"):
                response = self.transport.read()
            elif hasattr(attr, "__query_command"):
                response = self.transport.query(cmd_str)
            elif hasattr(attr, "__transaction_command"):
                response = self.transport.trans(cmd_str)
            else:
                raise CommandError(f"Interface method '{attr.__name__}' shall be decorated with "
                                   f"a command type decorator.")

            with contextlib.suppress(AttributeError):
                response = getattr(attr, "__post_cmd")(transport=self.transport, response=response)

            with contextlib.suppress(AttributeError):
                process_response = getattr(attr, "__process_response")
                response = process_response(response=response)

            return response

        # Add a hook to identify the command_wrapper function as a method, instead of a function.

        setattr(command_wrapper, "__method_wrapper", True)

        # Add the docstring of the interface method

        command_wrapper.__doc__ = attr.__doc__

        return command_wrapper

    def __getattribute__(self, item):
        """
        The function __getattribute__() is called unconditionally when calling a method or accessing
        an instance variable. This override of `__getattribute__` additionally checks if the
        attribute is a method which has the `__dynamic_interface` defined and then calls a specific
        function to handle the command dynamically.

        Check if item exists:
            - if `item` exists and has the __dynamic_interface attribute then let the function
              handle_dynamic_command() handle this, i.e. call the instrument command.
            - else: the method has been defined in the Controller class, and we should just call
              that method (because it is overridden).
        """

        # If item is not known, an AttributeError will be raised and __getattr__() will be called.

        attr = object.__getattribute__(self, item)

        if hasattr(attr, "__dynamic_interface"):

            # We come here when the method is defined in the Interface class (where it is
            # decorated with the @dynamic_interface), but not in the subclass. So, the method
            # is not overridden. We let the handle_dynamic_command() method handle this.

            attr = self.handle_dynamic_command(attr)

        return attr


class DynamicClientCommandMixin:
    """
    This mixin class contains functionality to forward a device command from a client Proxy class
    to its control server.

    !!! note
        This mixin overrides the `__getattribute__` method!

    """
    def __getattribute__(self, item):
        # If item is not known, an AttributeError will be raised and __getattr__() will be called.

        attr = object.__getattribute__(self, item)

        if hasattr(attr, "__dynamic_interface"):

            # We come here when the method is defined in the Interface class (where it is
            # decorated with the @dynamic_interface), but not in the subclass. So, the method
            # is not overridden. We let the handle_dynamic_command() method handle this.

            attr = self.handle_dynamic_command(attr)

        return attr

    def handle_dynamic_command(self, attr):

        @functools.wraps(attr)
        def command_wrapper(*args, **kwargs):

            attr_name = getattr(attr, "__name__")

            # This will ensure that the function is called with the proper arguments

            try:
                inspect.signature(attr).bind(*args, **kwargs)
            except TypeError as exc:
                LOGGER.error(f"Arguments do not match the signature of the function '{attr_name}': {exc}")
                return None

            # Create a command execution to pass the commanded function and the given arguments
            # to the control server for execution.

            device_method = get_function(self.__class__, attr_name)
            cmd = ClientServerCommand(name=attr_name,
                                      cmd=getattr(attr, "__cmd_string", ""),
                                      response=DynamicCommandProtocol.handle_device_method,
                                      device_method=device_method)
            ce = CommandExecution(cmd, *args, **kwargs)

            # Send the command to the control server for execution

            rc = self.send(ce)
            return rc

        # rewrite the proper signature for the called function

        command_wrapper.__signature__ = inspect.signature(attr)

        return command_wrapper
