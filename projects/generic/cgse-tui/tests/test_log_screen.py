"""Tests for the log screen: the window of log records read by the logger, moving it, and the tree of loggers."""

import datetime
import time

from test_app import StaticCollector
from textual.widgets import Input

from cgse_tui.app import CgseTuiApp
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens.detail import DetailScreen
from cgse_tui.screens.log_filter import LogFilterScreen
from cgse_tui.screens.log_screen import GotoScreen
from cgse_tui.screens.log_screen import LoggerTree
from cgse_tui.screens.log_screen import LogScreen
from cgse_tui.screens.log_screen import ProcessTree
from cgse_tui.screens.log_screen import format_span
from cgse_tui.screens.logtail import LogFilter
from cgse_tui.screens.logtail import selects_logger
from cgse_tui.screens.record_view import RecordView

LOGGER = ServiceInfo(
    name="Logger", service_type="LOG_CS", state=ServiceState.OK, cgse_object="log", host="127.0.0.1", port=6105
)

END = datetime.datetime(2026, 11, 9, 15, 0, 0).timestamp()

NAMES = ("egse", "egse.hexapod.puna", "egse.hexapod", "egse.registry", "cgse_tui")

PROCESSES = ("cm_cs", "sm_cs", "rs_cs")


def make_records(since, until, step=60):
    """A record every `step` seconds, the logger names and the processes in turn."""
    count = int((until - since) // step)
    return [
        dict(
            time=since + i * step,
            level="INFO",
            name=NAMES[i % len(NAMES)],
            module="m",
            process=PROCESSES[i % len(PROCESSES)],
            message=f"r{i}",
        )
        for i in range(count)
    ]


class FakeHistory:
    """Answers the `history` requests from records made on the fly, in pages; records the requests."""

    def __init__(self, answer=None):
        self.requests = []
        self.answer = answer

    async def __call__(self, service, since, until, maximum, cursor=None):
        self.requests.append((since, until, maximum, cursor))
        if self.answer is not None:
            return self.answer
        records = make_records(since, until)
        start = int(cursor or 0)
        page = records[start : start + maximum]
        more = start + maximum < len(records)
        return dict(status="ACK", records=page, cursor=str(start + maximum) if more else None)


def lines_of(screen):
    return screen.query_one("#log-lines", RecordView).plain_lines()


def window_text(screen):
    return str(screen.query_one("#window").render())


async def loaded(pilot, screen, timeout=5.0):
    """Waits until the screen has asked for its window and received the answers."""
    for _ in range(int(timeout / 0.05)):
        await pilot.pause(0.05)
        if screen._generation > 0 and not screen._loading:
            await pilot.pause()
            return
    raise TimeoutError("the window wasn't loaded")


class FakeTail:
    """The `tail` of the logger: the records added with `add()`, numbered; records the requests."""

    def __init__(self, records=None, seq=0):
        self.records = []
        self.seq = seq
        self.requests = []
        self.old = records is False  # an older logger without the tail command

    def add(self, *records):
        for record in records:
            self.seq += 1
            self.records.append(dict(record, seq=self.seq))

    async def __call__(self, service, after, maximum):
        self.requests.append((after, maximum))
        if self.old:
            return {"timestamp": "now"}
        records = [r for r in self.records if r["seq"] > after]
        return dict(last_seq=self.seq, records=records[-maximum:] if maximum > 0 else [])


def new_record(message, moment=None, name="egse.live", level="INFO"):
    moment = time.time() if moment is None else moment
    return dict(time=moment, level=level, name=name, module="m", process="cm_cs", message=message)


async def open_screen(pilot, app, history, tail=None, **kwargs):
    screen = LogScreen(lambda: LOGGER, history=history, tail=tail or FakeTail(), **kwargs)
    app.push_screen(screen)
    await loaded(pilot, screen)
    return screen


def test_format_span():
    assert [format_span(s) for s in (300, 1800, 3600, 3 * 3600, 86400, 2 * 86400)] == [
        "5 min",
        "30 min",
        "1 h",
        "3 h",
        "1 day",
        "2 days",
    ]


def test_selects_logger():
    assert selects_logger(frozenset({"egse"}), "egse")
    assert selects_logger(frozenset({"egse"}), "egse.hexapod")
    assert not selects_logger(frozenset({"egse"}), "egsex")
    assert not selects_logger(frozenset({"egse.hex"}), "egse.hexapod")  # whole parts, no substrings
    assert selects_logger(frozenset({"=egse"}), "egse")
    assert not selects_logger(frozenset({"=egse"}), "egse.hexapod")

    log_filter = LogFilter(loggers=frozenset({"egse.hexapod"}))
    assert log_filter.active and log_filter.describe() == "loggers egse.hexapod"
    matches = log_filter.matcher()
    assert matches(dict(name="egse.hexapod.puna")) and not matches(dict(name="egse"))


async def test_the_window_in_pages(monkeypatch):
    monkeypatch.setattr("cgse_tui.screens.log_screen.PAGE_RECORDS", 7)
    history = FakeHistory()
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, history, until=END)
        assert (screen.since, screen.until) == (END - 3600, END)
        assert len(screen.records) == 60 and len(history.requests) == 9  # 60 records in pages of 7
        assert [request[3] for request in history.requests[:2]] == [None, "7"]
        assert lines_of(screen)[0].endswith("r0")
        assert "Mon 2026-11-09 14:00:00 – Mon 2026-11-09 15:00:00 · 1 h · 60 records" in window_text(screen)


