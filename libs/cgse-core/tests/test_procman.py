"""Tests for the devices of the Setup in the process manager: the commands and how a running device is found."""

import logging
from types import SimpleNamespace

import pytest
from egse.setup import Setup
from egse.setup import SetupDevice

from egse.procman import ProcessManagerController
from egse.procman import StartCommand
from egse.procman import StatusCommand
from egse.procman import StopCommand

SETUP = Setup(
    {
        "gse": {
            "dt8874": {"device_name": "DT8874", "cgse_object": "dt8874"},
            "hexapod": {"device_name": "PUNA Hexapod", "cgse_object": "puna", "device_id": "PUNA_01"},
            "tcs": {"device_name": "TCS", "device": "dev-tcs", "device_id": "TCS"},  # an older device node
        }
    }
)


def test_the_commands_have_the_device_argument():
    assert StartCommand("puna:PUNA_01", "cgse puna", ["PUNA_01"], True).cmd == "cgse puna start PUNA_01 --sim"
    assert StopCommand("puna:PUNA_01", ["PUNA_01"], "cgse puna").cmd == "cgse puna stop PUNA_01"
    assert StatusCommand("puna:PUNA_01", ["PUNA_01"], "cgse puna").cmd == "cgse puna status PUNA_01"
    assert StatusCommand("dt8874:", [], "cgse dt8874").cmd == "cgse dt8874 status"
    assert StatusCommand("dt8874:", None, "cgse dt8874").cmd == "cgse dt8874 status"


def test_the_device_drivers_of_the_setup(monkeypatch):
    monkeypatch.setattr("egse.procman.load_setup", lambda: SETUP)
    controller = object.__new__(ProcessManagerController)  # without the Storage Manager check

    assert controller.get_device_ids() == {
        "TCS": ("TCS", "dev-tcs", ()),
        "dt8874:": ("DT8874", None, [], SetupDevice("dt8874", None, "DT8874", "gse.dt8874")),
        "puna:PUNA_01": (
            "PUNA Hexapod",
            None,
            ["PUNA_01"],
            SetupDevice("puna", "PUNA_01", "PUNA Hexapod", "gse.hexapod"),
        ),
    }


class FakeRegistry:
    def __init__(self, services):
        self.services = services

    def list_services(self, service_type=None):
        return [service for service in self.services if service_type in (None, service["metadata"]["type"])]


def test_a_device_driver_runs_when_its_cgse_object_and_device_id_match(caplog, monkeypatch):
    pytest.importorskip("PyQt5")  # the process manager GUI
    from egse.procman.procman_ui import DeviceMonitoringWorker

    def service(service_type, cgse_object, device_id):
        return {
            "name": service_type,
            "metadata": {"type": service_type, "cgse_object": cgse_object, "device_id": device_id},
        }

    dt8874_cs, puna_cs = service("DT8874", "dt8874", None), service("PUNA_01", "puna", "PUNA_01")
    monkeypatch.setattr("egse.procman.procman_ui.ProcessManagerProxy", lambda: None)
    monkeypatch.setattr("egse.procman.procman_ui.RegistryClient", lambda: FakeRegistry([dt8874_cs, puna_cs]))
    worker = DeviceMonitoringWorker("dt8874:", [], None, SetupDevice("dt8874", None, "DT8874", "gse.dt8874"))
    assert worker.cgse_cmd == "cgse dt8874" and worker.status_cmd.cmd == "cgse dt8874 status"

    assert worker.setup_device_services() == [dt8874_cs]
    worker.setup_device = SetupDevice("puna", "PUNA_01", "PUNA Hexapod", "gse.hexapod")
    assert worker.setup_device_services() == [puna_cs]

    # the device_id in the Setup is not the one of the control server: not running, the reason is logged once
    worker.setup_device = SetupDevice("dt8874", "DT8874", "DT8874", "gse.dt8874")
    with caplog.at_level(logging.WARNING, logger="egse.procman"):
        assert worker.setup_device_services() == []
        assert worker.setup_device_services() == []
    assert [record.getMessage() for record in caplog.records] == [
        "Setup gse.dt8874 has device_id 'DT8874', but the running dt8874 control server registers device_id None: "
        "leave device_id out of the Setup for a single device."
    ]


