"""
This module provides configuration management for the Common-EGSE.

The configuration manager knows about the configuration of the system and the test setup. It's
main responsibility is to maintain the setup of the tests that are performed. It is the single
point access for all configuration information.

## The Configuration aka Setup

The Setup contains the identification of all the devices, mechanisms, controllers etc. that are
used for a particular test. For each of these items the Setup contains hardware and software
version, conversion and calibration information, location, components, specific settings,
defaults, in a word, all information that is needed to uniquely identify the components,
and to reproduce the test under the same circumstances. The details for the Setup are explained
in the `egse.setup` module.

## Prerequisites:

When the configuration manager (`cm_cs`) is started, no Setup is loaded. The configuration
manager will then be in a default Setup state without any devices configured. This is called the
_Zero_ Setup. The only keyword/attribute available from this Setup is `site_id`.

## Setup commands

The main purpose of the configuration manager is to maintain and manage Setups. These Setups
will reside in a GitHub repository for which the `cm_cs` has access to read and write Setups. The
`cm_cs` provides all configuration information on request with the following commands that
are available from the `ConfigurationManagerProxy`.

#### `list_setups()`

You can request a list of available Setups with the `list_setups` command. This function takes
keyword arguments which are the attributes of the Setup and compares the attribute with the
given value. An example should make this clear. A setup has a `site_id` and for the CSL site
also a `position`. You can access these value as follows:

    >>> from egse.state import GlobalState
    >>> setup = GlobalState.setup
    >>> setup.site_id
    'CSL'
    >>> setup.position
    2

When you now want a list of all Setups specific for CSL that were applicable for position 2,
the following command will return that list.
```
with ConfigurationManagerProxy() as cm:
    print(cm.list_setups(site_id="CSL", position=2))
```
When you need to know which of these setups has the PUNA Hexapod with id=172543, add this
attribute as a keyword.
```
with ConfigurationManagerProxy() as cm:
    print(cm.list_setups(site_id="CSL", position=2, gse__hexapod__ID=172543))
```
When multiple attributes are specified, they are checked using a logical AND, not a logical OR,
meaning they have to meet _every_ attribute passed in and not just one of them.

You probably also noticed that instead of using the normal dot-notation to reach the hexapod id,
e.g. `gse.hexapod.ID`, we use double underscores to replace the dots. The reason for that is
that you can not have dots in keyword argument names. When you put a dot, you will get a
`SyntaxError`.

#### `load_setup(setup_id: int)`

Load a new Setup into the configuration manager. This command can only be called outside the
scope of an observation and will not have any effect when an observation is currently running.
Since the `cm_cs` knowns what the site_id is, the Setup for the current site is loaded
automativally.

#### `get_setup()`

Returns the Setup that is currently loaded on the configuration manager.


## Observation (aka Test) Commands

The configuration manager needs to know when an observation is started. It will keep track and
inform clients of the running observation.

#### `start_observation()`

This command starts a new observation. This will assign an new unique observation
identifier (`obsid`) for the observation and inform the Storage Manager that a new test has been
started with that `obsid`. A new test can not start before the previous test has been finished.
Also, a new Setup can not be loaded when an observation is running.

#### `end_observation()`

This command ends the current observation and notifies the Storage Manager that the test
has been ended.

#### `get_obsid()`

Returns the observation identifier of the currently running observation.


## Convenience Functions

The package also defines a number of convenience functions that simplify the communication
with the configuration manager `cm_cs`.

#### `is_configuration_manager_active()`

A function that checks if the `cm_cs` is running and responding to commands. This function makes
a connection with the `cm_cs` and sends it a _Ping_ command. This is the recommended way to check
the availability of the configuration manager.

"""
from __future__ import annotations

import logging
import operator
import subprocess
import textwrap
import threading
from pathlib import Path
from typing import NamedTuple
from typing import Optional
from typing import Union

import git
import rich
from git import GitCommandError
from prometheus_client import Gauge

