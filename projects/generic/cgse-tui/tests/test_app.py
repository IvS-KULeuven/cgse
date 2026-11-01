"""Tests for the TUI screens, driven with Textual's `App.run_test()`, with a collector that needs no services."""

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
        assert [str(column.label) for column in table.columns.values()] == list(COLUMNS)
        assert table.row_count == 2
        assert [str(cell) for cell in table.get_row("AWG1")] == list(service_row(SERVICES[0]))


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
        assert str(table.get_row("AWG1")[6]) == "9.0"
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