async def test_move_the_window():
    history = FakeHistory()
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, history, until=END)
        await pilot.press("left_square_bracket")
        await loaded(pilot, screen)
        assert (screen.since, screen.until) == (END - 7200, END - 3600)
        await pilot.press("right_square_bracket")
        await loaded(pilot, screen)
        assert screen.until == END

        await pilot.press("p")  # yesterday, the same time
        await loaded(pilot, screen)
        assert (screen.since, screen.until) == (END - 86400 - 3600, END - 86400)
        assert history.requests[-1][:2] == (END - 86400 - 3600, END - 86400)
        await pilot.press("n")
        await loaded(pilot, screen)
        assert screen.until == END

        await pilot.press("minus")  # 30 min, the same start
        await loaded(pilot, screen)
        assert (screen.since, screen.until) == (END - 3600, END - 1800)
        assert len(screen.records) == 30
        await pilot.press("plus")
        await pilot.press("plus")
        await loaded(pilot, screen)
        assert (screen.since, screen.until) == (END - 3600, END + 7200)  # 3 h, from the same start

        await pilot.press("g")
        await pilot.pause()
        assert isinstance(app.screen, GotoScreen)
        app.screen.query_one(Input).value = "2026-11-08 10:00"
        await pilot.press("enter")
        await loaded(pilot, screen)
        start = datetime.datetime(2026, 11, 8, 10, 0).timestamp()
        assert app.screen is screen and (screen.since, screen.until) == (start, start + 3 * 3600)


async def test_forward_stops_at_the_latest_window():
    history = FakeHistory()
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, history)  # the latest window, until now
        assert "live" in window_text(screen) and screen.live
        until = screen.until
        await pilot.press("left_square_bracket")
        await loaded(pilot, screen)
        assert "live" not in window_text(screen) and not screen.live
        await pilot.press("right_square_bracket")
        await pilot.press("right_square_bracket")
        await loaded(pilot, screen)
        assert "live" in window_text(screen) and screen.live and screen.until >= until


