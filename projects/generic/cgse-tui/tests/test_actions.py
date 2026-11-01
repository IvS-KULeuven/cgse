"""Tests for starting, stopping and restarting services, without running services or `cgse` commands."""

import logging
import sys

import pytest

from cgse_tui.data import actions
from cgse_tui.data.actions import CommandResult
from cgse_tui.data.actions import ServiceActions
from cgse_tui.data.actions import display
from cgse_tui.data.actions import lifecycle_command
from cgse_tui.data.actions import run_command
from cgse_tui.data.model import ServiceInfo
from cgse_tui.screens.action_select import available_actions

CGSE = "/venv/bin/cgse"


@pytest.fixture(autouse=True)
def cgse_executable(monkeypatch):
    monkeypatch.setattr(actions, "cgse_executable", lambda: CGSE)


def puna(**kwargs):
    return ServiceInfo(name="puna_cs", service_type="PUNA_01", cgse_object="puna", device_id="PUNA_01", **kwargs)


def test_lifecycle_command():
    assert lifecycle_command(puna(), "stop") == [CGSE, "puna", "stop", "PUNA_01"]
    assert lifecycle_command(puna(), "start", sim=True) == [CGSE, "puna", "start", "PUNA_01", "--sim"]
    assert lifecycle_command(ServiceInfo(name="SM", service_type="SM_CS", cgse_object="sm"), "start") == [
        CGSE,
        "sm",
        "start",
    ]
    assert lifecycle_command(ServiceInfo(name="X", service_type="X"), "start") is None  # no cgse command known
    assert display([CGSE, "puna", "stop", "PUNA_01"]) == "cgse puna stop PUNA_01"


def test_available_actions():
    assert available_actions(puna(), running=True) == {"stop", "restart"}
    assert available_actions(puna(), running=False) == {"start"}
    assert available_actions(ServiceInfo(name="X", service_type="X"), running=True) == set()


async def test_run_command_returns_exit_code_and_output():
    result = await run_command([sys.executable, "-c", "import sys; print('hello'); sys.exit(3)"])
    assert result.returncode == 3 and not result.ok
    assert "hello" in result.output


async def test_run_command_runs_in_a_new_session():
    import os

    result = await run_command([sys.executable, "-c", "import os; print(os.getsid(0))"])
    assert int(result.output) != os.getsid(0)  # the services it starts don't belong to the terminal of the TUI


