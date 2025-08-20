__all__ = [
    "GlobalState",
]

import abc
import textwrap

from egse.setup import Setup
from egse.setup import load_setup
from egse.setup import setup_ctx


class StateError(Exception):
    pass


class UnknownStateError(StateError):
    pass


class IllegalStateTransition(StateError):
    pass


class NotImplementedTransition(StateError):
    pass


class ConnectionStateInterface(abc.ABC):
    """
    A class used to enforce the implementation of the _connection_ interface
    to model the state of a (network) connection.

    Subclasses only need to implement those methods that are applicable to
    their state.

    """

    # This class is to enforce the implementation of the interface on both the
    # model, i.e. the Proxy, and the State class. At the same time, it will allow
    # the State subclasses to implement only those methods that are applicable
    # in their state.

    @abc.abstractmethod
    def connect(self, proxy):
        pass

    @abc.abstractmethod
    def disconnect(self, proxy):
        pass

    @abc.abstractmethod
    def reconnect(self, proxy):
        pass


class _GlobalState:
    """
    This class implements global state that is shared between instances of this class.
    """

    def __call__(self, *args, **kwargs):
        return self

    @property
    def setup(self) -> Setup | None:
        """
        Returns the currently active Setup for this process.

        NOTE: The returned Setup is not necessarily the currently active Setup in the
              configuration manager. That is only true of your process monitors the
              notifications from the configuration manager and updates the Setup when this
              is changed in/by the configuration manager. Use the `GlobalState.load_setup()`
              method to force loading the Setup from the configuration manager.

        Returns:
            The currently active Setup or None.
        """
        return setup_ctx.get()

    def load_setup(self) -> Setup | None:
        """
        Loads the currently active Setup from the Configuration manager. The current Setup is the Setup
        that is defined and loaded in the Configuration manager. When the configuration manager is not
        reachable, None will be returned, a warning will be logged, and the global state setup will be cleared.

        Since the GlobalState should reflect the configuration of the test, it can only load the current
        Setup from the configuration manager. If you need to work with different Setups, work with the `Setup`
        class and the Configuration Manager directly.

        Returns:
            The currently active Setup or None.
        """
        return load_setup()


GlobalState = _GlobalState()

if __name__ == "__main__":
    import rich

    rich.print(
        textwrap.dedent(
            f"""\
            GlobalState info:
              Setup loaded: {GlobalState.setup.get_id() if GlobalState.setup else "[orange3]no Setup loaded[/]"}
            """
        )
    )