async def test_the_tree_of_loggers_filters():
    history = FakeHistory()
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, history, until=END)
        tree = screen.query_one("#loggers", LoggerTree)
        top = [str(node.label) for node in tree.root.children]
        assert top == ["○ cgse_tui 12", "○ egse 48"]
        egse = tree.root.children[1]
        assert [node.data for node in egse.children] == ["=egse", "egse.hexapod", "egse.registry"]
        assert str(egse.children[0].label) == "○ egse itself 12"
        assert str(egse.children[1].label) == "○ hexapod 24"  # with egse.hexapod.puna

        tree.focus()
        tree.move_cursor(egse.children[1])
        await pilot.press("space")
        await pilot.pause()
        assert screen.log_filter.loggers == {"egse.hexapod"}
        assert len(lines_of(screen)) == 24
        assert str(egse.children[1].label).startswith("● hexapod")

        tree.move_cursor(egse.children[0])
        await pilot.press("space")
        await pilot.pause()
        assert screen.log_filter.loggers == {"egse.hexapod", "=egse"}
        assert len(lines_of(screen)) == 36

        # The filter dialog keeps the selected loggers.
        await pilot.press("f")
        await pilot.pause()
        assert isinstance(app.screen, LogFilterScreen)
        app.screen.query_one("#message", Input).value = "r1"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert screen.log_filter.loggers == {"egse.hexapod", "=egse"} and screen.log_filter.message == "r1"

        await pilot.press("c")
        await pilot.pause()
        assert screen.log_filter.loggers == frozenset()

        # The tree keeps the selection and the cursor when the next window is loaded.
        await pilot.press("space")
        await pilot.press("left_square_bracket")
        await loaded(pilot, screen)
        assert screen.log_filter.loggers == {"=egse"}
        assert tree.cursor_node.data == "=egse"


async def test_an_older_logger_or_no_logger():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, FakeHistory(answer={"timestamp": "now"}), until=END)
        assert "restart it with the current version" in window_text(screen)
        app.pop_screen()

        screen = await open_screen(pilot, app, FakeHistory(answer={"status": "NACK", "error": "bad cursor"}))
        assert "the logger: bad cursor" in window_text(screen)
        app.pop_screen()

        screen = LogScreen(lambda: None, history=FakeHistory(), tail=FakeTail())
        app.push_screen(screen)
        await loaded(pilot, screen)
        assert "the logger is not known (yet)" in window_text(screen)
        assert "loading" not in window_text(screen)


async def test_open_the_log_screen():
    unreachable = ServiceInfo(name="Logger", service_type="LOG_CS", state=ServiceState.OK, cgse_object="log")
    app = CgseTuiApp(collector=StaticCollector([unreachable]))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("L")
        await pilot.pause()
        assert isinstance(app.screen, LogScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, LogScreen)
        app.push_screen(DetailScreen(unreachable, log_tail=lambda *args: _no_tail()))
        await pilot.pause()
        await pilot.press("L")
        await pilot.pause()
        assert isinstance(app.screen, LogScreen)

    app = CgseTuiApp(collector=StaticCollector([unreachable]), logs=True)
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, LogScreen)


async def _no_tail():
    return {"last_seq": 0, "records": []}


async def wait_for(pilot, condition, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        await pilot.pause(0.05)
        if condition():
            return
    raise TimeoutError("the condition wasn't met")


async def test_the_latest_window_is_live(monkeypatch):
    monkeypatch.setattr("cgse_tui.screens.log_screen.TAIL_INTERVAL", 0.05)
    tail = FakeTail(seq=500)
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, FakeHistory(), tail=tail)
        assert screen.live and tail.requests[0] == (0, 0)  # the position before the files are read
        count = len(screen.records)

        # A record that was read from the files too is shown once; the traceback is only in the file.
        last = screen.records[-1]
        screen.records[-1]["message"] = last["message"] + "\nTraceback ..."
        tail.add(dict(last, message=last["message"].split("\n")[0]), new_record("new one"))
        await wait_for(pilot, lambda: len(screen.records) == count + 1)
        assert screen.records[-1]["message"] == "new one"
        assert lines_of(screen)[-1].endswith("new one")
        await wait_for(pilot, lambda: tail.requests[-1][0] == 502)  # the next request after the last record
        view = screen.query_one("#log-lines", RecordView)
        assert view.follows

        # Scrolled up, the view stays where it is.
        view.scroll_home(animate=False, immediate=True)
        await pilot.pause()
        assert "scrolled, end to follow" in screen.query_one("#log-panel").border_subtitle
        tail.add(new_record("another"))
        await wait_for(pilot, lambda: screen.records[-1]["message"] == "another")
        assert view.scroll_y == 0
        await pilot.press("end")
        await pilot.pause()
        assert view.follows

        # The logger restarted: the sequence numbers start again.
        tail.records, tail.seq = [], 0
        tail.add(new_record("after restart"))
        await wait_for(pilot, lambda: screen.records[-1]["message"] == "after restart")

        # An older window is not live, the latest window is live again.
        await pilot.press("left_square_bracket")
        await loaded(pilot, screen)
        assert not screen.live
        requests = len(tail.requests)
        await pilot.pause(0.3)
        assert len(tail.requests) == requests
        await pilot.press("t")
        await loaded(pilot, screen)
        assert screen.live


