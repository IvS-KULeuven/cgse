"""Tests for the renderers of the Details panel: plugins, built-ins and the generic tree."""

import logging

from rich.console import Console
from rich.table import Table

from cgse_tui import details as builtin
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.plugins import DetailsRenderers
from cgse_tui.plugins import latest_details

REPORT = {"control_server": {}, "details": {"mach": [0.0] * 6}}


def render(renderable) -> str:
    console = Console(width=100, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def hexapod(**kwargs) -> ServiceInfo:
    values = dict(state=ServiceState.OK, server_kind="sync", cgse_object="puna", report=REPORT)
    values.update(kwargs)
    return ServiceInfo(name="PUNA_01", service_type="PUNA_01", **values)


def renderers(plugins=None, builtins=None, loads=None) -> DetailsRenderers:
    def entry_points():
        if loads is not None:
            loads.append(1)
        return {name: (lambda plugin=plugin: plugin) for name, plugin in (plugins or {}).items()}

    return DetailsRenderers(builtins=builtins or {}, entry_points=entry_points)


def test_latest_details():
    assert latest_details(REPORT, {"mach": [1.0] * 6, "user": [2.0] * 6}) == {"mach": [1.0] * 6, "user": [2.0] * 6}
    assert latest_details({"details": {"error": "boom"}}, {"a": 1}) == {"a": 1}


def test_the_plugin_comes_first_then_the_builtin_then_the_generic_tree():
    calls = []

    def plugin(report, live):
        calls.append((report, live))
        return {"Position": "x", "Actuators": Table()}

    sections, source = renderers({"puna": plugin}, {"puna": lambda report, live: "builtin"}).render(hexapod())
    assert [title for title, _ in sections] == ["Position", "Actuators"]
    assert source == "plugin puna"
    assert calls == [(REPORT, {})]

    sections, source = renderers(builtins={"puna": lambda report, live: "builtin"}).render(hexapod())
    assert [title for title, _ in sections] == ["Details"] and "builtin" in render(sections[0][1])
    assert source == "status report"

    sections, source = renderers().render(hexapod())
    assert "mach" in render(sections[0][1]) and source == "status report"  # the generic tree


def test_no_plugin_call_without_data():
    called = []
    service = hexapod(report={})
    sections, _ = renderers({"puna": lambda report, live: called.append(1) or "x"}).render(service)
    assert not called and "No status report received yet" in render(sections[0][1])


def test_entry_points_are_read_once():
    loads = []
    plugins = renderers({"puna": lambda report, live: "x"}, loads=loads)
    for _ in range(3):
        plugins.render(hexapod())
        plugins.render(hexapod(cgse_object="tcu"))
    assert loads == [1]


def test_a_failing_plugin_shows_the_generic_tree_and_is_logged_once(caplog):
    def plugin(report, live):
        raise RuntimeError("boom")

    plugins = renderers({"puna": plugin})
    with caplog.at_level(logging.ERROR, logger="cgse_tui"):
        for _ in range(3):
            sections, source = plugins.render(hexapod())
    assert "mach" in render(sections[0][1])
    assert source == "plugin puna failed, see the log"
    assert [r.getMessage() for r in caplog.records] == ["The details of puna couldn't be shown: RuntimeError: boom"]


def test_a_plugin_that_returns_no_renderable_shows_the_generic_tree(caplog):
    sections, source = renderers({"puna": lambda report, live: {"Position": object()}}).render(hexapod())
    assert "mach" in render(sections[0][1]) and source.endswith("failed, see the log")


def test_an_error_while_rendering_doesnt_crash(caplog):
    class Broken:
        def __rich_console__(self, console, options):
            raise ValueError("bad table")
            yield

    sections, _ = renderers({"puna": lambda report, live: Broken()}).render(hexapod())
    with caplog.at_level(logging.ERROR, logger="cgse_tui"):
        text = render(sections[0][1])
    assert "The plugin couldn't be rendered: ValueError: bad table" in text
    assert "ValueError: bad table" in caplog.text


def test_a_plugin_that_cant_be_loaded_is_skipped(caplog):
    def broken_loader():
        raise ImportError("no module")

    plugins = DetailsRenderers(builtins={}, entry_points=lambda: {"puna": broken_loader})
    with caplog.at_level(logging.WARNING, logger="cgse_tui"):
        sections, source = plugins.render(hexapod())
        plugins.render(hexapod())
    assert source == "status report"
    assert len([r for r in caplog.records if "Couldn't load" in r.getMessage()]) == 1


def test_storage_manager_builtin():
    report = {
        "control_server": {},
        "details": {
            "storage_location": "/data/LAB",
            "disk_usage": {"total": 100 * 2**30, "used": 85 * 2**30, "free": 15 * 2**30},
            "loaded_setup_id": 1,
            "obsid": None,
            "registrations": ["obsid", "TVAC"],
        },
    }
    text = render(builtin.storage(report, {}))
    assert "85 % used, 15.0 of 100.0 GiB free" in text
    assert "none running" in text and "2: obsid, TVAC" in text
    assert builtin.disk_level(85.0).value == "warning" and builtin.disk_level(95.0).value == "critical"


def test_registry_builtin():
    report = {"enforce_unique_service_types": True, "services": [{"health": "passing"}, {"health": "critical"}]}
    text = render(builtin.registry(report, {}))
    assert "2 registered, 1 critical, 1 passing" in text


def cm_setup():
    from egse.setup import Setup

    setup = Setup({"site_id": "LAB", "history": {1: "first Setup"}, "gse": {"DAQ6510": {"channels": "(@101:103)"}}})
    setup.set_private_attribute("_setup_id", "00001")
    setup.set_private_attribute("_filename", "/data/LAB/conf/SETUP_LAB_00001_261029_091500.yaml")
    return setup


def test_configuration_manager_builtin():
    report = {
        "control_server": {"hostname": "10.0.0.5"},
        "details": {"obsid_active": False, "obsid": None, "setup_id": 1, "site_id": "LAB"},
    }
    sections = builtin.configuration_manager(report, {"obsid": None, "setup": cm_setup()})
    assert list(sections) == ["Configuration", "Setup 1"]
    text = render(sections["Configuration"])
    assert "none running" in text and "SETUP_LAB_00001_261029_091500.yaml" in text
    assert "first Setup" not in text  # the history is in the Setup panel
    assert "/data/LAB/conf  on 10.0.0.5" in text  # the folder on the machine of the CM
    setup = render(sections["Setup 1"])
    assert "└── DAQ6510" in setup
    assert setup.index("gse") < setup.index("history")  # by convention the history comes last

    running = builtin.configuration_manager(report, {"obsid": "LAB_00042", "setup": cm_setup()})
    assert "running: LAB_00042" in render(running["Configuration"])


def test_the_setup_tree_is_only_rebuilt_for_another_setup():
    report = {"control_server": {}, "details": {"setup_id": 1}}
    first = builtin.configuration_manager(report, {"setup": cm_setup()})["Setup 1"]
    second = builtin.configuration_manager(report, {"setup": cm_setup()})["Setup 1"]  # a new object, same Setup
    assert first is second

    other = cm_setup()
    other.set_private_attribute("_filename", "/data/LAB/conf/SETUP_LAB_00002_261030_091500.yaml")
    assert builtin.configuration_manager({"details": {"setup_id": 2}}, {"setup": other})["Setup 2"] is not first


def test_configuration_manager_without_monitoring_message():
    report = {"control_server": {}, "details": {"obsid_active": True, "obsid": "LAB_00042", "setup_id": 1}}
    sections = builtin.configuration_manager(report, {})
    assert list(sections) == ["Configuration"]
    assert "running: LAB_00042" in render(sections["Configuration"])


def test_the_same_renderable_keeps_its_guard():
    cached = Table()
    plugins = renderers({"puna": lambda report, live: cached})
    first, _ = plugins.render(hexapod())
    second, _ = plugins.render(hexapod())
    assert first[0][1] is second[0][1]
