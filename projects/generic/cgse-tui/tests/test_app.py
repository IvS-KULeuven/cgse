"""Tests for the TUI screens, driven with Textual's `App.run_test()`, with a collector that needs no services."""

from textual.widgets import DataTable

from cgse_tui.app import CgseTuiApp
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens.column_select import ColumnSelectScreen
from cgse_tui.screens.columns import COLUMNS
from cgse_tui.screens.columns import DEFAULT_COLUMNS
from cgse_tui.screens.columns import format_age
from cgse_tui.screens.columns import format_mib
from cgse_tui.screens.columns import format_uptime
from cgse_tui.screens.columns import visible_columns
from cgse_tui.screens.detail import DetailScreen
from cgse_tui.screens.overview import INDICATOR_COLUMN
from cgse_tui.screens.overview import OverviewScreen
from cgse_tui.screens.overview import service_row
from cgse_tui.screens.overview import state_indicator

SERVICES = [
    ServiceInfo(
        name="AWG1",
        service_type="AWG1",
        host="localhost",
        state=ServiceState.OK,
        server_kind="sync",
        pid=1234,
        uptime_s=3725.0,
        cpu_percent=1.5,
        rss=48_058_368,
        connected=True,
        sim_mode=True,
        device_id="AWG-01",
        report={"device": {"connected": True, "sim_mode": True}},
    ),
    ServiceInfo(name="Storage Manager", service_type="SM_CS", state=ServiceState.INACTIVE),
]


class StaticCollector:
    """Returns fixed services and records the report requests."""

    def __init__(self, services):
        self.services = services
        self.refreshed = []

    async def run(self):
        pass

    async def poll(self, reports=False):
        pass

    def snapshot(self):
        return self.services

    async def refresh_report(self, service_type):
        self.refreshed.append(service_type)
        return next(service for service in self.services if service.service_type == service_type)


def test_format_uptime():
    assert format_uptime(None) == ""
    assert format_uptime(59.9) == "00:00:59"
    assert format_uptime(3725) == "01:02:05"
    assert format_uptime(2 * 86400 + 3725) == "2d 01:02:05"


def test_format_mib():
    assert format_mib(None) == ""
    assert format_mib(512) == "0.0"
    assert format_mib(48_058_368) == "45.8"
    assert format_mib(2 * 2**30) == "2048.0"


def test_service_row():
    assert service_row(SERVICES[0]) == (
        "AWG1",
        "AWG1",
        "localhost",
        "ok",
        "01:02:05",
        "1234",
        "1.5",
        "45.8",
        "AWG-01",
        "connected",
        "yes",
    )
    assert service_row(SERVICES[1])[3:] == ("inactive", "", "", "", "", "", "", "")


def test_service_row_without_device():
    service = ServiceInfo(name="Storage Manager", service_type="SM_CS", state=ServiceState.OK, has_device=False)
    assert service_row(service)[-3:] == ("–", "–", "–")  # not applicable, an empty cell means: not known


def test_format_age():
    assert format_age(None, 100.0) == ""
    assert format_age(97.0, 100.0) == "3 s"
    assert format_age(100.0 - 312, 100.0) == "00:05:12"


def test_all_columns_have_a_value():
    hub = ServiceInfo(
        name="Metrics Hub",
        service_type="METRICS_HUB",
        port=6130,
        metadata={"server_kind": "metricshub", "collector_port": 6131},
        report={"statistics": {"received": 10, "written": 8, "dropped": 2, "queue": 0}},
        has_device=False,
    )
    cells = dict(zip((column.key for column in COLUMNS), service_row(hub, list(COLUMNS), now=0.0)))
    assert cells["other_ports"] == "collector 6131"
    assert (cells["received"], cells["sent"], cells["dropped"], cells["queue"]) == ("10", "8", "2", "0")
    assert cells["device_id"] == "–"
    assert cells["command"] == ""

    hub.cgse_object = "mh"
    cells = dict(zip((column.key for column in COLUMNS), service_row(hub, list(COLUMNS), now=0.0)))
    assert cells["command"] == "cgse mh"

    cm = ServiceInfo(name="CM", service_type="CM_CS", report={"details": {"setup_id": "00042", "obsid": None}})
    cells = dict(zip((column.key for column in COLUMNS), service_row(cm, list(COLUMNS), now=0.0)))
    assert (cells["setup"], cells["obsid"]) == ("00042", "")


def test_visible_columns_keep_the_table_order_and_the_name():
    assert [column.key for column in visible_columns(["pid", "type"])] == ["name", "type", "pid"]


async def test_overview_shows_the_services_of_the_collector():
    app = CgseTuiApp(collector=StaticCollector(SERVICES))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, OverviewScreen)
        table = app.screen.query_one("#services", DataTable)
        labels = [column.label for column in visible_columns(DEFAULT_COLUMNS)]
        assert [str(column.label) for column in table.columns.values()] == [INDICATOR_COLUMN, *labels]
        assert table.row_count == 2
        indicator, *cells = table.get_row("AWG1")
        assert indicator.plain == "■" and indicator.style == "green"
        assert [str(cell) for cell in cells] == list(service_row(SERVICES[0]))
        assert str(table.get_row_at(0)[1]) == "AWG1"  # sorted by name, not by the indicator column
        assert table.cursor_foreground_priority == "renderable"  # the indicator keeps its colour on the cursor row


