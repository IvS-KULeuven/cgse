import pytest

from symetrie_hexapod.cgse_services import joran
from symetrie_hexapod.cgse_services import puna
from symetrie_hexapod.cgse_services import zonda


@pytest.mark.parametrize("app", [puna, zonda, joran], ids=["puna", "zonda", "joran"])
def test_cgse_hexapod_subcommands(app):
    """The `cgse puna|zonda|joran` subcommands are for the service lifecycle only. There is no simulator process, the
    simulator is used with e.g. `cgse puna start --sim DEVICE_ID`."""
    names = [command.name for command in app.registered_commands]

    assert names == ["start", "stop", "status"]
