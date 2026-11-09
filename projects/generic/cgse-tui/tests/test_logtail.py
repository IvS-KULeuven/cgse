"""Tests for the log panel in the detail screen of the logger: filter, maximize, and the scroll position."""

import datetime

import pytest
from test_app import StaticCollector
from textual.widgets import Input
from textual.widgets import RichLog
from textual.widgets import SelectionList

from cgse_tui.app import CgseTuiApp
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens.detail import DetailScreen
from cgse_tui.screens.log_filter import LogFilterScreen
from cgse_tui.screens.logtail import MAX_LINES
from cgse_tui.screens.logtail import LogFilter
from cgse_tui.screens.logtail import parse_time

NOW = datetime.datetime(2026, 11, 9, 14, 30, 0).timestamp()

LOGGER = ServiceInfo(name="Logger", service_type="LOG_CS", state=ServiceState.OK, cgse_object="log")


def record(seq, message="message", level="INFO", process="cm_cs", name="egse.x", module="x", moment=NOW):
    return dict(seq=seq, time=moment, level=level, name=name, module=module, process=process, message=message)


def test_parse_time():
    assert parse_time("", NOW) is None
    assert parse_time("15m", NOW) == NOW - 900
    assert parse_time("2h", NOW) == NOW - 7200
    assert parse_time("30 s", NOW) == NOW - 30
    assert parse_time("14:00", NOW) == NOW - 1800  # today, local time
    assert parse_time("14:29:30", NOW) == NOW - 30
    assert parse_time("2026-11-08 14:30", NOW) == NOW - 86400
    with pytest.raises(ValueError, match="is not a time"):
        parse_time("yesterday", NOW)


def test_filter_on_levels_and_time():
    assert not LogFilter().active
    assert LogFilter().matcher(NOW)(record(1))
    matches = LogFilter(levels=frozenset({"WARNING", "ERROR"})).matcher(NOW)
    assert matches(record(1, level="ERROR")) and not matches(record(1, level="INFO"))

    matches = LogFilter(since="10m", until="14:25").matcher(NOW)
    assert matches(record(1, moment=NOW - 400))
    assert not matches(record(1, moment=NOW - 700))  # before the time range
    assert not matches(record(1, moment=NOW - 200))  # after the time range
    assert not matches({"seq": 1, "level": "INFO"})  # without a time


def test_filter_on_words():
    matches = LogFilter(process="cm_cs, SM_CS").matcher(NOW)
    assert matches(record(1, process="cm_cs")) and matches(record(1, process="sm_cs"))
    assert not matches(record(1, process="pm_cs"))

    matches = LogFilter(module="!egse.zmq").matcher(NOW)
    assert matches(record(1)) and not matches(record(1, name="egse.zmq_ser"))

    matches = LogFilter(module="hexapod").matcher(NOW)
    assert matches(record(1, name="egse", module="hexapod_cs"))  # the module when the logger name doesn't tell
    assert not matches(record(1, name="egse", module="tempcontrol"))

    matches = LogFilter(message="timeout, !retry").matcher(NOW)
    assert matches(record(1, message="Timeout after 2 s"))
    assert not matches(record(1, message="Timeout after 2 s, retry"))
    assert not matches(record(1, message="ok"))


def test_describe_filter():
    log_filter = LogFilter(levels=frozenset({"ERROR", "WARNING"}), process="cm_cs", since="15m")
    assert log_filter.describe() == "WARNING/ERROR; process cm_cs; time 15m – now"


def lines_of(screen):
    return [line.text for line in screen.query_one("#log-tail", RichLog).lines]


async def open_logger(pilot, app, log_tail=None):
    async def no_records(service, after, maximum):
        return {"last_seq": 0, "records": []}

    screen = DetailScreen(LOGGER, log_tail=log_tail or no_records)
    app.push_screen(screen)
    await pilot.pause(0.2)
    return screen


async def test_maximize_the_log_panel():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app)
        log_panel = screen.query_one("#log-panel")
        await pilot.press("m")
        assert screen.maximized is log_panel and screen.focused is screen.query_one("#log-tail")
        await pilot.press("m")
        assert screen.maximized is None

        await pilot.press("m")
        await pilot.press("escape")  # escape first restores the size of the panel
        assert app.screen is screen and screen.maximized is None
        await pilot.press("escape")
        assert app.screen is not screen