async def test_run_command_kills_a_command_that_takes_too_long():
    result = await run_command([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.2)
    assert result.returncode is None


class FakeCollector:
    """Is running or not according to the commands that were run."""

    def __init__(self, running: bool):
        self.running = running
        self.waits = []

    async def wait_until(self, service_type, running, timeout):
        self.waits.append((service_type, running))
        return self.running is running


class FakeRun:
    """Records the commands, a start or stop changes the state of the collector."""

    def __init__(self, collector, returncode=0, help_text=""):
        self.collector = collector
        self.returncode = returncode
        self.help_text = help_text
        self.commands = []

    async def __call__(self, command, timeout=None):
        self.commands.append(command)
        if "--help" in command:
            return CommandResult(command, 0, self.help_text)
        if self.returncode == 0:
            self.collector.running = command[2] == "start"
        return CommandResult(command, self.returncode, "line 1\nError: device PUNA_01 not found\n")


async def test_stop():
    collector = FakeCollector(running=True)
    run = FakeRun(collector)

    assert await ServiceActions(collector, run=run).perform("stop", puna())

    assert run.commands == [[CGSE, "puna", "stop", "PUNA_01"]]
    assert collector.waits == [("PUNA_01", False)]


async def test_failed_command_logs_its_output(caplog):
    collector = FakeCollector(running=False)
    run = FakeRun(collector, returncode=1)

    with caplog.at_level(logging.INFO, logger="cgse_tui.actions"):
        assert not await ServiceActions(collector, run=run).perform("start", puna())

    assert collector.waits == []  # no waiting for a command that failed
    assert "cgse puna start PUNA_01 failed with exit code 1" in caplog.text
    assert "Error: device PUNA_01 not found" in caplog.text


async def test_service_that_doesnt_register_is_reported(caplog):
    collector = FakeCollector(running=False)

    async def run(command, timeout=None):
        return CommandResult(command, 0, "")  # the command succeeds, but the service never registers

    with caplog.at_level(logging.INFO, logger="cgse_tui.actions"):
        assert not await ServiceActions(collector, run=run).perform("start", puna())

    assert "didn't register within" in caplog.text


@pytest.mark.parametrize(
    "help_text, support",
    [
        ("  --simulator, --sim  use a simulator", actions.SIMULATOR_OPTION),
        ("  --simulator  use a simulator", None),  # `--sim` would be rejected
        ("  --help", None),
    ],
)
async def test_simulator_option_of_the_start_command(help_text, support):
    collector = FakeCollector(running=True)
    run = FakeRun(collector, help_text=help_text)
    service_actions = ServiceActions(collector, run=run)

    assert await service_actions.simulator_support(puna()) == support
    assert await service_actions.simulator_support(puna()) == support  # kept, no second request
    assert run.commands == [[CGSE, "puna", "--help"], [CGSE, "puna", "start", "--help"]]


async def test_restart_with_the_simulator_option():
    collector = FakeCollector(running=True)
    run = FakeRun(collector, help_text="  --simulator, --sim  use a simulator")

    assert await ServiceActions(collector, run=run).perform("restart", puna(), simulator=True)

    assert run.commands[0] == [CGSE, "puna", "stop", "PUNA_01"]
    assert run.commands[-1] == [CGSE, "puna", "start", "PUNA_01", "--sim"]
    assert collector.waits == [("PUNA_01", False), ("PUNA_01", True)]


async def test_restart_without_the_simulator():
    collector = FakeCollector(running=True)
    run = FakeRun(collector, help_text="  --simulator, --sim  use a simulator")

    assert await ServiceActions(collector, run=run).perform("restart", puna(sim_mode=True), simulator=False)

    assert run.commands == [[CGSE, "puna", "stop", "PUNA_01"], [CGSE, "puna", "start", "PUNA_01"]]


class SimulatorProcessRun:
    """A device with a separate simulator process, like the DAQ6510: `start-sim` and `status-sim` commands."""

    def __init__(self, collector, simulator_running=False, answers_after=1):
        self.collector = collector
        self.simulator_running = simulator_running
        self.answers_after = answers_after  # number of status requests before a started simulator answers
        self.commands = []

    async def __call__(self, command, timeout=None):
        self.commands.append(command[1:])
        action = command[2]
        if action == "--help":
            return CommandResult(command, 0, "  start  start-sim  stop-sim  status-sim")
        if action == "status-sim":
            if self.simulator_running and self.answers_after > 0:
                self.answers_after -= 1
                return CommandResult(command, 1, "not running")
            return CommandResult(command, 0 if self.simulator_running else 1, "")
        if action == "start-sim":
            self.simulator_running = True
        if action in ("start", "stop"):
            self.collector.running = action == "start"
        return CommandResult(command, 0, "")


def daq6510():
    return ServiceInfo(name="DAQ6510", service_type="DAQ6510", cgse_object="daq6510")


async def test_start_with_a_simulator_process_starts_the_simulator_first():
    collector = FakeCollector(running=False)
    run = SimulatorProcessRun(collector)
    service_actions = ServiceActions(collector, run=run, simulator_interval=0.01)

    assert await service_actions.simulator_support(daq6510()) == actions.SIMULATOR_PROCESS
    assert await service_actions.perform("start", daq6510(), simulator=True)

    assert run.commands == [
        ["daq6510", "--help"],
        ["daq6510", "status-sim"],  # not running
        ["daq6510", "start-sim"],
        ["daq6510", "status-sim"],  # not answering yet
        ["daq6510", "status-sim"],
        ["daq6510", "start"],  # no --sim, the control server connects to the simulator
    ]


async def test_running_simulator_is_not_started_again():
    collector = FakeCollector(running=False)
    run = SimulatorProcessRun(collector, simulator_running=True, answers_after=0)

    assert await ServiceActions(collector, run=run).perform("start", daq6510(), simulator=True)

    assert ["daq6510", "start-sim"] not in run.commands
    assert run.commands[-1] == ["daq6510", "start"]


async def test_simulator_that_doesnt_answer_stops_the_start(caplog):
    collector = FakeCollector(running=False)
    run = SimulatorProcessRun(collector, answers_after=1000)
    service_actions = ServiceActions(collector, run=run, simulator_timeout=0.05, simulator_interval=0.01)

    with caplog.at_level(logging.INFO, logger="cgse_tui.actions"):
        assert not await service_actions.perform("start", daq6510(), simulator=True)

    assert ["daq6510", "start"] not in run.commands
    assert "the simulator doesn't answer" in caplog.text


async def test_restart_stops_when_the_stop_fails():
    collector = FakeCollector(running=True)
    run = FakeRun(collector, returncode=1)

    assert not await ServiceActions(collector, run=run).perform("restart", puna())

    assert run.commands == [[CGSE, "puna", "stop", "PUNA_01"]]