from egse.command import ClientServerCommand
from egse.command import stringify_function_call
from egse.config import find_file
from egse.config import find_files
from egse.control import ControlServer
from egse.control import is_control_server_active
from egse.decorators import dynamic_interface
from egse.decorators import static_vars
from egse.env import get_conf_data_location
from egse.env import get_conf_repo_location
from egse.env import get_project_name
from egse.env import get_site_id
from egse.exceptions import InternalError
from egse.obsid import ObservationIdentifier
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.response import Failure
from egse.response import Response
from egse.response import Success
from egse.settings import Settings
from egse.settings import SettingsError
from egse.setup import Setup
from egse.setup import load_last_setup_id
from egse.setup import save_last_setup_id
from egse.system import filter_by_attr
from egse.system import format_datetime
from egse.version import VERSION
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

LOGGER = logging.getLogger(__name__)

HERE = Path(__file__).parent

CTRL_SETTINGS = Settings.load("Configuration Manager Control Server")
SITE_ID = get_site_id()
COMMAND_SETTINGS = Settings.load(location=HERE, filename="confman.yaml")

CM_SETUP_ID = Gauge("CM_SETUP_ID", 'Setup ID')
CM_TEST_ID = Gauge("CM_TEST_ID", 'Test ID')


def _push_setup_to_repo(filename: str, commit_msg: str) -> Failure | Success:
    """
    Push the Setup file to the `cgse-conf` repository on GitHub.

    Args:
        filename: the basename of the new Setup file

    Returns:
        None.
    """

    repo_workdir = get_conf_repo_location()

    if repo_workdir is None:
        msg = textwrap.dedent(
            f"""\
            Couldn't determine the repository location for configuration data. 

            Check if the environment variable '{get_project_name()}_CONF_REPO_LOCATION' is set and valid 
            before starting the configuration manager.
            """
        )
        LOGGER.error(msg)
        return Failure(msg)

    repo = git.Repo(repo_workdir)

    if repo.is_dirty():
        LOGGER.warning(
            f"The cgse-conf repository is dirty. Check the git status at '{repo_workdir}'.")

    untracked = repo.untracked_files

    if len(untracked) != 1:
        msg = textwrap.dedent(
            f"""\
            The number of untracked files ({len(untracked)}) in the cgse-conf repository doesn't match 
            the expected. Check the git status at '{repo_workdir}' on the egse-server. 
            Only '{filename}' should be untracked.
            
            Untracked files: {untracked}
            """
        )
        LOGGER.error(msg)
        return Failure(msg)

    # match the filename to extract the full path to the file

    untracked = [x for x in untracked if filename in x]
    if (n := len(untracked)) != 1:
        msg = f"There should be one match for the filename, found {n}{'' if n == 0 else untracked}."
        LOGGER.error(msg)
        return Failure(msg)

    untracked = untracked[0]

    # The response is a list of tuples containing the path of the file added to the stages/index.

    try:
        response = repo.index.add(untracked)
        # assert response[0].path == untracked
    except FileNotFoundError:
        # if for some reason the untracked file can not be found, should not happen..
        LOGGER.warning(
            f"Untracked file {untracked} not found. Check the git status at {repo_workdir}."
        )

    # The response is a Commit object containing e.g. the commit message, the hash, the author, ...

    response = repo.index.commit(message=commit_msg)

    # The response is a list of FetchInfo instances
    # We need this `pull` command before we will push the changes because otherwise the push will
    # be rejected, see https://github.com/IvS-KULeuven/plato-common-egse/issues/2027. The problem
    # should not abort the submit command, but needs to be logged.

    try:
        response = repo.remote('upload').pull("main")
    except Exception as exc:
        LOGGER.error(exc, exc_info=True)

    # The response is a PushInfo object

    try:
        response = repo.remote('upload').push("main")
    except ValueError as exc:
        LOGGER.error(exc, exc_info=True)
        return Failure(f"Push of setup [{filename}] failed", exc)
    except GitCommandError as exc:
        LOGGER.error(exc, exc_info=True)
        return Failure(f"Push of setup [{filename}] failed", exc)

    return Success(f"Successfully pushed the setup to the repo {repo}")