async def test_the_log_keys_are_only_in_the_logger_screen():
    other = ServiceInfo(name="SM", service_type="SM_CS", state=ServiceState.OK, cgse_object="sm")
    app = CgseTuiApp(collector=StaticCollector([other]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = DetailScreen(other)
        app.push_screen(screen)
        await pilot.pause()
        assert not screen.check_action("toggle_log_maximized", ())
        assert not screen.check_action("filter_log", ())
        assert not screen.check_action("toggle_debug", ())
        await pilot.press("m")
        assert screen.maximized is None


async def test_filter_the_log_lines(monkeypatch):
    monkeypatch.setattr("cgse_tui.screens.detail.TAIL_INTERVAL", 0)
    records = [record(1, "first"), record(2, "careful", "WARNING", process="sm_cs"), record(3, "broken", "ERROR")]
    restarted = []

    async def log_tail(service, after, maximum):
        if restarted:
            return {"last_seq": 1, "records": [record(1, "after restart", "ERROR")] if after != 1 else []}
        return {"last_seq": 3, "records": [r for r in records if r["seq"] > after]}

    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app, log_tail)
        app.update_overview()  # the log panel shows its lines once it has a size
        await pilot.pause(0.2)
        assert [line.split()[-1] for line in lines_of(screen)] == ["first", "careful", "broken"]

        await pilot.press("f")
        assert isinstance(app.screen, LogFilterScreen)
        app.screen.query_one("#levels", SelectionList).select("WARNING")
        app.screen.query_one("#levels", SelectionList).select("ERROR")
        app.screen.query_one("#process", Input).value = "!sm_cs"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.screen is screen
        assert [line.split()[-1] for line in lines_of(screen)] == ["broken"]
        assert "filter: WARNING/ERROR; process !sm_cs, 1 of 3 shown" in screen.query_one("#log-panel").border_subtitle

        restarted.append(True)
        app.update_overview()  # new records pass the filter too, the marker is always shown
        await pilot.pause(0.2)
        assert lines_of(screen)[1:] == ["--- the logger was restarted ---", lines_of(screen)[2]]
        assert lines_of(screen)[2].endswith("after restart")

        await pilot.press("f")
        await pilot.press("ctrl+r")  # clear all
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert len(lines_of(screen)) == 5 and not screen.query_one("#log-panel").border_subtitle.count("filter")


async def test_a_wrong_time_keeps_the_filter_dialog_open():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app)
        await pilot.press("f")
        dialog = app.screen
        dialog.query_one("#since", Input).value = "soon"
        await pilot.press("ctrl+s")
        assert app.screen is dialog and "is not a time" in str(dialog.query_one("#error").render())
        await pilot.press("escape")
        assert app.screen is screen and not screen._log_filter.active


async def test_the_log_keeps_its_position_when_scrolled_up():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app)
        log = screen.query_one("#log-tail", RichLog)

        screen._append_log([record(seq, f"line {seq}") for seq in range(1, 101)])
        await pilot.pause()
        assert log.is_vertical_scroll_end  # follows the new lines
        screen._append_log([record(seq, f"line {seq}") for seq in range(101, 111)])
        await pilot.pause()
        assert log.is_vertical_scroll_end and log.lines[-1].text.endswith("line 110")

        log.scroll_to(y=20, animate=False, immediate=True)
        await pilot.pause()
        top = log.lines[int(log.scroll_y)].text
        screen._append_log([record(seq, f"line {seq}") for seq in range(111, 121)])
        await pilot.pause()
        assert log.scroll_y == 20 and log.lines[int(log.scroll_y)].text == top
        assert "scrolled, end to follow" in screen.query_one("#log-panel").border_subtitle

        # the oldest lines are removed beyond MAX_LINES: the view moves up with its lines
        screen._append_log([record(seq, f"line {seq}") for seq in range(121, MAX_LINES + 6)])
        await pilot.pause()
        assert len(log.lines) == MAX_LINES
        assert log.scroll_y == 15 and log.lines[int(log.scroll_y)].text == top

        await pilot.press("m")  # the log has the focus, end goes to the end, and the view follows again
        await pilot.press("end")
        await pilot.pause()
        screen._append_log([record(MAX_LINES + 6, "the last line")])
        await pilot.pause()
        assert log.is_vertical_scroll_end and log.lines[-1].text.endswith("the last line")
        assert "end to follow" not in screen.query_one("#log-panel").border_subtitle


