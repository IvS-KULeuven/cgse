"""Tests for the TUI screens, driven with Textual's `App.run_test()`."""

from textual.widgets import DataTable

from cgse_tui.app import CgseTuiApp
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens.detail import DetailScreen
from cgse_tui.screens.overview import COLUMNS
from cgse_tui.screens.overview import OverviewScreen
from cgse_tui.screens.overview import format_bytes
from cgse_tui.screens.overview import format_uptime
from cgse_tui.screens.overview import service_row

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


async def test_overview_starts_with_an_empty_table():
    app = CgseTuiApp()
    async with app.run_test():
        assert isinstance(app.screen, OverviewScreen)
        table = app.screen.query_one("#services", DataTable)
        assert [str(column.label) for column in table.columns.values()] == list(COLUMNS)
        assert table.row_count == 0


async def test_select_a_service_shows_its_details():
    app = CgseTuiApp()
    async with app.run_test() as pilot:
        app.screen.show_services(SERVICES)
        assert app.screen.query_one("#services", DataTable).row_count == 2

        await pilot.press("enter")
        assert isinstance(app.screen, DetailScreen)
        assert app.screen.service.name == "AWG1"

        await pilot.press("escape")
        assert isinstance(app.screen, OverviewScreen)


async def test_quit():
    app = CgseTuiApp()
    async with app.run_test() as pilot:
        await pilot.press("q")
    assert app.return_code == 0