# We have seen that especially when listing the setups, we have a performance problem.
# Therefore, we implement a cache for the Setup info that we use in different functions.
#
# The key is the Setup ID
# The value is the named tuple SetupInfo

_cached_setup_info = {}


class SetupInfo(NamedTuple):
    path: Path
    site_id: str
    cam_id: str
    description: str


def _populate_cached_setup_info():
    """
    Populates the internal cache of Setup information.

    Raises:
        InternalError when a Setup is loaded that doesn't have an ID associated.

    """
    global _cached_setup_info

    LOGGER.info("Populating cache with Setup Info.")

    location = get_conf_data_location()
    if location:
        data_conf_location = Path(location)
    else:
        raise ValueError(
            "Couldn't determine location of the configuration data with 'get_conf_data_location()'. "
            "Check if the environment is properly defined."
        )

    setup_info = {}

    for fn in find_files(pattern="SETUP*", root=data_conf_location):
        setup = Setup.from_yaml_file(fn)
        if id := setup.get_id():
            id = int(id)
            site_id = _get_site_id_for_setup(setup)
            cam_id = _get_sut_id_for_setup(setup)
            description = _get_description_for_setup(setup)
            setup_info[id] = SetupInfo(fn, site_id, cam_id, description)
        else:
            raise InternalError(f"Setup loaded without an ID, {fn=}")

    _cached_setup_info = dict(sorted(setup_info.items()))

    LOGGER.info("SetupInfo cache populated.")


def _add_setup_info_to_cache(setup: Setup):
    global _cached_setup_info

    if (_id := setup.get_id()) is None:
        raise InternalError(f"Setup loaded without an ID, {setup=!s}")

    if (_fn := setup.get_filename()) is None:
        raise InternalError(f"Setup with id={_id} has no filename associated.")

    _id = int(_id)
    _fn = Path(_fn)

    site_id = _get_site_id_for_setup(setup)
    cam_id = _get_sut_id_for_setup(setup)
    description = _get_description_for_setup(setup)

    _cached_setup_info[_id] = SetupInfo(_fn, site_id, cam_id, description)


def _print_cached_setup_info():
    global _cached_setup_info

    rich.print(_cached_setup_info)


def _get_cached_setup_info(setup_id: int) -> Optional[SetupInfo]:
    """Returns a setup info named tuple for the given setup id or None when no
    SetupInfo for the given setup_id is available.."""
    global _cached_setup_info

    return _cached_setup_info.get(setup_id)


def _reload_cached_setup_info():

    try:
        Setup.from_yaml_file.cache_clear()
    except AttributeError:
        LOGGER.warning("Setup.from_yaml_file() method is not decorated with an lru_cache.")

    _populate_cached_setup_info()


def is_configuration_manager_active(timeout: float = 0.5):
    """
    Checks whether the Configuration Manager is running.

    Args:
        timeout (float): Timeout when waiting for a reply [seconds, default=0.01]

    Returns:
        True if the Configuration Manager is running and replied with the expected answer.
    """

    endpoint = connect_address(
        CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.HOSTNAME, CTRL_SETTINGS.COMMANDING_PORT
    )

    return is_control_server_active(endpoint, timeout)


def _construct_filename(site_id: str, setup_id: int, creation_time: str = None):
    """Construct a filename for a Setup.

    FIXME: describe the restrictions on file naming and how they are parsed etc.

    Args:
        site_id (str): the site identifier
        setup_id (int): the setup identifier
        creation_time (str): the date-time shall be formatted as `YYMMDD_HHMMSS`
    """

    if creation_time:
        filename = f"SETUP_{site_id}_{setup_id:05d}_{creation_time}.yaml"
    else:
        filename = f"SETUP_{site_id}_{setup_id:05d}_{format_datetime(fmt='%y%m%d_%H%M%S')}.yaml"

    return filename


def _get_description_for_setup(setup: Setup, setup_id: int = None) -> str:
    setup_id = setup_id or int(setup.get_id())
    try:
        description = setup.history.get(setup_id)
    except AttributeError:
        description = None
    return description or f"no description found for Setup {setup_id}"