async def test_end_follows_the_log_again_without_maximizing():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app)
        log = screen.query_one("#log-tail", RichLog)
        screen._append_log([record(seq, f"line {seq}") for seq in range(1, 101)])
        await pilot.pause()
        log.scroll_to(y=10, animate=False, immediate=True)
        await pilot.pause()
        assert screen.focused is log
        await pilot.press("end")
        await pilot.pause()
        screen._append_log([record(101, "the last line")])
        await pilot.pause()
        assert log.is_vertical_scroll_end and log.lines[-1].text.endswith("the last line")


async def test_the_filter_dialog_fits_a_small_terminal():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await open_logger(pilot, app)
        await pilot.press("f")
        await pilot.pause()
        dialog = app.screen
        for selector in ("#levels", "#until", "#apply"):
            region = dialog.query_one(selector).region
            assert region.height and dialog.region.contains_region(region), selector


def test_dim_alone_is_no_filter():
    assert not LogFilter(dim=True).active
    assert LogFilter(levels=frozenset({"ERROR"}), dim=True).active


async def test_dim_the_lines_that_do_not_pass():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app)
        screen._append_log([record(1, "first"), record(2, "broken", "ERROR"), {"marker": "--- marker ---"}])
        await pilot.pause()

        await pilot.press("f")
        app.screen.query_one("#levels", SelectionList).select("ERROR")
        await pilot.click("#dim")
        await pilot.press("ctrl+s")
        await pilot.pause()
        log = screen.query_one("#log-tail", RichLog)
        assert [line.text.split()[-1] for line in log.lines] == ["first", "broken", "---"]  # all lines are shown
        dimmed = [
            all(segment.style and segment.style.dim for segment in line if segment.text.strip()) for line in log.lines
        ]
        assert dimmed == [True, False, True]  # the line that doesn't pass, and the marker as always
        assert "1 of 2 match, others dimmed" in screen.query_one("#log-panel").border_subtitle

        await pilot.press("f")
        assert app.screen.query_one("#dim").value  # the dialog opens with the current choice
        await pilot.click("#dim")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert [line.text.split()[-1] for line in log.lines] == ["broken", "---"]  # hidden again


def test_hide_debug():
    assert not LogFilter(hide_debug=True).active  # no criteria, the panel shows no counts
    assert LogFilter(hide_debug=True).hides(record(1, level="DEBUG"))
    assert not LogFilter(hide_debug=True).hides(record(1, level="INFO"))
    assert not LogFilter().hides(record(1, level="DEBUG"))


async def test_d_hides_the_debug_lines_also_when_dimmed():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app)
        log = screen.query_one("#log-tail", RichLog)
        screen._append_log([record(1, "chatter", "DEBUG"), record(2, "info"), record(3, "broken", "ERROR")])
        await pilot.pause()

        def words():
            return [line.text.split()[-1] for line in log.lines]

        await pilot.press("d")
        await pilot.pause()
        assert words() == ["info", "broken"] and "DEBUG hidden" in screen.query_one("#log-panel").border_subtitle
        await pilot.press("d")
        await pilot.pause()
        assert words() == ["chatter", "info", "broken"]

        # dimmed: DEBUG is hidden although it is one of the selected levels
        screen._set_log_filter(LogFilter(levels=frozenset({"DEBUG", "ERROR"}), dim=True, hide_debug=True))
        await pilot.pause()
        assert words() == ["info", "broken"]
        assert "1 of 2 match, others dimmed · DEBUG hidden" in screen.query_one("#log-panel").border_subtitle

        await pilot.press("f")  # the dialog shows it, and unchecking shows the DEBUG lines again
        assert app.screen.query_one("#hide-debug").value
        await pilot.click("#hide-debug")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert words() == ["chatter", "info", "broken"]


async def test_w_wraps_the_long_log_lines():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_logger(pilot, app)
        log = screen.query_one("#log-tail", RichLog)
        screen._append_log([record(1, "x" * 300), record(2, "debug " + "y" * 300, "DEBUG")])
        await pilot.pause()
        assert not log.wrap and len(log.lines) == 2  # a line per message

        await pilot.press("w")  # the log has the focus in the logger screen
        await pilot.pause()
        assert log.wrap and len(log.lines) > 4

        await pilot.press("d")  # a filter change writes the lines again, still wrapped
        await pilot.pause()
        assert log.wrap and len(log.lines) > 2 and all("y" not in line.text for line in log.lines)
