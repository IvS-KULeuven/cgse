import shutil
from pathlib import Path

import pytest

from egse.config import WorkingDirectory
from egse.config import find_dirs
from egse.config import find_file
from egse.config import find_files
from egse.config import find_first_occurrence_of_dir
from egse.config import find_root
from egse.config import get_common_egse_root

_HERE = Path(__file__).parent.resolve()


def test_find_first_occurrence_of_dir():

    assert str(find_first_occurrence_of_dir("conf", root=_HERE)).endswith("tests/data/conf")
    assert str(find_first_occurrence_of_dir("dev1", root=_HERE)).endswith("tests/data/lib/dev1")
    assert str(find_first_occurrence_of_dir("dev2", root=_HERE)).endswith("tests/data/lib/dev2")

    assert find_first_occurrence_of_dir("not-a-directory", root=_HERE) is None

    # Pass in a different root directory

    assert str(find_first_occurrence_of_dir("dev1", root=_HERE/"data")).endswith("lib/dev1")

    folders = (
        _HERE / "x_data/01/kul",
        _HERE / "x_data/02/kul",
        _HERE / "x_data/02/42/kul",
        _HERE / "x_data/03/42/kul",
        _HERE / "x_data/03/43/kul",
        _HERE / "x_data/03/43/kul/ivs",
        _HERE / "x_data/04/42/kal",
        _HERE / "x_data/04/42/kul",
    )
    for folder in folders:
        folder.mkdir(parents=True)

    assert str(find_first_occurrence_of_dir("kul", root=_HERE)).endswith("tests/x_data/01/kul")
    assert str(find_first_occurrence_of_dir("03/42/kul", root=_HERE)).endswith("tests/x_data/03/42/kul")
    assert str(find_first_occurrence_of_dir("03/*/kul", root=_HERE)).endswith("tests/x_data/03/42/kul")
    assert str(find_first_occurrence_of_dir("42/kul", root=_HERE)).endswith("tests/x_data/02/42/kul")
    assert str(find_first_occurrence_of_dir("*/42/kul", root=_HERE)).endswith("tests/x_data/02/42/kul")
    assert str(find_first_occurrence_of_dir("ivs", root=_HERE)).endswith("tests/x_data/03/43/kul/ivs")
    assert str(find_first_occurrence_of_dir("04/*/k?l", root=_HERE)).endswith("tests/x_data/04/42/kal")

    shutil.rmtree(_HERE / "x_data")


def test_find_root():

    assert find_root(None) is None
    assert find_root("/") is None
    assert find_root("/", tests=("tmp",)) == Path("/")
    assert find_root("/", tests=("non-existing-tmp",)) is None


def test_get_common_egse_root():

    print()

    # for the following test I assume that we are in the repository, but we can not test
    # the value as it will be different for each installation
    assert get_common_egse_root() is not None

    print(f"{get_common_egse_root() = }")

    # for the following test I assume that we are on a unix system (Linux or macOS)
    assert get_common_egse_root(Path("/tmp")) is None


def test_find_root_exceptions():

    assert find_root("/non-existing-path") is None
    assert find_root(None) is None


def test_get_common_egse_root_with_env():

    import os

    os.environ["COMMON_EGSE_PATH"] = "/Users/rik/git"

    # I added lru_cache to speed up the get_common_egse_root() function, but this
    # is of course fatal for test harnesses. T_HEREfore, clear the cache before and
    # after this test.

    get_common_egse_root.cache_clear()

    assert get_common_egse_root() == Path("/Users/rik/git")

    get_common_egse_root.cache_clear()

    del os.environ["COMMON_EGSE_PATH"]


def test_find_files():
    files = list(find_files("COPY*", root=get_common_egse_root()))
    assert files

    for f in files:
        assert f.name.startswith("COPY")

    # no files named 'data', only folders that are named 'data', use find_dirs for this.

    files = list(find_files("data", root=get_common_egse_root() / "src"))
    assert not files

    # When I want to find a file in a specific directory, use the in_dir keyword

    filename_pattern = "shared-lib.so"
    files = list(find_files(filename_pattern, in_dir="lib/dev1"))
    print()
    print(files)

    # The expected file is in the src/egse/lib/CentOS-7 folder, but
    # t_HERE could also be a build directory which contains the file.

    assert len(files) in (1, 2)


def test_find_dirs():
    dir_name = "dev[12]"
    dirs = list(find_dirs(dir_name))
    assert dirs

    dir_name = "dev1"
    dirs = list(find_dirs(dir_name))
    assert dirs

    dir_name = "lib/dev*"
    dirs = list(find_dirs(dir_name))
    print(dirs)
    # The third file could be in the build folder which doesn't always exists.
    # A fourth file could be in the virtual environment venv or venv38
    assert len(dirs) in (2, 3, 4)

    # use the leading '/' to prevent that another 'lib/dev' is matched.

    dir_name = "/lib/dev*"
    dirs = list(find_dirs(dir_name))
    print(dirs)
    # The second file could be in the build folder which doesn't always exists.
    assert len(dirs) in (1, 2)


def test_find_file():

    assert find_file("pyproject.toml")
    assert find_file("data-file.txt")
    assert not find_file("non-existing-file.txt")

    assert find_file("config.py", in_dir="egse")


def test_working_directory():
    import os

    # Check if a ValueError is raised when using a non-existing folder

    with pytest.raises(ValueError):
        with WorkingDirectory("/XXX"):  # There shall not be such a directory at the root folder
            pass

    # Check if indeed the context manager has changed directories

    cwd = os.getcwd()

    with WorkingDirectory(_HERE.parent) as wdir:
        assert wdir.path / "tests" == _HERE
        for file in wdir.path.glob('tests'):
            assert str(file) == str(_HERE)

    assert cwd == os.getcwd()
