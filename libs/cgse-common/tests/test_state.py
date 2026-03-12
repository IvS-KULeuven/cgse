from types import NoneType

from egse.setup import Setup
from egse.state import GlobalState


def test_state():
    print()
    print(f"{GlobalState.setup=}")

    assert isinstance(GlobalState.setup, (Setup, NoneType))
    assert isinstance(GlobalState.load_setup(), (Setup, NoneType))

    print(f"{GlobalState.setup=}")

    assert GlobalState.load_setup() is GlobalState.setup
    assert GlobalState.setup is not None

    print(f"{GlobalState.setup=}")
    print(f"{GlobalState.load_setup()=}")
    print(f"{GlobalState.setup=}")
