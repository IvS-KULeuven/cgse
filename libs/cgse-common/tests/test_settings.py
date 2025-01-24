from pathlib import Path

from egse.settings import Settings

HERE = Path(__file__).parent


def test_load_filename():
    # Specific test for a call with the filename and a location. This is the way the command files
    # will be loaded.

    settings = Settings.load(location=HERE / "data" / "data", filename="command.yaml")

    assert "Commands" in settings
