from __future__ import annotations

__all__ = [
    "create_empty_file",
    "create_text_file",
    "is_process_not_running",
    "setup_conf_data",
    "setup_data_storage_layout",
    "teardown_data_storage_layout",
]

import os
import textwrap
from pathlib import Path
from typing import List

from egse.env import get_site_id
from egse.env import set_conf_data_location
from egse.env import set_data_storage_location
from egse.env import set_log_file_location
from egse.process import is_process_running


def is_process_not_running(items: List):
    """Check if a process is not running currently."""
    return not is_process_running(items)


def setup_conf_data(tmp_data_dir: Path):

    site_id = get_site_id()
    data_root = tmp_data_dir / site_id / "conf"
    data_root.mkdir(parents=True, exist_ok=True)

    create_text_file(
        data_root / f"SETUP_{site_id}_00000_240123_120000.yaml",
        textwrap.dedent(
            f"""\
            # This is the 'Zero' Setup for {site_id}.

            Setup:
                site_id: {site_id}

                history:
                    0: Initial zero Setup for {site_id}
            """
        )
    )

    create_text_file(
        data_root / f"SETUP_{site_id}_00028_240123_120028.yaml",
        textwrap.dedent(
            f"""\
            # This is Setup nr 28 for {site_id}.

            Setup:
                site_id: {site_id}

                history:
                    0: Initial zero Setup for {site_id}
                    28: I just jumped straight to twenty eight
            """
        )
    )


def teardown_conf_data(data_dir: Path):
    ...


def teardown_data_storage_layout(data_dir: Path):
    ...


def setup_data_storage_layout(tmp_data_dir: Path) -> Path:
    """
    Create a standard layout for the data storage as expected by the CGSE. The path is created from the
    `tmp_data_dir`. The site_id is derived from the environment module using: `get_site_id()`.

    The layout with site_id = "LAB23":

        tmp_data_dir/
        └───data/
            └── LAB23
                ├── conf
                │   └── data
                ├── daily
                │   └── 20250118
                ├── log
                └── obs

    Returns:
        The path to the data folder including the site_id. In the above case,
        that is: `{tmp_data_dir}/data/LAB23`.

    """
    data_root = tmp_data_dir / get_site_id()
    data_root.mkdir(parents=True)

    tmp_dir = data_root / "daily"
    tmp_dir.mkdir()

    tmp_dir = data_root / "conf"
    tmp_dir.mkdir()

    tmp_dir = data_root / "conf" / "data"
    tmp_dir.mkdir()

    tmp_dir = data_root / "obs"
    tmp_dir.mkdir()

    tmp_dir = data_root / "log"
    tmp_dir.mkdir()

    set_data_storage_location(str(data_root))
    set_conf_data_location(str(data_root / "conf"))
    set_log_file_location(str(data_root / "log"))

    return data_root


def create_empty_file(filename: str | Path, create_folder: bool = False):
    """
    A function and context manager to create an empty file with the given
    filename. When used as a function, the file needs to be removed explicitly
    with a call to `filename.unlink()` or `os.unlink(filename)`.

    This function can be called as a context manager in which case the file will
    be removed when the context ends.

    Returns:
        The filename as a Path.
    """
    class _ContextManager:
        def __init__(self, filename: str | Path, create_folder: bool):

            self.filename = Path(filename)

            if self.filename.exists():
                raise FileExistsError(f"The empty file you wanted to create already exists: {filename}")

            if create_folder and not self.filename.parent.exists():
                self.filename.parent.mkdir(parents=True)

            with self.filename.open(mode='w'):
                pass

        def __enter__(self):
            return self.filename

        def __exit__(self, exc_type, exc_val, exc_tb):

            self.filename.unlink()

    return _ContextManager(filename, create_folder)


def create_text_file(filename: str | Path, content: str, create_folder: bool = False):
    """
    A function and context manager to create a text file with the given string
    as content. When used as a function, the file needs to be removed explicitly
    with a call to `filename.unlink()` or `os.unlink(filename)`.

    This function can be called as a context manager in which case the file will
    be removed when the context ends.

    >> with create_text_file("samples.txt", "A,B,C\n1,2,3\n4,5,6\n"):
    ..     # do something with the file or its content

    Returns:
        The filename as a Path.
    """
    class _ContextManager:
        def __init__(self, filename: str | Path, create_folder: bool):

            self.filename = Path(filename)

            if self.filename.exists():
                raise FileExistsError(f"The text file you wanted to create already exists: {filename}")

            if create_folder and not self.filename.parent.exists():
                self.filename.parent.mkdir(parents=True)

            with filename.open(mode='w') as fd:
                fd.write(content)

        def __enter__(self):
            return self.filename

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.filename.unlink()

    return _ContextManager(filename, create_folder)


# Test the helper functions

def main():
    print(f"cwd = {os.getcwd()}")

    fn = Path("xxx.txt")

    with create_empty_file(fn):
        assert fn.exists()
    assert not fn.exists()

    create_empty_file(fn)
    assert fn.exists()
    fn.unlink()
    assert not fn.exists()

    # Test the create_a_text_file() helper function

    with create_text_file(fn, textwrap.dedent(
        """\
        A,B,C,D
        1,2,3,4
        5,6,7,8
        """
    )) as filename:
        assert fn.exists()
        assert filename == fn

        print(fn.read_text())

    assert not fn.exists()

    fn = Path("data/xxx.txt")

    with create_empty_file(fn, create_folder=True):
        assert fn.exists()

    assert not fn.exists()


if __name__ == '__main__':
    main()
