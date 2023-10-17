import time
from functools import partial
from typing import Callable

import pytest

from egse.command import ClientServerCommand
from egse.command import Command
from egse.command import CommandError
from egse.command import CommandExecution
from egse.command import InvalidArgumentsError
from egse.command import WaitCommand
from egse.command import parse_format_string
from egse.command import stringify_function_call
from egse.state import GlobalState


class PrintCommand(Command):
    def execute(self, cmd_string):
        print(f'{self.__class__.__name__}({self._name}) executing "{cmd_string}"')
        return 0


class HexapodCommand(ClientServerCommand):
    pass


class HuberCommand(ClientServerCommand):
    pass


def return_command_string(self, cmd_string):
    return cmd_string


def add_cr_to_string(self, cmd_string):
    return cmd_string + "\r\n"


def test_dry_run(monkeypatch):
    monkeypatch.setattr(HexapodCommand, "execute", return_command_string)
    cmd = HexapodCommand(name="dry-run-cmd", cmd="dry-run-test {flag} {arg}")

    rc = cmd("--dr", "arg_1")
    assert rc.startswith("dry-run-test")

    with pytest.raises(AttributeError):
        rc = cmd.client_call(None, "--dr", "arg_1")

    GlobalState.dry_run = True

    rc = cmd.client_call(None, "--dr", "arg_1")
    assert rc.successful
    cmd_seq = GlobalState.get_command_sequence()
    assert cmd_seq
    assert len(cmd_seq) == 1
    assert str(cmd_seq[0]).startswith("[HexapodCommand] ")

    print(cmd_seq[0])

    # Clean up = reset global state

    GlobalState.dry_run = False
    GlobalState.clear_command_sequence()


def test_command_class(mocker):
    mocker.patch.object(Command, "execute")

    cmd = Command(name="mock-test", cmd="mock-test {flag} {arg}")

    rc = cmd(flag="-a", arg="mock-execute-method")
    cmd.execute.assert_called_with("mock-test -a mock-execute-method")

    rc = cmd("-a", "mock-execute-method")
    cmd.execute.assert_called_with("mock-test -a mock-execute-method")


def test_return_code_of_execute(monkeypatch):
    monkeypatch.setattr(HexapodCommand, "execute", return_command_string)

    checkQVars = HexapodCommand(name="QVars?", cmd="&2 Q20 Q{var},{count},{step}")

    assert checkQVars(var=36, count=1, step=1) == "&2 Q20 Q36,1,1"
    assert checkQVars(36, 1, 1) == "&2 Q20 Q36,1,1"

    getSpeed = HexapodCommand(
        name="CFG?SPEED", cmd="&2 Q20=35", response=partial(checkQVars, 80, 6, 1)
    )

    rc = getSpeed()

    assert rc == "&2 Q20 Q80,6,1"


def test_number_of_argument(monkeypatch):
    monkeypatch.setattr(Command, "execute", return_command_string)

    aCommand = Command(name="aCommand", cmd="cmd no-arguments")

    assert aCommand() == "cmd no-arguments"

    with pytest.raises(CommandError):
        rc = aCommand(1)
    with pytest.raises(CommandError):
        rc = aCommand(rc=2)
    with pytest.raises(CommandError):
        rc = aCommand(1, rc=2)

    aCommand = Command(name="aCommand", cmd="cmd args = {}")

    assert aCommand("one argument") == "cmd args = one argument"

    with pytest.raises(CommandError):
        rc = aCommand()
    with pytest.raises(CommandError):
        rc = aCommand(rc=2)
    with pytest.raises(CommandError):
        rc = aCommand(1, rc=2)

    aCommand = Command(name="aCommand", cmd="cmd args = {sw}")

    assert aCommand(sw="one keyword argument") == "cmd args = one keyword argument"
    assert aCommand(1) == "cmd args = 1"

    with pytest.raises(CommandError):
        rc = aCommand()
    with pytest.raises(CommandError):
        rc = aCommand(1, sw=2)

    aCommand = Command("aCommand", "&2 Q{qvar1} Q{qvar2}")

    assert aCommand(20, 42) == "&2 Q20 Q42"

    aCommand = Command("aCommand", "&2 Q{qvar1} Q{qvar2:04d}")

    assert aCommand(20, 42) == "&2 Q20 Q0042"
    assert aCommand(qvar1=20, qvar2=42) == "&2 Q20 Q0042"


def test_strange_characters(monkeypatch):
    monkeypatch.setattr(HexapodCommand, "execute", return_command_string)
    monkeypatch.setattr(HuberCommand, "execute", add_cr_to_string)

    hex_cmd = HexapodCommand("hex_cmd", "&2 Q{qvar} {{xxx}}")
    assert hex_cmd(13) == "&2 Q13 {xxx}"

    hub_cmd = HuberCommand("hub_cmd", cmd="acc{axis:d}:{value:d}")
    assert hub_cmd(1, 100) == "acc1:100\r\n"