async def test_overview_updates_rows_in_place():
    collector = StaticCollector(SERVICES)
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#services", DataTable)

        collector.services = [SERVICES[0]]  # the AWG1 stopped and is no longer known
        app.update_overview()
        assert table.row_count == 1

        SERVICES[0].cpu_percent = 9.0
        app.update_overview()
        assert str(table.get_row("AWG1")[7]) == "9.0"  # the CPU % column, after the indicator column
        SERVICES[0].cpu_percent = 1.5


async def test_select_a_service_shows_its_details():
    collector = StaticCollector(SERVICES)
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen)
        assert app.screen.service.service_type == "AWG1"
        assert collector.refreshed == ["AWG1"]  # a new status report is requested when the screen opens

        await pilot.press("escape")
        assert isinstance(app.screen, OverviewScreen)


async def test_refresh_is_logged_in_the_log_pane():
    from textual.widgets import RichLog

    app = CgseTuiApp(collector=StaticCollector(SERVICES))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause(0.2)
        app.update_overview()
        await pilot.pause()
        lines = [line.text for line in app.overview.query_one("#log", RichLog).lines]

    assert any("Refresh: polling the registry" in line for line in lines)
    assert any("Refresh done." in line for line in lines)


async def test_refresh_in_the_detail_screen_is_logged():
    collector = StaticCollector(SERVICES)
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")  # opening the screen requests the status
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        messages = [text for _, text in app.log_handler.drain()]

    assert sum("Requesting the status of AWG1" in text for text in messages) == 2
    assert any("Status of AWG1 received." in text for text in messages)


def test_state_indicator():
    def indicator(state, **kwargs):
        square = state_indicator(ServiceInfo(name="x", service_type="X", state=state, **kwargs))
        return square.plain, str(square.style)

    assert indicator(ServiceState.OK) == ("■", "green")  # running, no device
    assert indicator(ServiceState.OK, has_device=True, connected=True) == ("■", "green")
    assert indicator(ServiceState.OK, has_device=True, connected=False) == ("■", "dark_orange")  # no device connection
    assert indicator(ServiceState.OK, has_device=True, connected=None) == ("■", "green")  # connection not known
    assert indicator(ServiceState.STALE) == ("■", "red")  # not responding
    assert indicator(ServiceState.STALE, has_device=True, connected=False) == ("■", "red")  # not responding wins
    assert indicator(ServiceState.INACTIVE) == ("□", "")  # not running: an empty frame
    assert indicator(ServiceState.UNKNOWN) == ("■", "grey50")  # registered, no information yet


async def test_select_columns_changes_the_table_right_away():
    app = CgseTuiApp(collector=StaticCollector(SERVICES))
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.overview.query_one("#services", DataTable)

        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, ColumnSelectScreen)

        await pilot.press("n")  # no columns: only the indicator and the name are left
        await pilot.pause()
        assert [str(column.label) for column in table.columns.values()] == [INDICATOR_COLUMN, "Name"]
        assert table.row_count == 2

        await pilot.press("space")  # the first column in the list: Type
        await pilot.pause()
        assert [str(column.label) for column in table.columns.values()] == [INDICATOR_COLUMN, "Name", "Type"]
        assert [str(cell) for cell in table.get_row("AWG1")[1:]] == ["AWG1", "AWG1"]

        await pilot.press("d")  # back to the defaults
        await pilot.pause()
        assert [key.value for key in table.columns][1:] == [column.key for column in visible_columns(DEFAULT_COLUMNS)]

        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, OverviewScreen)


class RecordingActions:
    def __init__(self):
        self.performed = []

    def is_busy(self, service_type):
        return False

    async def simulator_support(self, service):
        return "process"

    async def perform(self, action, service, simulator=False):
        self.performed.append((action, service.service_type, simulator))
        return True


async def test_actions_dialog_for_the_selected_service(monkeypatch):
    from textual.widgets import Button
    from textual.widgets import Checkbox

    from cgse_tui.data import actions
    from cgse_tui.screens.action_select import ActionSelectScreen

    monkeypatch.setattr(actions, "cgse_executable", lambda: "/venv/bin/cgse")
    SERVICES[0].cgse_object = "tgf4000"
    recorder = RecordingActions()
    app = CgseTuiApp(collector=StaticCollector(SERVICES), actions=recorder)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")  # the first row: AWG1, running
            await pilot.pause()
            assert isinstance(app.screen, ActionSelectScreen)
            enabled = {button.id for button in app.screen.query(Button) if not button.disabled}
            assert enabled == {"stop", "restart", "cancel"}
            assert app.screen.focused.id == "cancel"  # Enter doesn't stop a running service
            checkbox = app.screen.query_one("#simulator", Checkbox)
            assert checkbox.value is True  # AWG1 runs with its simulator
            assert not checkbox.disabled and "cgse tgf4000 start-sim" in str(checkbox.label)

            await pilot.click("#simulator")  # restart without the simulator
            await pilot.click("#restart")
            await pilot.pause()
            assert isinstance(app.screen, OverviewScreen)
            assert recorder.performed == [("restart", "AWG1", False)]

            await pilot.press("a")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert recorder.performed == [("restart", "AWG1", False)]  # cancelled
    finally:
        SERVICES[0].cgse_object = None


async def test_columns_grow_with_updated_cells():
    service = ServiceInfo(name="Storage Manager", service_type="SM_CS", state=ServiceState.INACTIVE)
    collector = StaticCollector([service])
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.overview.query_one("#services", DataTable)
        assert table.columns["host"].content_width < len("192.168.168.175")

        service.host, service.has_device, service.connected = "192.168.168.175", True, True
        app.update_overview()
        await pilot.pause()

        assert table.columns["host"].content_width >= len("192.168.168.175")
        assert table.columns["device"].content_width >= len("connected")
