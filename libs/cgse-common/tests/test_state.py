from types import NoneType

from egse.setup import Setup
from egse.state import GlobalState


def test_state():
    assert GlobalState.setup is None

    # The following test depends on whether the configuration manager is running or not
    assert isinstance(GlobalState.load_setup(), (Setup, NoneType))
