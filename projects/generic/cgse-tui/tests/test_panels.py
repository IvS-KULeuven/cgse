"""Tests for the content of the panels in the detail screen."""

import math

from rich.console import Console

from cgse_tui.data.model import Level
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.data.monitor import live_values
from cgse_tui.screens import panels
from cgse_tui.screens.columns import format_time


def render(renderable) -> str:
    console = Console(width=120, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def control_server(**kwargs) -> ServiceInfo:
    return ServiceInfo(name="AWG1", service_type="AWG1", server_kind="sync", state=ServiceState.OK, **kwargs)


def test_format_value():
    assert panels.format_value(None) == "–"
    assert panels.format_value(True) == "yes"
    assert panels.format_value(math.nan) == "NaN"
    assert panels.format_value(1 / 3) == "0.333333"
    assert panels.format_value([1, None, 2.5]) == "1, –, 2.5"
    assert panels.format_value({"pid": 1, "up": 2.0}) == "pid=1, up=2"
    assert panels.format_value(1793570256.3) == "1793570256.3"
    assert panels.format_value(1793570256.3, "start_time") == format_time(1793570256.3)


def test_live_values_without_process_information():
    sync = {"timestamp": "t", "delay": 1000, "PID": 42, "Up": 1.0, "CPU%": 3.0, "mach": [0.0, 1.0]}
    assert live_values(sync) == {"mach": [0.0, 1.0]}
    asynchronous = {"schema_version": 1, "timestamp": "t", "delay": 1000, "control_server": {}, "process": {}}
    # the components of an async control server are the same values as the details of its status report
    assert live_values({**asynchronous, "components": {"scan": "idle"}}) == {"scan": "idle"}


def test_generic_renders_groups_and_tables():
    text = render(
        panels.generic(
            {"obsid": "OBS-1", "disk": {"used": 10, "free": 90}, "registrations": [{"name": "AWG1"}, {"name": "TCU"}]}
        )
    )
    assert "obsid" in text and "OBS-1" in text
    assert "├── used" in text and "└── free" in text  # nested keys as a tree
    assert "AWG1" in text and "TCU" in text


def test_details_panel_states():
    assert "No status report received yet" in render(panels.details_panel(control_server())[0])
    old_server = control_server(report={"process": {"pid": 1}, "process_status": {}})
    assert "doesn't offer the status report" in render(panels.details_panel(old_server)[0])
    failed = control_server(report={"control_server": {}, "details": {"error": "boom"}})
    assert "error: boom" in render(panels.details_panel(failed)[0])
    hexapod = control_server(report={"control_server": {}, "details": {"alength": [math.nan, 1.0]}})
    assert "NaN, 1" in render(panels.details_panel(hexapod)[0])


def test_details_of_a_custom_server_is_its_status_without_process():
    hub = ServiceInfo(name="Notification Hub", service_type="NH_CS", report={"statistics": {"events_received": 7}})
    hub.report["process"] = {"pid": 99}
    text = render(panels.details_panel(hub)[0])
    assert "events_received" in text and "pid" not in text


def test_device_panel():
    assert not panels.has_device_panel(control_server(has_device=False))
    assert panels.has_device_panel(control_server())  # not known yet
    assert not panels.has_device_panel(ServiceInfo(name="Logger", service_type="LOG_CS"))

    service = control_server(has_device=True, connected=False, sim_mode=True, report={"device": {"connected": False}})
    text = render(panels.device_panel(service))
    assert "Connected" in text and "no" in text and "Simulator" in text
    assert "error: gone" in render(panels.device_panel(control_server(report={"device": {"error": "gone"}})))


def test_title():
    service = control_server(last_update=100.0)
    indicator = panels.state_indicator(service)
    assert panels.title(service, indicator, 103.0).plain == "■ AWG1 (AWG1) – ok – updated 3 s ago"
    assert "no longer registered" in panels.title(service, indicator, 103.0, gone=True).plain
    assert "requesting" in panels.title(service, indicator, 103.0, requesting=True).plain


def test_details_are_updated_with_the_live_values():
    service = control_server(
        report={"control_server": {}, "details": {"mach": [0.0] * 6, "alength": [1.0] * 6}},
        monitoring={"PID": 42, "CPU%": 1.0, "mach": [1.0] * 6},
    )
    details, source = panels.details_panel(service)
    text = render(details)
    assert source == panels.LIVE
    assert "1, 1, 1" in text and "alength" in text  # the live mach, the alength of the report
    assert "PID" not in text

    assert panels.details_panel(control_server(report={"control_server": {}, "details": {"a": 1}}))[1] == panels.REPORT

    # a server without the status report still has its live values
    assert panels.details_panel(control_server(monitoring={"mach": [0.0]}))[1] == panels.LIVE


def test_large_groups_are_not_unfolded():
    setup = {"gse": {f"device_{index}": {"channels": index, "unit": "CELSIUS"} for index in range(100)}}
    text = render(panels.generic({"setup_id": 1, "setup": setup, "small": {"a": 1}}))
    assert f"more than {panels.MAX_GROUP_SIZE} rows" in text
    assert "device_0" not in text
    assert "└── a" in text  # small groups are unfolded


def test_stale_service_shows_the_last_monitoring_message():
    service = control_server(monitoring={"mach": [0.0]})
    service.state = ServiceState.STALE
    assert panels.details_panel(service)[1] == panels.LAST_MONITORING


def test_count_rows():
    assert panels.count_rows({"a": 1, "b": {"c": 1, "d": 2}}, 100) == 4  # a, the heading b, c, d
    assert panels.count_rows({str(index): index for index in range(100)}, 10) == 10


def test_nested_keys_are_drawn_as_a_tree_with_the_values_aligned():
    values = {"site_id": "LAB", "gse": {"DAQ6510": {"channels": "(@101:103)", "route": {"INTERVAL": 10}}, "TCU": 1}}
    lines = render(panels.generic(values)).splitlines()
    assert [line.rstrip() for line in lines] == [
        "site_id               LAB",
        "gse",
        "├── DAQ6510",
        "│   ├── channels      (@101:103)",
        "│   └── route",
        "│       └── INTERVAL  10",
        "└── TCU               1",
    ]


def test_tables_inside_a_tree():
    text = render(panels.generic({"scan": {"tasks": [{"name": "scan", "done": False}]}}))
    assert "tasks" in text and "name" in text and "done" in text and "no" in text


def test_process_panel_shows_why_the_numbers_are_coloured():
    service = control_server(cpu_percent=95.0, rss=2**20)
    assert "average" not in render(panels.process_panel(service))
    service.cpu_level, service.cpu_reason = Level.CRITICAL, "average CPU 95 % over the last 60 s"
    rows = dict(panels.process_rows(service))
    assert rows["CPU %"].style == "bold red" and rows["RSS"].style == ""
    assert "average CPU 95 % over the last 60 s" in render(panels.process_panel(service))