def _get_sut_id_for_setup(setup: Setup) -> str:

    try:
        if "id" in setup.sut:
            sut_id = setup.sut.id
        elif "ID" in setup.sut:
            sut_id = setup.sut.ID
        else:
            sut_id = None
    except AttributeError:
        sut_id = None

    return sut_id or "no sut_id"


def _get_site_id_for_setup(setup: Setup) -> str:

    try:
        site_id = setup.site_id if "site_id" in setup else None
    except AttributeError:
        site_id = None

    return site_id or "no site_id"


@static_vars(test_id=0)
def create_obsid(last_obsid: str, site_id: str, setup_id: int):
    # This is method is currently just a prove of concept, the real thing should
    # read the LID, SID from the current Setup and then generate or keep track
    # of a TEST ID.

    # How do we guarantee a unique OBSID? OBSIDs need to be made persistent at least for the Site.
    # That way we can, when a new ObservationIdentifier is generated, check if it's indeed unique.

    if last_obsid:
        create_obsid.test_id = int(last_obsid.split(maxsplit=1)[0])

    create_obsid.test_id += 1

    # We need access to the setup, because we need the LabID, the SetupID
    # How do we define the configuration ID and Test ID?

    return ObservationIdentifier(site_id, setup_id, create_obsid.test_id)


class ConfigurationManagerInterface:
    """
    This interface is for sending commands to the configuration manager to e.g. start and stop
    an observation/test, or get information about the Setups.

    The interface should be implemented by the `ConfigurationManagerController` and the
    `ConfigurationManagerProxy` (and possibly a `ConfigurationManagerSimulator` should we
    need that e.g. for testing purposes).
    """

    @dynamic_interface
    def start_observation(self, function_info: dict) -> Response:
        """Starts a new observation or test. The following actions will be taken:

        * create an observation identifier, aka `obsid`
        * notify the Storage Control Server that a new observation is started
        * return the generated `obsid`

        Args:
            function_info: dictionary with information about the function called
        Returns:
            `Success` (with `obsid` as `return_code`) or `Failure` when already in an observation
            or Storage returned Failure.
        """
        raise NotImplementedError

    @dynamic_interface
    def end_observation(self) -> Response:
        """Ends the current observation and notifies the Storage Control Server.

        Returns:
            `Success` when the observation could be closed properly and the Storage CS was notified
            or `Failure` otherwise.
        """
        raise NotImplementedError

    @dynamic_interface
    def get_obsid(self) -> Success:
        """Returns the current observation identifier. When no observation is running, `None` is
        returned as the `return_code` in `Success`.

        Returns:
            Always returns `Success` with current observation identifier, i.e. `obsid`.
        """
        raise NotImplementedError

    @dynamic_interface
    def load_setup(self, setup_id: int = None) -> Union[Setup, Failure]:
        raise NotImplementedError

    @dynamic_interface
    def get_setup(self, setup_id: int = None):
        raise NotImplementedError

    @dynamic_interface
    def reload_setups(self):
        raise NotImplementedError

    @dynamic_interface
    def list_setups(self, **attr):
        raise NotImplementedError

    @dynamic_interface
    def submit_setup(self, setup: Setup, description: str, replace: bool = True) -> Setup | None:
        raise NotImplementedError

    @dynamic_interface
    def get_setup_for_obsid(self, obsid):
        raise NotImplementedError


