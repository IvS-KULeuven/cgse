"""
Test Mixin functions that are defined in the egse.mixin module.
"""

import logging
import random
from enum import IntEnum
from typing import Callable

import pytest

from egse.command import CommandError
from egse.decorators import dynamic_interface
from egse.decorators import read_command
from egse.device import DeviceTransport
from egse.mixin import DynamicCommandMixin
from egse.mixin import dynamic_command

LOGGER = logging.getLogger("egse.test.mixin")

CHOICES = [b"I don't know what you mean.", b"Can you repeat the question, please?", b"Are you talking to me?"]


# The following two functions shall move to egse.decorators


def query_command(cmd_string: str = None):
    """Decorate an interface function for querying."""

    def func_wrapper(func):
        """Adds a static variable `__query_command` to a method."""
        setattr(func, "__query_command", True)
        setattr(func, "__cmd_string", cmd_string)
        return func

    return func_wrapper


def write_command(cmd_string: str = None):
    """Decorate an interface function for writing."""

    def func_wrapper(func):
        """Adds a static variable `__query_command` to a method."""
        setattr(func, "__write_command", True)
        setattr(func, "__cmd_string", cmd_string)
        return func

    return func_wrapper


def response_processor(processor: Callable):
    """Decorate an interface with a function to process the response of the instrument command."""

    def func_wrapper(func):
        """Adds a static variable `__process_response` to a method."""
        setattr(func, "__process_response", processor)
        return func

    return func_wrapper


def reverse_response(response: bytes) -> bytes:
    """Reverse a bytes object."""
    return response[::-1]


def index_of(response: bytes) -> int:
    """Return the index in CHOICES."""
    return CHOICES.index(response)


class FriendlyTransport(DeviceTransport):
    """What goes to the device and comes back as response."""

    def write(self, command: str):
        LOGGER.info(f"I'm writing down: {command}")

    def read(self) -> bytes:
        return random.choice(CHOICES)

    def trans(self, command: str) -> bool:
        LOGGER.info(f"I'm answering: {command}")
        return False if "studying" in command else True


class FriendlyInterface:
    """Interface definition of all valid commands."""

    @dynamic_interface
    @read_command
    def how_do_you_do(self) -> str:
        """The easiest question."""

    @dynamic_interface
    @query_command("Can I help you with ${topic}?")
    def can_i_help_you_with(self, topic: str) -> bool:
        """Always returns True, except for topic='studying'."""

    @dynamic_interface
    @write_command("Can you do ${command} for me, please?")
    def can_you_do(self, command: str) -> bool:
        """Print an almost friendly welcome message."""

    @dynamic_interface
    @write_command("Can we do ${command} with ${who}?")
    def can_we_do(self, command: str, *, who: str) -> bool:
        """Print an almost friendly welcome message."""

    @dynamic_interface
    @read_command
    @response_processor(reverse_response)
    def can_you_hear_me(self):
        """Return a reverse of the response."""

    @dynamic_interface
    @read_command
    @response_processor(index_of)
    def which_choice(self):
        """Return the choice that was made."""


class Questions(DynamicCommandMixin, FriendlyInterface):
    """Ask some friendly questions."""

    def __init__(self):
        self.transport = FriendlyTransport()
        super().__init__()

    def are_you_directed(self) -> str:
        """Answers directly."""
        return "No, I'm not directed."


def test_standard_commands():
    q = Questions()

    assert q.how_do_you_do() in CHOICES  # read_command
    assert "not directed" in q.are_you_directed()  # command defined in Questions class itself
    assert q.can_you_do(command="the laundry") is None  # write_command
    assert not q.can_i_help_you_with(topic="studying")  # query_command
    assert q.can_i_help_you_with(topic="the laundry")  # query_command

    with pytest.raises(CommandError):
        q.can_we_do("a BBQ", "friends")  # write_command

    q.can_we_do("a BBQ", who="friends")  # write_command

    assert not q.can_i_help_you_with("studying")  # query_command


def test_docstring_example():
    """This example is given in the docstring of `create_command_string`."""

    def func(a, b, flag=True):
        pass

    template = "CREATE:FUN:${a} ${b} [${flag}]"

    response = DynamicCommandMixin.create_command_string(func, template, "TEMP", 23)
    assert response == "CREATE:FUN:TEMP 23 [True]"


def test_process_response():
    q = Questions()

    # maybe also test the reverse function first ;)

    assert reverse_response(b"abcdefgh") == b"hgfedcba"

    assert q.can_you_hear_me()[::-1] in CHOICES
    assert q.which_choice() in list(range(len(CHOICES)))


RESPONSES = [b"42", b"73", b"27", b"666", b"123"]


class NewStyleTransport(DeviceTransport):
    """What goes to the device and comes back as response."""

    def write(self, command: str):
        LOGGER.info(f"write: {command}")

    def read(self) -> bytes:
        return random.choice(RESPONSES)

    def trans(self, command: str) -> bytes:
        LOGGER.info(f"trans: {command}")
        return command.encode()

    def query(self, command: str) -> bytes:
        LOGGER.info(f"query: {command}")
        return random.choice(RESPONSES)


class MyEnum(IntEnum):
    XXX = 42
    YYY = 73


def pre_command(transport: DeviceTransport = None, **kwargs):
    LOGGER.info(f"Inside pre_command({transport.__class__.__name__}, {kwargs})")


def post_command(transport: DeviceTransport = None, response: bytes = None):
    LOGGER.info(f"Inside post_command(transport={transport.__class__.__name__}, {response=})")
    return response