def test_no_simulator_option_when_the_cgse_command_fails(caplog):
    pytest.importorskip("PyQt5")  # the process manager GUI
    from egse.procman.procman_ui import DeviceWidget

    widget = SimpleNamespace(cgse_cmd="false")  # a command that fails, like `cgse <unknown object>`
    with caplog.at_level(logging.WARNING, logger="egse.procman"):
        assert DeviceWidget.has_sim_option(widget) is False
    assert "`false start --help` failed (exit code 1)" in caplog.text


class FakeProcessManager:
    """A proxy of the process manager: without commands when the process manager was busy at its connection."""

    connects = []  # one per proxy: whether it connects and loads the commands
    answers = []  # one per request: the answer to `get_device_process_status`

    def __init__(self):
        self.connected = FakeProcessManager.connects.pop(0)

    def has_commands(self):
        return self.connected

    def disconnect_cs(self):
        pass

    def get_device_process_status(self, status_cmd):
        return FakeProcessManager.answers.pop(0)


def test_the_status_is_asked_again_when_the_process_manager_was_busy(caplog, monkeypatch):
    pytest.importorskip("PyQt5")  # the process manager GUI
    from egse.procman.procman_ui import DeviceMonitoringWorker

    status = {"device_id": "puna:PUNA_01", "cs_is_active": True}
    FakeProcessManager.connects = [False, True]
    FakeProcessManager.answers = ["Control Server seems to be off-line", status]
    monkeypatch.setattr("egse.procman.procman_ui.ProcessManagerProxy", FakeProcessManager)
    monkeypatch.setattr("egse.procman.procman_ui.RegistryClient", lambda: FakeRegistry([]))
    worker = DeviceMonitoringWorker("puna:PUNA_01", ["PUNA_01"], None, SetupDevice("puna", "PUNA_01", "PUNA", "gse.h"))

    with caplog.at_level(logging.WARNING, logger="egse.procman"):
        assert worker.device_process_status() is None  # the process manager is busy at the first connection
        assert worker.device_process_status() is None  # connected, the request fails
        assert worker.device_process_status() == status
    assert [record.getMessage() for record in caplog.records] == [
        "No status of puna:PUNA_01 from the Process Manager: the Process Manager doesn't answer",
        "No status of puna:PUNA_01 from the Process Manager: Control Server seems to be off-line",
    ]
    assert worker.status_problem is None


def test_the_operational_mode_button_is_painted_when_disabled(monkeypatch):
    pytest.importorskip("PyQt5")  # the process manager GUI
    from qtpy.QtGui import QPainter
    from qtpy.QtGui import QPixmap
    from qtpy.QtWidgets import QApplication
    from qtpy.QtWidgets import QMainWindow

    from egse.procman.procman_ui import DeviceWidget

    app = QApplication.instance() or QApplication([])  # noqa: F841, the widgets need it
    monkeypatch.setattr(DeviceWidget, "has_sim_option", lambda self: False)  # e.g. the DAQ6510
    monkeypatch.setattr(DeviceWidget, "has_ui_option", lambda self: False)
    device = SetupDevice("daq6510", None, "DAQ6510", "gse.DAQ6510")
    widget = DeviceWidget("daq6510:", "DAQ6510", None, [], QMainWindow(), device)

    button = widget.simulator_option_button
    button.set_selected(False)  # as the process manager does for a running control server
    button.disable()
    pixmap = QPixmap(30, 30)  # kept, the painter needs it
    painter = QPainter(pixmap)
    button.drawCustomWidget(painter)  # raised IndexError with one disabled icon
    painter.end()