class ConfigurationManagerController(ConfigurationManagerInterface):
    """Handles the commands that are sent to the configuration manager.

    .. note::
        The docstrings for each of the commands are in the `ConfigurationManagerInterface`.
    """

    def __init__(self):

        # Import these modules here as to optimize the import of classes and functions in other parts of the CGSE.
        # The CongifurationManagerController is only used by the CM CS and these Storage imports are only used in
        # this class and take too much loading time...

        from egse.storage import StorageProxy
        from egse.storage import is_storage_manager_active
        from egse.storage.persistence import TYPES

        self._obsid: ObservationIdentifier | None = None
        self._setup_id: int | None = None
        self._sut_name: str | None = None

        if is_storage_manager_active():
            self._storage = StorageProxy()
            response = self._storage.register(
                {
                    "origin": "obsid",
                    "persistence_class": TYPES['TXT'],
                    "prep": {"mode": "a", "ending": "\n"},
                    "persistence_count": True,
                    "filename": "obsid-table.txt",
                }
            )
            LOGGER.info(response)
        else:
            self._storage = None
            LOGGER.error("No Storage Manager available !!!!")

        # Find the location for the configuration data

        location = get_conf_data_location()
        if location:
            self._data_conf_location = Path(location)
        else:
            raise ValueError(
                "The location for the configuration data is not defined. Please check your environment."
            )

        # Populate the cache with information from the available Setups. This will also load each
        # Setup and cache them with the lru_cache decorator. Since this takes about 5s for 100
        # Setups, we run this function in a daemon thread in order not to block the cm_cs from
        # reacting to command requests.

        cache_thread = threading.Thread(target=_populate_cached_setup_info)
        cache_thread.daemon = True
        cache_thread.start()

        # Load the last used Setup

        setup_id = load_last_setup_id()
        self.load_setup(setup_id)

    def quit(self):
        if self._storage:
            self._storage.disconnect_cs()

    @property
    def data_location(self) -> Path:
        """Return the location of the configuration data, i.e. the Setup YAML files."""
        return self._data_conf_location

    def start_observation(self, function_info: dict) -> Response:
        if self._obsid is not None:
            return Failure(
                "An new observation can not be started before the previous observation is "
                "finished. You will need to first send an end_observation request to the "
                "configuration manager."
            )

        last_obsid = None

        if self._storage:
            last_obsid = self._storage.read({"origin": "obsid", "select": "last_line"})
            last_obsid = last_obsid.return_code if isinstance(last_obsid, Success) else None

        self._obsid = create_obsid(last_obsid, SITE_ID, self._setup_id)

        if self._storage:
            response = self._storage.start_observation(self._obsid, self._sut_name)
        else:
            return Failure(
                "Couldn't send start observation to Storage Manager, no Storage Manager available."
            )

        if not response.successful:
            self._obsid = None
            return Failure(
                "Sending a start_observation to the Storage Control Server failed",
                response,
            )

        description = function_info.pop("description", "")
        cmd = stringify_function_call(function_info).replace('\n', ' ')

        if description:
            cmd += f" [{description}]"

        response = self._storage.save(
            {
                "origin": "obsid",
                "data": f"{self._obsid.test_id:05d} "
                f"{self._obsid.lab_id} "
                f"{self._obsid.setup_id:05d} "
                f"{format_datetime()} "
                f"{cmd}",
            }
        )

        if isinstance(response, Failure):
            LOGGER.warning(
                f"There was a Failure when saving to the obsid-table: "
                f"{response}")
        else:
            LOGGER.info(f"Successfully created an observation with obsid={self._obsid}.")

        return Success("Returning the OBSID", self._obsid)

    def end_observation(self) -> Response:
        if not self._obsid:
            return Failure(
                "Received end_observation command while not currently in an observation context."
            )

        if self._storage:
            response = self._storage.end_observation(self._obsid)
        else:
            return Failure(
                "Couldn't send end observation to Storage Manager, no Storage Manager available."
            )

        if not response.successful:
            return Failure(
                "Sending an end_observation to the Storage Control Server failed.",
                response,
            )

        LOGGER.info(f"Successfully ended observation with obsid={self._obsid}.")

        self._obsid = None

        return Success("Successfully ended the observation.")

    def get_obsid(self) -> Success:
        if self._obsid:
            msg = "Returning the current OBSID."
        else:
            msg = "No observation running. Use start_observation() to start an observation."
        return Success(msg, self._obsid)

    def load_setup(self, setup_id: int = None) -> Union[Setup, Failure]:
        """Load the Setup with the given setup_id.

        Args:
            setup_id (int): the identifier for the requested Setup.
        Returns:
            The requested Setup.
        """
        # The current implementation is file based. The files have a strict naming convention and
        # are located in the `data/conf` directory.
        #
        # 1. Find the Setup for the given setup_id and the Site (is this read from the Settings
        #    file, or set by some GUI or process?
        # 2. Load that Setup from its file at the default location
        # 3. Return an acknowledgement that the Setup is loaded on the CM_CS or not

        if setup_id is None:
            return Failure(
                f"No Setup ID was given, cannot load a Setup into the configuration manager. "
                f"If you wanted to get the current Setup from the configuration manager, use the "
                f"get_setup() method instead."
            )

        if self._obsid:
            return Failure(
                f"A new Setup can not be loaded when an observation is running. "
                f"The current obsid is {self._obsid}. Use `end_observation()` before "
                f"loading a new Setup."
            )

        setup_files = list(
            find_files(
                pattern=f"SETUP_{SITE_ID}_{setup_id:05d}_*.yaml", root=self._data_conf_location
            )
        )

        if len(setup_files) != 1:
            LOGGER.error(
                msg := f"Expected to find just one Setup YAML file, found {len(setup_files)}. "
                       f"[{SITE_ID = }, {setup_id = }, data_conf_location={self._data_conf_location}]"
            )
            return Failure("Loading Setup", InternalError(msg))

        setup_file = setup_files[0]

        try:
            self._setup = Setup.from_yaml_file(setup_file)
            self._setup_id = setup_id
            self._sut_name = _get_sut_id_for_setup(self._setup)
            LOGGER.info(f"New Setup loaded from {setup_file}")
            save_last_setup_id(self._setup_id)
            return self._setup
        except SettingsError as exc:
            return Failure(f"The Setup file can not be loaded from {setup_file}.", exc)
        except AttributeError as exc:
            msg = f"The Setup [id={setup_id}] has no camera.ID entry."
            LOGGER.error(msg, exc_info=True)
            # FIXME: if we come here, shouldn't we load the zero Setup so that the problem of the
            #        missing camera ID gets solved?
            return Failure(msg)

    def get_setup(self, setup_id: int = None) -> Union[Setup, Failure]:
        """
        Returns the Setup for the given setup_id. If no setup_id argument was provided,
        the current Setup from the configuration manager will be returned.

        This is a -read-only function.
        Under no circumstance will the Setup of the configuration manager be changed.

        Args:
            setup_id (int): the identifier for the requested Setup.
        Returns:
            The requested Setup.
        """

        if setup_id:
            # If a Setup ID is given, just load and return the Setup for that ID
            # The Setup is NOT added to the Configuration Manager as the current Setup.

            setup_files = list(
                find_files(
                    pattern=f"SETUP_{SITE_ID}_{setup_id:05d}_*.yaml", root=self._data_conf_location
                )
            )

            if len(setup_files) != 1:
                LOGGER.error(
                    msg := f"Expected to find just one Setup YAML file, found {len(setup_files)}."
                )
                return Failure("Expected only one Setup.", InternalError(msg))

            setup_file = setup_files[0]

            try:
                return Setup.from_yaml_file(setup_file)
            except SettingsError as exc:
                return Failure(f"The Setup file can not be loaded from {setup_file}.", exc)

        else:
            # No Setup ID was given, so we return the current Setup loaded in the Configuration Manager

            if self._setup:
                return self._setup
            else:
                return Failure("No Setup was loaded on the Configuration Manager.")

    def get_setup_id(self) -> int:
        """Returns the Setup identifier for the currently loaded Setup.

        Returns:
            The `setup_id` of the Setup loaded by the `cm_cs`, or None.
        """

        return self._setup_id

    def get_site_id(self) -> str:
        """Returns the Site identifier that is used by the configuration manager.

        Returns:
            The Site identifier as a string.
        """

        return SITE_ID

    def reload_setups(self):
        """
        Clears the cache and Reloads the available Setups.

        This function does not affect the currently loaded Setup.
        """
        _reload_cached_setup_info()

    def list_setups(self, **attr):
        """
        Returns a sorted list of all the available Setups for the current site. The list contains
        tuples with the following content: setup_id, site_id, description, cam_id.

        Args:
            **attr: see egse.system.filter_by_attr()

        Returns:
            A list with information on the available Setups.
        """
        # The current implementation is file based. The files have a strict naming convention and
        # are located in the `data/conf` directory.
        #
        # 1. Get a list of the Setup files from the default location, i.e. data/conf
        # 2. Prepare a list of tuples with that information ordered by Setup ID
        # 3. Return that list

        setup_list = []

        setups = [Setup.from_yaml_file(info.path) for info in _cached_setup_info.values()]

        setups = filter_by_attr(setups, **attr)

        for setup in setups:
            _, setup_site, setup_id, _ = str(setup._filename).split("_", maxsplit=3)
            description = _get_description_for_setup(setup, int(setup_id))
            cam_id = _get_sut_id_for_setup(setup)
            setup_list.append((setup_id, setup_site, description, cam_id))

        # Sort by site, then by id

        return sorted(setup_list, key=operator.itemgetter(1, 0), reverse=False)

    def get_setup_for_obsid(self, obsid):
        obsid = f"{obsid:05d}" if isinstance(obsid, int) else obsid
        rc = self._storage.read({"origin": "obsid", "select": ("startswith", obsid)})
        if rc.successful:
            # FIXME: this should be a function that can also be used in load_setup(),
            #  because they do basically the same thing
            try:
                setup_id = int(rc.return_code[-1].split(maxsplit=3)[2])
                setup_file = find_file(
                    name=f"SETUP_{SITE_ID}_{setup_id:05d}_*.yaml", root=self._data_conf_location
                )
                setup = Setup.from_yaml_file(setup_file)
            except (IndexError, SettingsError):
                setup = None

        return setup

    def submit_setup(self, setup: Setup, description: str, replace: bool = True):

        # 1. Determine the Site for this Setup, or should this be the Site that is known by the
        #    CM_CS?
        # 2. Find the correct (next) number for the Setup for the given Site
        # 3. Do I want to make some comparison?
        #    Do we need to keep a record from which this Setup is derived?

        # FIXME: define and handle exceptional conditions, like IOError

        if self._obsid is not None:
            return Failure(
                "An new Setup can not be submitted when an observation is running. You will need "
                "to first send an end_observation request to the configuration manager."
            )

        site = setup.site_id

        setup_id = self.get_next_setup_id_for_site(site)

        filename = _construct_filename(SITE_ID, setup_id)

        if not hasattr(setup, "history"):
            setup.history = {}

        setup.history.update({f"{setup_id}": description})
        setup.set_private_attribute("_setup_id", setup_id)
        setup.to_yaml_file(self._data_conf_location / filename)

        # No repository is defined. This should not break, but a warning is in place.
        # The warnings are issued by the get_conf_repo_location() function.

        if get_conf_repo_location() is None:
            return

        try:
            rc = _push_setup_to_repo(filename, description)
            if isinstance(rc, Failure):
                return rc
            _add_setup_info_to_cache(setup)
        except (Exception, ) as exc:
            msg = "Submit_setup could not complete it's task to send the new Setup to the repo."
            LOGGER.error(msg, exc_info=True)
            return Failure("Submit_setup could not complete it's task to send the new Setup to the repo.", exc)
        else:
            LOGGER.info(f"Successfully pushed Setup {setup_id} to the repository.")

        if replace:
            self._setup = setup
            self._setup_id = setup_id
            save_last_setup_id(setup_id)

        return setup

    def get_next_setup_id_for_site(self, site: str) -> int:
        """
        Return the next available Setup ID for the given Site.

        Args:
            site (str): site identification, e.g. CSL, SRON, ...
        """
        site = site or SITE_ID
        files = sorted(find_files(pattern=f"SETUP_{site}_*.yaml", root=self._data_conf_location))
        last_file = files[-1]
        setup_id = last_file.name.split("_")[2]

        return int(setup_id) + 1


