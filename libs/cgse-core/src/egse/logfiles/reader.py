"""Lists and reads the files of the log folder, for the `files` and `read` commands of the log-files service.

Only the files directly in the log folder can be read, by their bare name: no paths, no hidden files, and no symbolic
link that points out of the folder. A read returns at most `MAX_READ_LIMIT` bytes.

A page that continues where the previous one ended ends at the end of a line, except at the end of the file, where a
process may still be writing its last line. A page before a position (e.g. the last page) starts at the beginning of
a line.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_READ = 256 * 1024
"""The default number of bytes of a page."""

MAX_READ_LIMIT = 1024 * 1024
"""The maximum number of bytes of a page, a larger request is reduced to this."""


def file_path(folder: Path, name: str) -> Path:
    """The path of the file with the given name in the folder.

    Raises:
        ValueError: the name is not the bare name of a regular file in the folder.
    """
    if not name or name != Path(name).name or name.startswith("."):
        raise ValueError(f"Not a file name in the log folder: {name!r}.")
    path = folder / name
    if path.resolve().parent != folder.resolve() or not path.is_file():
        raise ValueError(f"No such file in the log folder: {name!r}.")
    return path


def list_files(folder: Path) -> list[dict[str, Any]]:
    """The regular files in the folder with their `name`, `size` and `mtime`, the most recently changed first."""
    files = []
    for path in folder.iterdir():
        if path.name.startswith("."):
            continue
        try:
            if path.resolve().parent != folder.resolve() or not path.is_file():
                continue
            stat = path.stat()
        except OSError:  # removed while listing, e.g. a rotation
            continue
        files.append(dict(name=path.name, size=stat.st_size, mtime=stat.st_mtime))
    return sorted(files, key=lambda item: item["mtime"], reverse=True)


def read_file(
    folder: Path, name: str, offset: int | None = None, max_bytes: int = MAX_READ, before: int | None = None
) -> dict[str, Any]:
    """A page of the file: from `offset` on, the page that ends at `before`, or the last page when both are None.

    A page from `offset` starts exactly there, to continue where the previous page ended, also in the middle of a line.
    A page that ends at `before` (or the last page) starts at the beginning of a line.

    Returns:
        A dictionary with `name`, `size` and `mtime` of the file, `offset` and `end` of the page (`end` is where the
        next page starts) and `text`. When `offset` is beyond the end of the file, the file was truncated or replaced
        (e.g. a rotation): `truncated` is True and the page is empty, ask for the last page again.

    Raises:
        ValueError: the name is not that of a file in the folder.
    """
    path = file_path(folder, name)
    max_bytes = max(1, min(max_bytes, MAX_READ_LIMIT))
    with path.open("rb") as file:
        stat = path.stat()
        size = stat.st_size
        answer = dict(name=name, size=size, mtime=stat.st_mtime, truncated=False)

        if offset is not None:
            if offset > size:
                return {**answer, "offset": size, "end": size, "text": "", "truncated": True}
            start = max(0, offset)
            file.seek(start)
            data = file.read(min(max_bytes, size - start))
            if start + len(data) < size and b"\n" in data:  # not at the end of the file: end with a complete line
                data = data[: data.rindex(b"\n") + 1]
        else:
            end = size if before is None else max(0, min(before, size))
            start = max(0, end - max_bytes)
            if start > 0:
                file.seek(start - 1)
                if file.read(1) != b"\n":  # in the middle of a line: start at the next line
                    aligned = start + len(file.readline())
                    if aligned < end:  # else the line is longer than the page, it's cut
                        start = aligned
            file.seek(start)
            data = file.read(end - start)

        return {**answer, "offset": start, "end": start + len(data), "text": data.decode("utf-8", errors="replace")}
