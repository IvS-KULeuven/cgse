import shutil
from pathlib import Path

import pytest
from egse.resource import AmbiguityError
from egse.resource import NoSuchFileError
from egse.resource import ResourceError
from egse.resource import add_resource_id
from egse.resource import get_resource
from egse.resource import get_resource_dirs
from egse.resource import get_resource_locations
from egse.resource import get_resource_path
from egse.resource import initialise_resources
from egse.resource import print_resources
from egse.system import format_datetime
from fixtures.helpers import create_empty_file

HERE = Path(__file__).parent.resolve()


@pytest.fixture
def reset_resource():
    import egse.resource

    egse.resource.resources.clear()


def test_find_file_in_resource_location():
    print()

    data_root = Path(__file__).parent / "data"
    initialise_resources(data_root)
    print_resources()

    with pytest.raises(ResourceError):
        _ = get_resource(":/cars/volvo.txt")

    # Find file in first resource location, both with and without wildcard

    fn = get_resource(":/icons/soap_sponge.svg")
    assert "tests/data/icons/soap_sponge" in str(fn)

    fn = get_resource(":/icons/hourglass*.svg")
    assert "tests/data/icons/hourglass.svg" in str(fn)

    # Find file in second resource location, both with and without wildcard

    fn = get_resource(":/icons/keyboard.png")
    assert "tests/data/icons/keyboard" in str(fn)

    with create_empty_file(filename=data_root / "icons" / f"file_with_timestamp_{format_datetime('today')}.txt"):
        fn = get_resource(":/icons/file_with_timestamp*.txt")
        assert f"tests/data/icons/file_with_timestamp_{format_datetime('today')}.txt" in str(fn)

    # File is not found in any resource location

    with pytest.raises(NoSuchFileError, match="unknown.png") as exc_info:
        _ = get_resource(":/icons/unknown.png")
    assert exc_info.type is NoSuchFileError
    assert "No file found that matches" in exc_info.value.args[0]


def test_find_file_in_resource_location_with_wildcard():
    print()

    data_root = Path(__file__).parent / "data"

    with create_empty_file(filename=data_root / "icons" / "flat" / "screen.png", create_folder=True):
        initialise_resources(data_root)
        print_resources()

        fn = get_resource(":/icons/*/screen.png")
        assert "tests/data/icons/flat/screen" in str(fn)

        with create_empty_file(
            filename=data_root / "icons" / "flat" / f"file_with_timestamp_{format_datetime('today')}.txt"
        ):
            fn = get_resource(":/icons/*/file_with_timestamp*.txt")
            assert f"tests/data/icons/flat/file_with_timestamp_{format_datetime('today')}.txt" in str(fn)

    with create_empty_file(filename=data_root / "icons" / "double" / "flat" / "table.png", create_folder=True):
        initialise_resources(data_root)
        print_resources()

        fn = get_resource(":/icons/**/table.png")
        assert "tests/data/icons/double/flat/table" in str(fn)

        with create_empty_file(
            filename=data_root / "icons" / "double" / "flat" / f"file_with_timestamp_{format_datetime()}.txt"
        ):
            fn = get_resource(":/icons/**/file_with_timestamp*.txt")
            assert "tests/data/icons/double/flat/file_with" in str(fn)


def test_initialisation(caplog):
    print()

    # The resource module initialises itself with root=__file__

    with pytest.raises(ResourceError):
        _ = get_resource(":/icons/some-image.png")

    # This will just issue a warning log message

    initialise_resources()
    print_resources()
    print(f"{caplog.text = }")

    caplog.clear()

    initialise_resources(Path(__file__).parent / "data")
    print_resources()
    print(f"{caplog.text = }")

    fn = get_resource(":/icons/soap_sponge.svg")
    print(f"{fn = }")
    fn = get_resource(":/icons/keyboard.png")
    print(f"{fn = }")


def test_initialisation_ambiguity(reset_resource):
    print()

    # Let's first create a directory hierarchy that contains ambiguity in the sense that the same folder
    # exists at different levels in the hierarchy. `data` is a default resource location and we will use
    # that for this test.

    folders = (
        HERE / "x_resources" / "aaa" / "xdata",
        HERE / "x_resources" / "xxx" / "data",
        HERE / "x_resources" / "xxx" / "one" / "data",
        HERE / "x_resources" / "xxx" / "two" / "data",
        HERE / "x_resources" / "bbb" / "one" / "data",
    )

    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    # This function should not raise an AmbiguityError anymore

    initialise_resources(HERE / "x_resources")

    resource_locations = get_resource_locations()

    print(f"{resource_locations = }")

    for location in resource_locations["data"]:
        if location.match("*/x_resources/bbb/one/data"):
            break
    else:
        pytest.fail("Expected resource not found!")

    shutil.rmtree(HERE / "x_resources")