class ConfigurationManagerCommand(ClientServerCommand):
    pass


class ConfigurationManagerProxy(Proxy, ConfigurationManagerInterface):
    """
    The Configuration Manager Proxy class is used to connect to the Configuration Manager
    Control Server and send commands and requests for the configuration manager.
    """

    def __init__(
        self,
        protocol=CTRL_SETTINGS.PROTOCOL,
        hostname=CTRL_SETTINGS.HOSTNAME,
        port=CTRL_SETTINGS.COMMANDING_PORT,
    ):
        """
        Args:
            protocol: the transport protocol [default is taken from settings file]
            hostname: location of the control server (IP address) [default is taken
                from settings file]
            port: TCP port on which the control server is listening for commands
                [default is taken from settings file]
        """
        super().__init__(connect_address(protocol, hostname, port))


class ConfigurationManagerProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

        self.controller = ConfigurationManagerController()

        self.load_commands(
            COMMAND_SETTINGS.Commands,
            ConfigurationManagerCommand,
            ConfigurationManagerController,
        )

        self.build_device_method_lookup_table(self.controller)

        self.cgse_version = VERSION

        try:
            self.git_version = subprocess.check_output(
                ["git", "describe", "--tags", "--long"], stderr=subprocess.STDOUT)
            self.git_version = self.git_version.strip().decode("ascii")
        except subprocess.CalledProcessError as exc:
            LOGGER.debug(
                f"A git error occurred for the `git describe` command: {exc}", stack_info=True)
            self.git_version = "no git-version determined"

    def get_bind_address(self):
        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_status(self) -> dict:
        status = super().get_status()

        status.update({"obsid": self.controller.get_obsid().return_code})
        status.update({"setup": self.controller.get_setup()})

        return status

    def get_housekeeping(self) -> dict:
        obsid = self.controller.get_obsid().return_code
        test_id = obsid.test_id if obsid else float('nan')
        setup_id = self.controller.get_setup_id()
        site_id = self.controller.get_site_id()

        hk = {
            "timestamp": format_datetime(),
            "CM_SITE_ID": site_id,
            "CM_SETUP_ID": setup_id,
            "CM_TEST_ID": test_id,
            "CM_OBSID": obsid,
            "CM_CGSE_VERSION": self.cgse_version,
            "CM_GIT_VERSION": self.git_version,
        }

        # Update the metrics

        CM_SETUP_ID.set(float(setup_id))
        CM_TEST_ID.set(float(test_id))

        return hk

    def quit(self):
        self.controller.quit()


