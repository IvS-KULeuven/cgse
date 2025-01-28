from pathlib import Path

import pytest
import rich

from egse.env import set_local_settings
from egse.settings import Settings
from egse.settings import load_local_settings


_HERE = Path(__file__).parent


def test_memoized():

    print()
    Settings.load()

    locations = Settings.get_memoized_locations()
    rich.print(f"{locations = }")

    # There shall at least be cgse-common and cgse-core
    assert len(locations) >= 2

    for location in locations:
        if 'cgse-common' in location:
            x = Settings.get_memoized(location)
            assert x["SITE"]["SSH_PORT"] == 22
            break
    else:
        # We arrive here when there wa no break out of the loop
        pytest.fail("The 'cgse-common' package is not found in the memoized locations.")

    assert Settings.is_memoized("xxx") is False
    assert Settings.is_memoized(locations[0]) is True
    assert Settings.is_memoized(locations[1]) is True

    Settings.add_memoized("xxx", {'A': 1, "B": 2})
    assert Settings.is_memoized("xxx") is True

    Settings.clear_memoized()
    assert Settings.is_memoized("xxx") is False
    assert Settings.get_memoized_locations() == []

    Settings.load()
    rich.print(f"Settings to_string():\n{Settings.to_string()}")


def test_settings_files():
    """
    This test will check if it can find the different `settings.yaml` files that are part of the `egse` namespace.
    """

    print()

    settings = Settings.load()

    rich.print(settings)
    rich.print(settings.keys())

    site = settings.SITE

    rich.print(site)

    site = Settings.load("SITE")

    rich.print(site)


def test_load_local_settings():

    settings = load_local_settings()
    rich.print(settings)

    set_local_settings(str(_HERE / "data" / "local_settings.yaml"))

    settings = load_local_settings()
    rich.print(settings)

    site = Settings.load("SITE")
    assert site.ID == "CORE"


def test_main(capsys):

    from egse.settings import main as settings_main

    settings_main()

    captured = capsys.readouterr()

    assert 'Memoized locations' in captured.out  # noqa