def test_get_resource(reset_resource):
    print()

    # Need to call initialise here because we reset the module in the fixture

    initialise_resources(Path(__file__).parent / "data")

    pathname = get_resource(":/icons/keyboard.png")
    assert isinstance(pathname, Path)
    assert "board" in str(pathname)
    assert pathname.exists()

    pathname = get_resource(":/data/data-file.txt")
    assert isinstance(pathname, Path)
    assert "data-file" in str(pathname)
    assert pathname.exists()

    with pytest.raises(NoSuchFileError):
        _ = get_resource(":/icons/no-such-file.png")

    pathname = get_resource(__file__)
    print(f"{pathname = }")
    assert isinstance(pathname, Path)
    assert "resource" in str(pathname)
    assert pathname.exists()

    with pytest.raises(NoSuchFileError):
        _ = get_resource("resource.py")


def test_get_resource_with_wildcard(reset_resource):
    print()

    root = Path(__file__).parent / "data"
    initialise_resources(root)

    # Create test folder

    test_folder = root / "data/resources"
    test_folder.mkdir(parents=True, exist_ok=True)

    try:
        # Add test files

        for fn in "001_1000_RC2.txt", "002_1001_RC3.txt", "003_1001_RC3.txt", "004_1002_RC3.txt":
            create_empty_file(test_folder / fn)

        for fn in "005_2000_RC3.txt", "002_2001_RC4.txt", "003_2001_RC4.txt", "004_2002_RC4.txt":
            create_empty_file(test_folder / "two" / "levels" / fn, create_folder=True)

        add_resource_id("RCs", root / "data/resources")

        print_resources()

        rc_file = get_resource(":/RCs/001_*.txt")
        assert "RC2" in str(rc_file)
        assert "data/data/resources" in str(rc_file)

        rc_file = get_resource(":/RCs/005_*.txt")
        assert "RC3" in str(rc_file)
        assert "data/data/resources/two" in str(rc_file)

        with pytest.raises(AmbiguityError):
            _ = get_resource(":/RCs/*_1001_*.txt")

        with pytest.raises(AmbiguityError):
            _ = get_resource(":/RCs/*/*_2001_*.txt")

        _ = get_resource(":/RCs/*/002_2001_*.txt")
        _ = get_resource(":/RCs/**/002_2001_*.txt")

        with pytest.raises(AmbiguityError):
            _ = get_resource(":/RCs/**/00?_2001_*.txt")

        with pytest.raises(AmbiguityError):
            _ = get_resource(":/RCs/00?_1001_*.txt")

        with pytest.raises(AmbiguityError):
            _ = get_resource(":/RCs/00?_2001_*.txt")

        with pytest.raises(NoSuchFileError):
            _ = get_resource(":/RCs/00?_1005*.txt")

        with pytest.raises(NoSuchFileError):
            _ = get_resource(":/RCs/*/005_200?_RC4.txt")

        with pytest.raises(NoSuchFileError):
            _ = get_resource(":/RCs/**/007_200?_RC4.txt")

        with pytest.raises(ResourceError):
            _ = get_resource(":/abc/def.txt")

        with pytest.raises(NoSuchFileError):
            _ = get_resource(":/RCs/?/def.txt")

    finally:
        shutil.rmtree(test_folder)


def test_add_resource(reset_resource):
    print()

    assert get_resource_locations() == {}

    # Need to call initialise here because we reset the module in the fixture

    root = Path(__file__).parent / "data"
    initialise_resources(root)

    resources = get_resource_locations()

    assert "icons" in resources
    assert "data" in resources

    new_dir = "fancy-plugs"
    new_resource = "plugs"

    try:
        # ValueError because the folder `new_dirt` doesn't exist yet in 'root'

        with pytest.raises(ValueError):
            add_resource_id(new_resource, root / new_dir)

        (root / new_dir).mkdir()

        add_resource_id(new_resource, root / new_dir)

        n_styles = len(get_resource_locations().get("styles", []))

        (root / "xxx").mkdir()
        (root / "yyy").mkdir()

        add_resource_id("styles", root / "xxx")
        add_resource_id("styles", root / "yyy")

        resource_locations = get_resource_locations()
        assert "styles" in resource_locations
        assert len(resource_locations["styles"]) == n_styles + 2

    finally:
        # Remove folder created for this test

        for folder in root / new_dir, root / "xxx", root / "yyy":
            shutil.rmtree(folder)


def test_get_resource_dirs(caplog):
    assert len(get_resource_dirs(__file__)) > 0

    # We have a data folder in the tests, so check if this folder is part of the resource dirs

    assert any([str(x).endswith("data") for x in get_resource_dirs(__file__)])

    caplog.clear()

    assert get_resource_dirs(None) == []
    assert "WARNING" in caplog.text


def test_get_resource_path():
    with pytest.raises(FileNotFoundError):
        get_resource_path("non-existing-file", HERE)

    # The following resources should all exist in this project
    # We don't need the return value as the function raises a FileNotFoundError
    # when the resource is not found.

    _ = get_resource_path("empty_data_file.txt", Path(__file__).parent / "data")  # in tests/data/data
    _ = get_resource_path("keyboard.png", Path(__file__).parent / "data")  # in tests/data/icons