# The following functions are defined here to allow them to be used in the list_setups() method
# and be pickled and passed over ZeroMQ.


def is_in(a, b):
    """Returns result of `a in b`."""
    return a in b


def is_not_in(a, b):
    """Returns result of `a not in b`."""
    return a not in b


def get_status():

    if is_configuration_manager_active():
        with ConfigurationManagerProxy() as cm:
            obsid = cm.get_obsid()
            obsid = obsid.return_code
            setup = cm.get_setup()
            try:
                site_id = f"Site ID: {setup.site_id}"
            except AttributeError:
                site_id = 'Site ID: [red]UNKNOWN[/]'

            if obsid:
                obsid = f"Running observation: {obsid}"
            else:
                obsid = "No observation running"

            try:
                if setup.has_private_attribute("_setup_id"):
                    setup_id = setup.get_private_attribute("_setup_id")
                    setup_id = f"Setup loaded: {setup_id}"
                else:
                    setup_id = '[red]No Setup loaded[/]'
            except Exception as exc:
                setup_id = "An Exception was caught: {exc}"

            return textwrap.dedent(
                f"""\
                Configuration manager:
                    Status: [green]active[/]
                    {site_id}
                    {obsid}
                    {setup_id}
                    Hostname: {cm.get_ip_address()}
                    Monitoring port: {cm.get_monitoring_port()}
                    Commanding port: {cm.get_commanding_port()}
                    Service port: {cm.get_service_port()}
                """
            )
    else:
        return 'Configuration Manager Status: [red]not active'