def test_format_strings():
    fstring = "cmd = empty"
    assert parse_format_string(fstring) == (0, 0, 0, [])

    fstring = "cmd = {}"
    assert parse_format_string(fstring) == (1, 1, 0, [])

    fstring = "cmd = {sw}"
    assert parse_format_string(fstring) == (1, 0, 1, ["sw"])

    fstring = "cmd = {:2.5x}"
    assert parse_format_string(fstring) == (1, 1, 0, [])

    fstring = "cmd = {sw:2.5x}"
    assert parse_format_string(fstring) == (1, 0, 1, ["sw"])

    fstring = "cmd = {sw:2.5x} {xs}"
    assert parse_format_string(fstring) == (2, 0, 2, ["sw", "xs"])

    with pytest.raises(CommandError):
        fstring = "cmd = {sw:2.5x} {} {xs}"
        assert parse_format_string(fstring) == (3, 1, 2, ["sw", "xs"])

    fstring = "cmd = {sw:2.5x} {{no-key}} {xs}"
    assert parse_format_string(fstring) == (2, 0, 2, ["sw", "xs"])


def test_simple_definition():
    # OK, I agree, this is a very complex way to write addition of integers, but it demonstrates a point...

    class AddIntsCommand(Command):
        def execute(self, cmd_string):
            parts = cmd_string.split()
            return int(parts[0]) + int(parts[1])

    add = AddIntsCommand(name="add", cmd="{} {}", wait=partial(time.sleep, 1))
    assert add(2, 5) == 7


def test_wait_and_respond(monkeypatch):
    monkeypatch.setattr(HexapodCommand, "execute", return_command_string)

    getQ20 = HexapodCommand(name="getQ20", cmd="&2 Q20")

    waitForQ20 = WaitCommand(getQ20, lambda x: x in [0, -1, -2])
    waitFor10Seconds = WaitCommand(partial(time.sleep, 1), lambda x: True)

    checkQVars = HexapodCommand(name="QVars?", cmd="&2 Q20 Q{var},{count},{step}")

    getSpeed = HexapodCommand(
        name="CFG?SPEED",
        cmd="&2 Q20=35",
        response=partial(checkQVars, 80, 6, 1),
        wait=waitFor10Seconds,
    )

    rc = getSpeed()

    assert rc == "&2 Q20 Q80,6,1"


def test_pos_and_keyword_arguments(monkeypatch):
    monkeypatch.setattr(Command, "execute", return_command_string)

    with pytest.raises(CommandError):
        mixed_args_cmd = Command(name="mixed arguments", cmd="cmd {first} {} {third}")
        mixed_args_cmd(2, first=1, third=3)


def test_command_execution():
    ce = CommandExecution(PrintCommand(name="print", cmd="{} and {}"), "one", "two")
    response = ce.run()

    assert response == 0


def test_doc_string():

    cmd = Command(name="Plain", cmd="plain_command", description="A Plain Command")

    assert "A Plain Command" in cmd.__doc__


def test_validate_arguments():

    cmd = Command(name="Plain", cmd="plain_command", description="A Plain Command")

    # If this doesn't raise an exception, the arguments are validated.

    assert cmd.validate_arguments() is None

    with pytest.raises(InvalidArgumentsError):
        cmd.validate_arguments(1, 2)

    cmd = Command(name="validate", cmd="command {one} {two} {three}")

    cmd.validate_arguments(1, 2, 3)
    cmd.validate_arguments(one="1", two="2", three="three")

    with pytest.raises(InvalidArgumentsError):
        cmd.validate_arguments(1, two=2, three=3)


def test_client_server_command():
    def response(a, b):
        return a + b

    class MyCommand(ClientServerCommand):
        pass

    class MyProxy:
        def send(self, ce: CommandExecution):
            return ce

    my_cmd = MyCommand(name="MyCommand", cmd="my_cmd {} {}", response=response)

    other = MyProxy()

    assert isinstance(my_cmd.client_call(other, 1, 2), CommandExecution)
    assert my_cmd.client_call(other, 1, 2).get_name() == "MyCommand"

    assert my_cmd.server_call(2, 1) == 0


def test_stringify_function_call():
    def function(func: Callable, *args, **kwargs):

        result = stringify_function_call(
            {"func_name": func.__name__, "args": args, "kwargs": kwargs}
        )

        return result

    result = function(function)
    assert result == "function()"

    result = function(function, 1, 2, 3)
    assert result == "function(1, 2, 3)"

    result = function(function, info="help")
    assert result == 'function(info="help")'

    result = function(function, info="help", wait=20)
    assert result == 'function(info="help", wait=20)'

    result = function(function, 1, 2, 3, info="help")
    assert result == 'function(1, 2, 3, info="help")'

    result = function(function, 1, 2, 3, wait=10)
    assert result == "function(1, 2, 3, wait=10)"

    result = stringify_function_call({})
    assert result == "unknown_function()"
