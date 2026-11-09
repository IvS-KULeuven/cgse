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
    from textual.widgets import RichLog

    collector = StaticCollector(SERVICES)
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")  # opening the screen requests the status
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        app.update_overview()  # the log messages go to the log pane, also on the timer of the app
        messages = [line.text for line in app.overview.query_one("#log", RichLog).lines]

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


def text(screen, selector: str) -> str:
    """The text of a Static in the given screen, rendered as plain text."""
    from rich.console import Console
    from textual.widgets import Static

    console = Console(width=120, color_system=None)
    with console.capture() as capture:
        console.print(screen.query_one(selector, Static).content)
    return capture.get()


async def test_detail_screen_follows_the_service_live():
    from textual.widgets import Pretty

    awg = ServiceInfo(
        name="AWG1",
        service_type="AWG1",
        state=ServiceState.OK,
        server_kind="sync",
        pid=1234,
        has_device=True,
        report={"control_server": {}, "device": {"connected": True}, "details": {"frequency": 1000}},
    )
    collector = StaticCollector([awg])
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, DetailScreen)
        assert "1234" in text(screen, "#process")
        assert "frequency" in text(screen, ".section")

        restarted = ServiceInfo(name="AWG1", service_type="AWG1", state=ServiceState.OK, server_kind="sync", pid=5678)
        collector.services = [restarted]  # the collector has a new object for the restarted service
        app.update_overview()
        assert screen.service is restarted
        assert "5678" in text(screen, "#process")

        collector.services = []  # no longer registered
        app.update_overview()
        assert screen.service is restarted  # the last information is kept
        assert "no longer registered" in text(screen, "#title")
        assert screen.query_one("#panels").has_class("-dimmed")

        await pilot.press("v")
        assert screen.query_one("#raw-view").display and not screen.query_one("#panels").display
        assert isinstance(screen.query_one("#raw", Pretty), Pretty)


def test_cpu_and_memory_cells_are_coloured_by_their_level():
    from cgse_tui.data.model import Level
    from cgse_tui.screens.columns import COLUMNS_BY_KEY

    service = ServiceInfo(name="AWG1", service_type="AWG1", cpu_percent=95.0, rss=2**20, uss=2**19)
    service.cpu_level, service.memory_level = Level.CRITICAL, Level.WARNING
    cells = {key: COLUMNS_BY_KEY[key].cell(service, 0.0) for key in ("cpu", "memory", "uss", "pid")}
    assert (str(cells["cpu"].style), str(cells["memory"].style), str(cells["uss"].style)) == (
        "bold red",
        "dark_orange",
        "dark_orange",
    )
    assert str(cells["pid"].style) == ""


async def test_registry_drill_down_opens_the_details_of_a_service():
    from cgse_tui.screens.registry import RegistryTable

    registry = ServiceInfo(
        name="Service Registry",
        service_type="SERVICE_REGISTRY",
        state=ServiceState.OK,
        server_kind="registry",
        cgse_object="reg",
        report={
            "services": [
                {
                    "id": "awg-1",
                    "name": "awg1",
                    "host": "localhost",
                    "port": 2000,
                    "health": "passing",
                    "metadata": {"type": "AWG1"},
                },
            ]
        },
    )
    collector = StaticCollector([SERVICES[0], registry])
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.show_details("SERVICE_REGISTRY")
        await pilot.pause()
        screen = app.screen
        table = screen.query_one("#registrations", RegistryTable)
        assert table.row_count == 1 and screen.query_one("#registry-panel").display
        assert "1 registered" in text(screen, ".section")

        app.update_overview()  # the table is updated in place
        assert table.row_count == 1

        table.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, DetailScreen) and app.screen.service.service_type == "AWG1"
        assert not app.screen.query_one("#registry-panel").display

        await pilot.press("escape")
        assert app.screen is screen


