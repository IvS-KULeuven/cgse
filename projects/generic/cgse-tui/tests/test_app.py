"""Tests for the TUI screens, driven with Textual's `App.run_test()`, with a collector that needs no services."""

from textual.widgets import DataTable

from cgse_tui.app import CgseTuiApp
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens.detail import DetailScreen
from cgse_tui.screens.overview import COLUMNS
from cgse_tui.screens.overview import INDICATOR_COLUMN
from cgse_tui.screens.overview import OverviewScreen
from cgse_tui.screens.overview import format_bytes
from cgse_tui.screens.overview import format_uptime
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

    async def poll(self):
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


def test_format_bytes():
    assert format_bytes(None) == ""
    assert format_bytes(512) == "512 B"
    assert format_bytes(48_058_368) == "45.8 MiB"


def test_service_row():
    assert service_row(SERVICES[0]) == (
        "AWG1",
        "AWG1",
        "localhost",
        "ok",
        "01:02:05",
        "1234",
        "1.5",
        "45.8 MiB",
        "connected",
        "yes",
    )
    assert service_row(SERVICES[1])[3:] == ("inactive", "", "", "", "", "", "")


def test_service_row_without_device():
    service = ServiceInfo(name="Storage Manager", service_type="SM_CS", state=ServiceState.OK, has_device=False)
    assert service_row(service)[-2:] == ("–", "–")  # not applicable, an empty cell means: not known


async def test_overview_shows_the_services_of_the_collector():
    app = CgseTuiApp(collector=StaticCollector(SERVICES))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, OverviewScreen)
        table = app.screen.query_one("#services", DataTable)
        assert [str(column.label) for column in table.columns.values()] == [INDICATOR_COLUMN, *COLUMNS]
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
