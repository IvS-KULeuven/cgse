"""Tests for the log-files screen: the files of the log folders, a file from its end, earlier pages and following."""

from pathlib import Path

import pytest
from egse.logfiles.reader import list_files
from egse.logfiles.reader import read_file
from test_app import StaticCollector
from textual.widgets import Log
from textual.widgets import Tree

from cgse_tui.app import CgseTuiApp
from cgse_tui.data.model import ServiceInfo
from cgse_tui.data.model import ServiceState
from cgse_tui.screens import files_screen
from cgse_tui.screens.action_select import ActionSelectScreen
from cgse_tui.screens.files_screen import LogFilesScreen
from cgse_tui.screens.files_screen import format_age
from cgse_tui.screens.files_screen import format_size
from cgse_tui.screens.log_screen import LogScreen

SERVICE = ServiceInfo(
    name="lf_cs@lab-pc",
    service_type="LF_CS@lab-pc-3f2a9c",
    state=ServiceState.OK,
    cgse_object="lf",
    host="127.0.0.1",
    port=40000,
    metadata={"machine_id": "lab-pc:1234", "log_folder": "/data/log"},
)


class FakeLogFiles:
    """Answers like a log-files service, from the files of a folder; records the requests."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.requests = []

    async def files(self, service):
        return dict(status="ACK", folder=str(self.folder), files=list_files(self.folder))

    async def page(self, service, name, offset=None, before=None, maximum=None):
        self.requests.append((name, offset, before, maximum))
        try:
            return dict(status="ACK", **read_file(self.folder, name, offset, maximum or 1000, before))
        except ValueError as exc:
            return dict(status="NACK", error=str(exc))


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "puna_cs.puna_01.start.log").write_text("".join(f"line {index}\n" for index in range(100)))
    (tmp_path / "general.log").write_text("record\n")
    return tmp_path


def lines_of(screen):
    return list(screen.query_one("#file-lines", Log).lines)


async def wait_for(pilot, condition, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        await pilot.pause(0.05)
        if condition():
            await pilot.pause()
            return
    raise TimeoutError("the condition wasn't met")


def file_nodes(screen):
    tree = screen.query_one("#files", Tree)
    return [leaf for machine in tree.root.children for leaf in machine.children]


async def open_screen(pilot, app, fake):
    screen = LogFilesScreen(lambda: [SERVICE], files=fake.files, page=fake.page)
    app.push_screen(screen)
    await wait_for(pilot, lambda: len(file_nodes(screen)) == 2)
    return screen


def test_format_size_and_age():
    assert format_size(812) == "812 B"
    assert format_size(14_540) == "14.2 KiB"
    assert format_size(3_250_000) == "3.1 MiB"
    assert format_age(12) == "12 s"
    assert format_age(300) == "5 min"
    assert format_age(3 * 3600 + 5) == "3 h"
    assert format_age(2 * 86400) == "2 d"


async def test_the_machines_and_their_files(folder):
    fake = FakeLogFiles(folder)
    app = CgseTuiApp(collector=StaticCollector([SERVICE]))
    async with app.run_test() as pilot:
        screen = await open_screen(pilot, app, fake)
        tree = screen.query_one("#files", Tree)
        assert [str(node.label).split()[0] for node in tree.root.children] == ["lab-pc"]
        assert {node.data[1] for node in file_nodes(screen)} == {"puna_cs.puna_01.start.log", "general.log"}


async def test_a_file_from_its_end_and_earlier_pages(folder, monkeypatch):
    monkeypatch.setattr(files_screen, "PAGE_BYTES", 100)
    fake = FakeLogFiles(folder)
    app = CgseTuiApp(collector=StaticCollector([SERVICE]))
    async with app.run_test() as pilot:
        screen = await open_screen(pilot, app, fake)
        screen.show_file(SERVICE, "puna_cs.puna_01.start.log")
        await wait_for(pilot, lambda: screen.text)
        assert screen.text.endswith("line 99\n")
        assert screen.text.startswith("line ")
        assert screen.query_one("#file-lines", Log).is_vertical_scroll_end

        while screen._file_start > 0:
            before = screen._file_start
            await pilot.press("b")
            await wait_for(pilot, lambda: screen._file_start < before)
        assert screen.text == (folder / "puna_cs.puna_01.start.log").read_text()
        assert lines_of(screen)[0] == "line 0"


async def test_the_file_is_followed(folder, monkeypatch):
    monkeypatch.setattr(files_screen, "FOLLOW_INTERVAL", 0.1)
    fake = FakeLogFiles(folder)
    app = CgseTuiApp(collector=StaticCollector([SERVICE]))
    async with app.run_test() as pilot:
        screen = await open_screen(pilot, app, fake)
        screen.show_file(SERVICE, "general.log")
        await wait_for(pilot, lambda: screen.text == "record\n")

        with (folder / "general.log").open("a") as file:
            file.write("Traceback (most")
        await wait_for(pilot, lambda: screen.text.endswith("(most"))
        with (folder / "general.log").open("a") as file:
            file.write(" recent call last):\n")
        await wait_for(pilot, lambda: screen.text.endswith("last):\n"))
        assert lines_of(screen)[:2] == ["record", "Traceback (most recent call last):"]

        (folder / "general.log").write_text("new\n")  # replaced, e.g. a rotation
        await wait_for(pilot, lambda: screen.text == "new\n")


async def test_no_service_and_an_unknown_file(folder):
    fake = FakeLogFiles(folder)
    app = CgseTuiApp(collector=StaticCollector([]))
    async with app.run_test() as pilot:
        screen = LogFilesScreen(lambda: [], files=fake.files, page=fake.page)
        app.push_screen(screen)
        await wait_for(pilot, lambda: "cgse lf start" in screen._status_text)

        screen.show_file(SERVICE, "nope.log")
        await wait_for(pilot, lambda: "nope.log" in screen._status_text)
        assert screen.text == ""


async def test_open_from_the_log_screen(folder):
    app = CgseTuiApp(collector=StaticCollector([SERVICE]))
    async with app.run_test() as pilot:
        app.push_screen(LogScreen(lambda: None))
        await pilot.pause()
        await pilot.press("F")
        await pilot.pause()
        assert isinstance(app.screen, LogFilesScreen)
        assert app.find_log_file_services() == [SERVICE]


async def test_no_actions_for_the_log_files_service_of_another_machine(monkeypatch):
    import cgse_tui.app

    monkeypatch.setattr(cgse_tui.app, "get_machine_id", lambda: "this-pc:5678")
    app = CgseTuiApp(collector=StaticCollector([SERVICE]))
    async with app.run_test() as pilot:
        notices = []
        monkeypatch.setattr(app, "notify", lambda message, **kwargs: notices.append(message))
        app.select_action(SERVICE)
        await pilot.pause()
        assert "another machine" in notices[0]
        assert not isinstance(app.screen, ActionSelectScreen)
