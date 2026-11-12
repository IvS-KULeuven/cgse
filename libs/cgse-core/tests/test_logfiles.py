import os
from pathlib import Path

import pytest

import egse.logfiles
from egse.logfiles import is_locked
from egse.logfiles import lock_info
from egse.logfiles import lock_path
from egse.logfiles import service_type
from egse.logfiles.reader import MAX_READ_LIMIT
from egse.logfiles.reader import list_files
from egse.logfiles.reader import read_file
from egse.logfiles.server import LockFile
from egse.logfiles.server import LogFilesServer
from egse.logfiles.server import take_lock
from egse.logfiles.server import write_lock_info


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    folder = tmp_path / "log"
    folder.mkdir()
    (folder / "puna_cs.puna_01.start.log").write_text("".join(f"line {index}\n" for index in range(1000)))
    (folder / "general.log").write_text("record\n")
    (folder / ".hidden").write_text("secret\n")
    (tmp_path / "outside.txt").write_text("outside\n")
    (folder / "link.log").symlink_to(tmp_path / "outside.txt")
    (folder / "subfolder").mkdir()
    return folder.resolve()


def test_list_files(folder):
    os.utime(folder / "general.log", (1_000_000, 1_000_000))
    names = [item["name"] for item in list_files(folder)]
    assert names == ["puna_cs.puna_01.start.log", "general.log"]  # newest first, no hidden, link or folder


@pytest.mark.parametrize("name", ["../outside.txt", "/etc/passwd", ".hidden", "link.log", "subfolder", "", "nope"])
def test_read_refuses_other_files(folder, name):
    with pytest.raises(ValueError):
        read_file(folder, name)


def test_read_last_page_starts_at_a_line(folder):
    page = read_file(folder, "puna_cs.puna_01.start.log", max_bytes=100)
    assert page["end"] == page["size"]
    assert page["text"].endswith("line 999\n")
    assert page["text"].startswith("line ")
    assert page["offset"] > 0
    assert len(page["text"].encode()) <= 100


def test_read_forward_pages_join_without_gaps(folder):
    text, offset = "", 0
    while True:
        page = read_file(folder, "puna_cs.puna_01.start.log", offset, max_bytes=1000)
        assert page["text"] == "" or page["text"].endswith("\n")
        text += page["text"]
        if page["end"] == offset:
            break
        offset = page["end"]
    assert text == (folder / "puna_cs.puna_01.start.log").read_text()


def test_read_earlier_page_ends_where_the_next_starts(folder):
    last = read_file(folder, "puna_cs.puna_01.start.log", max_bytes=100)
    earlier = read_file(folder, "puna_cs.puna_01.start.log", max_bytes=100, before=last["offset"])
    assert earlier["text"].startswith("line ")
    assert earlier["end"] == last["offset"]


def test_read_follows_a_growing_file_and_partial_last_line(folder):
    path = folder / "general.log"
    page = read_file(folder, "general.log", 0)
    with path.open("a") as file:
        file.write("partial")
    page = read_file(folder, "general.log", page["end"])
    assert page["text"] == "partial"
    with path.open("a") as file:
        file.write(" line\n")
    assert read_file(folder, "general.log", page["end"])["text"] == " line\n"


def test_read_after_truncation(folder):
    page = read_file(folder, "puna_cs.puna_01.start.log", 999_999)
    assert page["truncated"] is True
    assert page["text"] == ""


def test_read_is_limited(folder):
    (folder / "big.log").write_bytes(b"x" * (MAX_READ_LIMIT + 10))
    assert len(read_file(folder, "big.log", 0, 10 * MAX_READ_LIMIT)["text"]) == MAX_READ_LIMIT


def test_lock(folder, tmp_path, monkeypatch):
    monkeypatch.setattr(egse.logfiles.tempfile, "gettempdir", lambda: str(tmp_path))
    path = lock_path(folder)
    assert not is_locked(path)
    assert lock_info(folder) is None

    fd = take_lock(path)
    assert fd is not None
    write_lock_info(fd, dict(pid=os.getpid(), port=1234))
    assert is_locked(path)
    assert lock_info(folder)["port"] == 1234
    monkeypatch.setattr(egse.logfiles.server, "LOCK_TRIES", 1)
    assert take_lock(path) is None  # one service per machine and log folder

    os.close(fd)  # the process ends, e.g. killed: the lock is released
    assert not is_locked(path)
    assert lock_info(folder) is None


def test_service_type_per_machine_and_folder(folder, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    assert service_type(folder).startswith("LF_CS@")
    assert service_type(folder) != service_type(other)
    first = service_type(folder)
    monkeypatch.setattr(egse.logfiles, "get_machine_id", lambda: "lab-pc:another-machine")
    assert service_type(folder) != first


def test_server_commands(folder):
    server = LogFilesServer(folder)
    try:
        status = server.handle("status")
        assert status["status"] == "ACK"
        assert status["folder"] == str(folder)
        assert status["registered"] is False

        files = server.handle("files")
        assert [item["name"] for item in files["files"]][0] in ("puna_cs.puna_01.start.log", "general.log")

        page = server.handle("read general.log 0")
        assert page["status"] == "ACK"
        assert page["text"] == "record\n"

        assert server.handle("read ../outside.txt")["status"] == "NACK"
        assert server.handle("read")["status"] == "NACK"
        assert server.handle("read general.log x")["status"] == "NACK"
        assert server.handle("bogus")["status"] == "NACK"
        assert server.handle("read 'unclosed")["status"] == "NACK"

        last = server.handle("read puna_cs.puna_01.start.log - 100")
        assert last["text"].endswith("line 999\n")
        earlier = server.handle(f"before puna_cs.puna_01.start.log {last['offset']} 100")
        assert earlier["end"] == last["offset"]
        assert server.handle("before puna_cs.puna_01.start.log")["status"] == "NACK"
    finally:
        server.close()


def test_read_before_a_line_longer_than_the_page(folder):
    (folder / "long.log").write_text("short\n" + "y" * 500 + "\n")
    page = read_file(folder, "long.log", max_bytes=100)
    assert page["text"] == "y" * 99 + "\n"


def test_lock_file_is_kept(folder, tmp_path, monkeypatch):
    monkeypatch.setattr(egse.logfiles.tempfile, "gettempdir", lambda: str(tmp_path))
    lock = LockFile(lock_path(folder))
    assert lock.take()
    lock.write(dict(pid=os.getpid(), port=1234))
    try:
        os.utime(lock.path, (1_000_000, 1_000_000))
        lock.keep()
        assert lock.path.stat().st_mtime > 1_000_000  # touched for the cleaner of the temporary directory

        lock.path.unlink()  # removed anyway: a new start must still see that the service runs
        assert lock_info(folder) is None
        lock.keep()
        assert lock_info(folder)["port"] == 1234
    finally:
        lock.release()
    assert lock_info(folder) is None