async def test_process_manager_lists_its_core_services_with_their_state():
    from cgse_tui.screens.procman import CoreServicesTable

    procman = ServiceInfo(
        name="Process Manager",
        service_type="PM_CS",
        state=ServiceState.OK,
        server_kind="sync",
        cgse_object="pm",
        report={
            "control_server": {},
            "device": None,
            "details": {"core_processes": {"Storage Manager": "SM_CS", "Process Manager": "PM_CS"}},
        },
    )
    collector = StaticCollector([procman, SERVICES[1]])  # the Storage Manager is inactive
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.show_details("PM_CS")
        await pilot.pause()
        app.update_overview()
        screen = app.screen
        table = screen.query_one("#core-services", CoreServicesTable)
        assert table.row_count == 2 and screen.query_one("#procman-panel").display
        assert screen.query_one("#procman-panel").border_subtitle == "1 of 2 running"
        assert str(table.get_row("SM_CS")[3]) == "inactive"
        assert not screen.query_one("#registry-panel").display
        assert "2 managed" in text(screen, ".section")

        table.focus()
        table.move_cursor(row=table.get_row_index("SM_CS"))
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.service.service_type == "SM_CS"
        assert not app.screen.query_one("#procman-panel").display


def log_record(seq, message, level="INFO"):
    return {"seq": seq, "time": 1.8e9, "level": level, "name": "egse.x", "process": "cm_cs", "message": message}


async def test_the_logger_screen_shows_the_last_log_lines(monkeypatch):
    from textual.widgets import RichLog

    from cgse_tui.screens import detail

    logger_service = ServiceInfo(
        name="Logger",
        service_type="LOG_CS",
        state=ServiceState.OK,
        server_kind="command",
        cgse_object="log",
        report={"file_logger_location": "/data/log/general.log"},
    )
    answers = [
        {"last_seq": 2, "records": [log_record(1, "first"), log_record(2, "second", "WARNING")]},
        {"last_seq": 3, "records": [log_record(3, "third")]},
        {"last_seq": 1, "records": [log_record(1, "after restart")]},
    ]
    requests = []

    async def log_tail(service, after, maximum):
        requests.append((after, maximum))
        return answers[len(requests) - 1] if len(requests) <= len(answers) else {"last_seq": 1, "records": []}

    monkeypatch.setattr(detail, "TAIL_INTERVAL", 0)  # a request on every update of the screen
    collector = StaticCollector([logger_service])
    app = CgseTuiApp(collector=collector)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = DetailScreen(logger_service, log_tail=log_tail)
        app.push_screen(screen)
        await pilot.pause()
        for _ in range(3):
            app.update_overview()
            await pilot.pause(0.1)
        assert screen.has_class("-with-log") and screen.query_one("#log-panel").display
        lines = [line.text for line in screen.query_one("#log-tail", RichLog).lines]
        assert requests[:3] == [(0, 1000), (2, 1000), (3, 1000)]  # only the new records after the first request
        assert any("first" in line for line in lines) and any("third" in line for line in lines)
        assert any("the logger was restarted" in line for line in lines)
        assert lines[-1].endswith("after restart")