class NewStyleCommandInterface:
    """Interface definition for new style dynamic commands."""

    @dynamic_command(cmd_type="read")
    def new_style_read_command(self) -> bool:
        """A read command only needs to set the cmd_type and doesn't take any arguments."""

    @dynamic_command(cmd_type="write", cmd_string="new style writing: flag=${flag}")
    def new_style_write_command(self, flag=True):
        """A write command shall also define cmd_string and usually has arguments."""

    @dynamic_command(cmd_type="query", cmd_string="new style query: request temp=${temp}")
    def new_style_query_command(self, temp: str):
        """A query command shall define both cmd_type and cmd_string."""

    @dynamic_command(cmd_type="transaction", cmd_string="new style transaction command: config=${config}")
    def new_style_trans_command(self, config: str = "CONFIG"):
        """A transaction command shall define both cmd_type and cmd_string."""

    @dynamic_command(
        cmd_type="transaction",
        cmd_string="trans_command, ${x}, ${y}, ${z}",
        process_cmd_string=lambda x: x.upper() + "\x0d\x0a",
    )
    def test_cmd_string_processor(self, x, y, *, z):
        """Returns the command string."""

    @dynamic_command(
        cmd_type="transaction", cmd_string="trans_command, ${x}, ${y}, ${z} and ${SOME_PREDEFINED_VARIABLE}"
    )
    def test_cmd_string_extra(self, x, y, *, z):
        """Returns the command string."""

    @dynamic_command(cmd_type="transaction", cmd_string="trans_command, {x:04d}, {y:0.2f}, {z:0.4f}", use_format=True)
    def test_cmd_string_format(self, x, y, *, z):
        """Returns the command string."""

    @dynamic_command(cmd_type="transaction", cmd_string="trans_command ${enumeration}")
    def test_cmd_enum(self, enumeration: MyEnum):
        """Returns the command string"""

    @dynamic_command(cmd_type="transaction", cmd_string="trans_command {enumeration}", use_format=True)
    def test_cmd_enum_with_format(self, enumeration: MyEnum):
        """Returns the command string"""

    @dynamic_command(cmd_type="transaction", cmd_string="msg = ${msg}", pre_cmd=pre_command, post_cmd=post_command)
    def test_cmd_pre_post(self, msg: str):
        """Return the command string, executes pre- and post-commands."""


class NewStyleCommand(DynamicCommandMixin, NewStyleCommandInterface):
    """Simple new style commanding interface."""

    def __init__(self):
        self.transport = NewStyleTransport()
        super().__init__()


def test_new_style(caplog):
    caplog.set_level(logging.INFO)

    print()

    ns = NewStyleCommand()

    # Test basic normal behaviour

    assert ns.new_style_read_command() in RESPONSES
    assert ns.new_style_write_command() is None
    assert ns.new_style_query_command("TRP22") in RESPONSES
    assert ns.new_style_trans_command() == b"new style transaction command: config=CONFIG"

    # Test some expected errors

    with pytest.raises(CommandError):
        ns.test_cmd_string_processor(2, 3, 36)

    # Test cmd_string processor

    assert ns.test_cmd_string_processor(2, 3, z=36) == b"TRANS_COMMAND, 2, 3, 36\r\n"

    # Check if the correct docstring is attached to the dynamic command

    assert "transaction" in ns.new_style_trans_command.__doc__

    # $-based substitutions that are not in the argument list will be left alone.
    # This allows to substitute these at another level, e.g. in the cmd_string processor, or
    # in the transport methods.

    assert ns.test_cmd_string_extra(1, 2, z=3) == b"trans_command, 1, 2, 3 and ${SOME_PREDEFINED_VARIABLE}"

    assert ns.test_cmd_string_extra(1, 2, z=None) == b"trans_command, 1, 2, None and ${SOME_PREDEFINED_VARIABLE}"

    assert ns.test_cmd_string_format(27, 42.12345, z=1.3) == b"trans_command, 0027, 42.12, 1.3000"

    assert ns.test_cmd_enum(MyEnum.XXX) == f"trans_command {MyEnum.XXX}".encode()

    assert ns.test_cmd_enum_with_format(MyEnum.XXX) == f"trans_command {MyEnum.XXX}".encode()

    caplog.clear()

    response = ns.test_cmd_pre_post("testing pre- and post-commands")
    assert response == b"msg = testing pre- and post-commands"

    print(f"{caplog.text = }")

    assert "Inside pre_command(NewStyleTransport" in caplog.text
    assert "function_name" in caplog.text
    assert (
        "Inside post_command(transport=NewStyleTransport, response=b'msg = testing pre- and post-commands')"
        in caplog.text
    )


def test_interface_definition():
    with pytest.raises(TypeError):

        class CommandInterface:
            """
            This will raise the following TypeError:
            dynamic_command() missing 1 required keyword-only argument: 'cmd_type'
            """

            @dynamic_command()
            def no_cmd_type(self):
                pass

    with pytest.raises(ValueError):

        class CommandInterface:
            """
            This will raise a ValueError: No cmd_string was provided for cmd_type='write'.
            """

            @dynamic_command(cmd_type="write")
            def no_cmd_string(self):
                pass

    with pytest.raises(ValueError):

        class CommandInterface:
            """
            This will raise a ValueError: No cmd_string was provided for cmd_type='query'.
            """

            @dynamic_command(cmd_type="query")
            def no_cmd_string(self):
                pass

    with pytest.raises(ValueError):

        class CommandInterface:
            """
            This will raise a ValueError: No cmd_string was provided for cmd_type='transaction'.
            """

            @dynamic_command(cmd_type="transaction")
            def no_cmd_string(self):
                pass
