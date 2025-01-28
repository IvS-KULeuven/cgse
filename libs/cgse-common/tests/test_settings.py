from pathlib import Path

import pytest
import rich

from egse.decorators import profile
from egse.env import env_var
from egse.settings import Settings
from egse.settings import SettingsError
from egse.settings import load_settings_file

HERE = Path(__file__).parent


def test_load_filename():
    # Specific test for a call with the filename and a location. This is the way the command files
    # will be loaded.

    settings = Settings.load(location=HERE / "data" / "data", filename="command.yaml")

    assert "Commands" in settings
    assert settings.Commands['list_commands']['description'] == "Returns a list of the available commands."


def test_load_settings_file():

    settings = load_settings_file(path=HERE / "data" / "data", filename="calibration.yaml", force=True)

    assert "cal_1" in settings
    assert settings.cal_1['coefficients'] ==  [1.5, 2.1, 3.4, 4.7]


def test_load_empty_settings_file():

    settings = load_settings_file(path=HERE / "data" / "data", filename="empty_yaml_file.yaml", force=True)

    assert settings == {}


def test_unknown_settings_file():

    with pytest.raises(SettingsError, match="Settings YAML file 'non-existing.yaml' is not found"):
        _ = load_settings_file(path=HERE / "data" / "data", filename="non-existing.yaml", force=True)


def test_corrupt_yaml_file():

    with pytest.raises(SettingsError, match="Error loading YAML document"):
        _ = load_settings_file(path=HERE / "data" / "data", filename="corrupt.yaml", force=True)


def test_load_global_settings():

    # Since this is a unit test for `cgse-common`, only that Settings YAML file should be loaded.

    settings = Settings.load()

    assert "SITE" in settings.keys()
    assert "PROCESS" in settings.keys()


def test_load_global_settings_group():

    settings = Settings.load("SITE")

    assert "ID" in settings.keys() and settings.ID == "XXXX"
    assert "SSH_SERVER" in settings.keys() and settings.SSH_SERVER == "localhost"
    assert "SSH_PORT" in settings.keys() and settings.SSH_PORT == 22

    with pytest.raises(SettingsError, match="Group name 'SITE_ID' is not defined"):
        _ = Settings.load("SITE_ID")


def test_load_local_settings():

    with env_var(CGSE_LOCAL_SETTINGS=str(HERE / "data" / "data" / "local_settings.yaml")):
        settings = Settings.load(add_local_settings=True)
        assert settings.SITE['ID'] == "YYYY"

        settings = Settings.load("SITE", add_local_settings=True)
        assert settings.ID == "YYYY"

        with pytest.raises(SettingsError, match="Group name 'SITE_ID' is not defined"):
            _ = Settings.load("SITE_ID", add_local_settings=True)


def test_get_site_id():

    from egse.settings import get_site_id

    Settings.clear_memoized()

    with env_var(CGSE_LOCAL_SETTINGS=None):
        site_id = get_site_id()
        assert site_id == "XXXX"  # This should be the SITE.ID from the settings.yaml file in cgse_common

    with env_var(CGSE_LOCAL_SETTINGS=str(HERE / "data" / "data" / "local_settings.yaml")):
        Settings.load("SITE", add_local_settings=True, force=True)
        site_id = get_site_id()
        assert site_id == "YYYY"  # This should be the SITE.ID from the local_settings.yaml file


def test_profiling(capsys):

    @profile
    def do_something():
        rich.print("Running do_something()")
        return Settings.load()

    x = do_something()

    captured = capsys.readouterr()
    assert "Running do_something()" in captured.out
    assert "PROFILE" not in captured.out
    assert captured.err == ""
    assert "PACKAGES" in x

    Settings.set_profiling(True)

    x = do_something()
    captured = capsys.readouterr()
    assert "Running do_something()" in captured.out
    assert "PROFILE[1]: " in captured.out
    assert captured.err == ""
    assert "PACKAGES" in x

    Settings.set_profiling(False)