async def test_an_old_logger_has_no_log_lines():
    from textual.widgets import RichLog

    logger_service = ServiceInfo(name="Logger", service_type="LOG_CS", state=ServiceState.OK, cgse_object="log")

    async def log_tail(service, after, maximum):
        return {"timestamp": "now"}  # an older logger answers an unknown command with only a timestamp

    app = CgseTuiApp(collector=StaticCollector([logger_service]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = DetailScreen(logger_service, log_tail=log_tail)
        app.push_screen(screen)
        await pilot.pause(0.2)
        app.update_overview()  # the log panel shows its lines once it has a size
        await pilot.pause(0.2)
        lines = [line.text for line in screen.query_one("#log-tail", RichLog).lines]
        assert lines == ["This logger can't send its log lines, restart it with the current version."]


def test_format_record():
    from cgse_tui.screens.logtail import format_record

    line = format_record(log_record(7, "careful", "WARNING"))
    assert line.plain.endswith("WARNING  cm_cs egse.x careful")


async def test_the_sections_of_the_details_have_the_same_height():
    from cgse_tui.plugins import DetailsRenderers

    def three_sections(report, live):
        return {"One": "a", "Two": "a\nb\nc\nd", "Three": "a\nb"}

    service = ServiceInfo(
        name="AWG1",
        service_type="AWG1",
        state=ServiceState.OK,
        server_kind="sync",
        cgse_object="awg",
        report={"control_server": {}, "details": {"x": 1}},
    )
    renderers = DetailsRenderers(builtins={"awg": three_sections}, entry_points=dict)
    app = CgseTuiApp(collector=StaticCollector([service]))
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        screen = DetailScreen(service, renderers=renderers)
        app.push_screen(screen)
        await pilot.pause(0.3)
        area = screen.query_one("#details-area")
        row = area.query_one(".details-row")
        assert row.styles.grid_size_columns == 3
        heights = [panel.region.height for panel in row.query(".panel")]
        assert len(heights) == 3 and len(set(heights)) == 1  # all three as high as the highest
        assert heights[0] >= 6  # the 4 lines of the highest section and its border


async def test_a_plugin_can_put_its_sections_in_rows():
    from cgse_tui.plugins import DetailsRenderers

    def rows(report, live):
        return [{"One": "a", "Two": "a\nb"}, {"Wide": "a table that needs the full width"}]

    service = ServiceInfo(
        name="AWG1",
        service_type="AWG1",
        state=ServiceState.OK,
        server_kind="sync",
        cgse_object="awg",
        report={"control_server": {}, "details": {"x": 1}},
    )
    renderers = DetailsRenderers(builtins={"awg": rows}, entry_points=dict)
    app = CgseTuiApp(collector=StaticCollector([service]))
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        screen = DetailScreen(service, renderers=renderers)
        app.push_screen(screen)
        await pilot.pause(0.3)
        grids = list(screen.query_one("#details-area").query(".details-row"))
        assert [grid.styles.grid_size_columns for grid in grids] == [2, 1]
        wide = grids[1].query_one(".panel")
        assert wide.border_title == "Wide" and wide.region.width > 140  # the full width


async def test_f1_shows_the_help():
    from textual.widgets import Markdown

    from cgse_tui.screens.help import HelpScreen

    app = CgseTuiApp(collector=StaticCollector(SERVICES))
    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause(0.3)
        assert isinstance(app.screen, HelpScreen) and app.screen.anchor is None
        assert "The CGSE TUI" in app.screen.query_one(Markdown).source
        await pilot.press("f1")  # F1 closes it again
        await pilot.pause(0.1)
        assert isinstance(app.screen, OverviewScreen)

        await pilot.press("enter")  # the detail screen of the first service
        await pilot.pause(0.3)
        await pilot.press("f1")
        await pilot.pause(0.5)
        assert isinstance(app.screen, HelpScreen) and app.screen.anchor == "the-detail-screen"
        scroll = app.screen.query_one("#help")
        assert scroll.scroll_y > 0  # opened at the part about the detail screen
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert isinstance(app.screen, DetailScreen)


async def test_a_device_of_the_setup_that_does_not_run_is_dimmed():
    setup_device = ServiceInfo(
        name="PUNA Hexapod",
        service_type="setup:puna:PUNA_01",
        state=ServiceState.INACTIVE,
        cgse_object="puna",
        device_id="PUNA_01",
        has_device=True,
        setup_path="gse.hexapod",
    )
    app = CgseTuiApp(collector=StaticCollector([SERVICES[0], setup_device]))
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#services", DataTable)
        name, service_type = table.get_row("setup:puna:PUNA_01")[1:3]
        assert name.plain == "PUNA Hexapod" and "dim" in str(name.style) + str(name.spans)
        assert service_type.plain == ""  # no service type before it ran
