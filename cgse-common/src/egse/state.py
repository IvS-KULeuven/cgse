import abc
import logging
import textwrap
from pathlib import Path
from typing import Optional

from egse.decorators import borg
from egse.decorators import deprecate
from egse.setup import Setup

LOGGER = logging.getLogger(__name__)


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


@borg
class _GlobalState:
    """
    This class implements global state that is shared between instances of this class.
    """

    # TODO (rik): turn command sequence into a class and move add_, clear_ and get_ to that class

    def __init__(self):
        self._dry_run = False
        self._command_sequence = []
        self._setup: Optional[Setup] = None

    def __call__(self, *args, **kwargs):
        return self

    @property
    def dry_run(self):
        return self._dry_run

    @dry_run.setter
    def dry_run(self, flag: bool):
        self._dry_run = flag

    def add_command(self, cmd):
        self._command_sequence.append(cmd)

    def get_command_sequence(self):
        return self._command_sequence

    def clear_command_sequence(self):
        self._command_sequence.clear()

    @property
    def setup(self) -> Optional[Setup]:
        """
        Returns the currently active Setup from the configuration manager. Please note that each call
        to this property sends a request to the configuration manager to return its current Setup. If
        you are accessing information from the Setup in a loop or function that is called often, save
        the Setup into a local variable before proceeding.

        Returns:
            The currently active Setup or None (when the configuration manager is not reachable).
        """
        return self.load_setup()

    # This function should be the standard function to reload a setup from the configuration manager
    # Since we have no proper CM yet, the function loads from the default setup.yaml file.
    # But what happens then in other parts of the system, where e.g. the PM has also the 'rights'
    # to call load_setup() on the CM_CS?

    def load_setup(self) -> Optional[Setup]:
        """
        Loads the currently active  Setup from the Configuration manager. The current Setup is the Setup
        that is defined and loaded in the Configuration manager. When the configuration manager is not
        reachable, None will be returned and a warning will be logged.

        Since the GlobalState should reflect the configuration of the test, it can only load the current
        Setup from the configuration manager. If you need to work with different Setups, work with the `Setup`
        class and the Configuration Manager directly.

        Returns:
            The currently active Setup or None.
        """
        from egse.confman import ConfigurationManagerProxy
        from egse.confman import is_configuration_manager_active

        if is_configuration_manager_active():
            with ConfigurationManagerProxy() as cm_proxy:
                self._setup = cm_proxy.get_setup()
        else:
            LOGGER.warning(textwrap.dedent(
                f"""\
                    Could not reach the Configuration Manager to request the Setup, returning the current local Setup.
                    
                    Check if the Configuration Manager is running and why it can not be consulted. When it's 
                    back on-line, do a 'load_setup()'. 
                """
            ))

        return self._setup

    # FIXME:
    #  These two 'private' methods are still called in plato-test-scripts, so until that is fixed,
    #  leave the methods here

    @deprecate(reason="this is a private function", alternative="reload_setup()")
    def _reload_setup(self):
        self._setup = Setup.from_yaml_file()
        return self._setup

    @deprecate(reason="this is a private function", alternative="reload_setup_from()")
    def _reload_setup_from(self, filename: Path):
        """Used by the unit tests to load a predefined setup."""
        self._setup = Setup.from_yaml_file(filename=filename)
        return self.setup


GlobalState = _GlobalState()

__all__ = [
    "GlobalState",
]

if __name__ == "__main__":

    from rich import print

    print(textwrap.dedent(
        f"""\
            GlobalState info:
              Setup loaded: {GlobalState.setup.get_id()}
              Dry run: {'ON' if GlobalState.dry_run else 'OFF'}
              Command Sequence: {GlobalState.get_command_sequence()} \
        """)
    )