async def test_the_live_window_moves(monkeypatch):
    monkeypatch.setattr("cgse_tui.screens.log_screen.TAIL_INTERVAL", 0.05)
    monkeypatch.setattr("cgse_tui.screens.log_screen.TRIM_RECORDS", 1)
    tail = FakeTail()
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        history = FakeHistory()
        screen = await open_screen(pilot, app, history, tail=tail, span=300)  # a record every 60 s
        oldest = history.requests[0][0]  # the first record is at the start of the window
        tail.add(new_record("new"))
        await wait_for(pilot, lambda: screen.records[-1]["message"] == "new")
        # The window moved, the oldest record is no longer in it.
        assert screen.since > oldest and screen.records[0]["time"] > oldest
        assert len(lines_of(screen)) == len(screen.records)


async def test_no_live_updates_from_an_older_logger():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, FakeHistory(), tail=FakeTail(records=False))
        assert not screen.live
        assert "no live updates" in window_text(screen) and "the latest" in window_text(screen)


async def test_the_processes_pane_filters():
    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await open_screen(pilot, app, FakeHistory(), until=END)
        processes = screen.query_one("#processes", ProcessTree)
        assert [str(node.label) for node in processes.root.children] == ["○ cm_cs 20", "○ rs_cs 20", "○ sm_cs 20"]
        # The two panes are above each other at the left.
        loggers_panel, processes_panel = screen.query_one("#loggers-panel"), screen.query_one("#processes-panel")
        assert loggers_panel.region.x == processes_panel.region.x
        assert processes_panel.region.y > loggers_panel.region.y

        processes.focus()
        processes.move_cursor(processes.root.children[1])
        await pilot.press("space")
        await pilot.pause()
        assert screen.log_filter.processes == {"rs_cs"}
        assert len(lines_of(screen)) == 20 and all(" rs_cs " in line for line in lines_of(screen))
        assert str(processes.root.children[1].label).startswith("● rs_cs")
        assert "processes rs_cs" in screen.query_one("#log-panel").border_subtitle

        # With loggers selected too, a record must be of both.
        loggers = screen.query_one("#loggers", LoggerTree)
        loggers.focus()
        loggers.move_cursor(loggers.root.children[0])  # cgse_tui: every 5th record
        await pilot.press("space")
        await pilot.pause()
        assert len(lines_of(screen)) == 4  # 12 records of cgse_tui, 4 of them of rs_cs

        await pilot.press("c")  # clears both
        await pilot.pause()
        assert screen.log_filter.loggers == frozenset() and screen.log_filter.processes == frozenset()
        assert len(lines_of(screen)) == 60


async def test_f1_shows_the_help_of_the_log_screen():
    from cgse_tui.screens.help import DETAIL_SCREEN_ANCHOR
    from cgse_tui.screens.help import LOG_SCREEN_ANCHOR
    from cgse_tui.screens.help import HelpScreen

    app = CgseTuiApp(collector=StaticCollector([LOGGER]))
    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.pause()
        app.push_screen(HelpScreen(DETAIL_SCREEN_ANCHOR))
        await pilot.pause(0.5)
        detail_part = app.screen.query_one("#help").scroll_y
        app.pop_screen()

        screen = await open_screen(pilot, app, FakeHistory(), until=END)
        await pilot.press("f1")
        await pilot.pause(0.5)
        assert isinstance(app.screen, HelpScreen) and app.screen.anchor == LOG_SCREEN_ANCHOR
        assert app.screen.query_one("#help").scroll_y > detail_part > 0  # the log screen comes after the detail screen
        await pilot.press("f1")
        await pilot.pause(0.1)
        assert app.screen is screen
