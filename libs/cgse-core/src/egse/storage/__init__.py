"""
This module provides storage functionality for the Common-EGSE.

![Storage Manager](../../../img/storage-design.png)

### Introduction

All control servers and other components that need to save data through the storage manager
need to register to the storage manager first. That can be done by creating a `StorageProxy`
and sending a register message for the component. The name that is registered is also used by
all `save` messages to identify the component and dispatch the correct persistence function.

All control servers (that inherit from the ControlServer class) will automatically register to
the Storage Manager when the control server (CS) starts. When the CS quits normally (by the
`quit_server()` command of the Service proxy) the control server will automatically be
unregistered from the Storage manager.

By default, when the Storage is active, it will save all the information that it gets for those
components that have registered to the Storage manager.

```python
storage_proxy = StorageProxy()
...
storage_proxy.register({'origin': reg_name,
                        'persistence_class': TYPES['CSV'],
                        'prep': {'column_names': [], 'mode': 'w'}})
...

storage_proxy.save({'origin': reg_name, 'data': data})
...
storage_proxy.unregister({'origin': reg_name})
```

### Commands

The Storage component shall understand the following commands:

* registration of a component

    * `storage_proxy.register({'origin': str, 'persistence_class'; <class>, 'prep': dict})`
    * `storage_proxy.unregister({'origin': str})`

* accept the following commands from the configuration manager

    * `storage_proxy.start_observation(obsid: str)`
    * `storage_proxy.end_observation(obsid: str)`

* accept housekeeping and data packets from the DPU simulator housekeeping and accept
    housekeeping and status data from any control server

    * `storage_proxy.save({'origin': name, 'data': data})`


When an observation is started, the Storage Manager will 'fork' the data stream and save the
control server information in a separate set of files. The filenames will carry the `obsid`
(see below).

### What data is saved?

* Housekeeping data from other control servers, e.g. device CS or the configuration manager
* Status data from other control servers
* SpaceWire packets from the N-FEE and the F-FEE, this includes housekeeping and CCD data
* Image data from the camera, i.e. processed Spacewire data packets

### How is data saved?

* Different data types are stored in specific formats according to the PersistenceLayer
  that was chosen
* The following file formats are supported:
    * CSV - for tabular data, typically housekeeping and status information
    * TXT - for logging information
    * FITS - for image data
    * HDF5 - for SpaceWire data and housekeeping packets

### How are the files named?

We have two sets of files:

1. files that contain only the data that was collected for an observation, i.e.
   between the calls to `start_observation` and `end_observation`. These files are located
   in the `obs` sub-folder of the main data store location. The filename is constructed from
   the test id, the site id and the setup id, followed by the data source identifier and a
   timestamp. An example from the PUNA Hexapod housekeeping file:
   `00031_CSL_00008_PUNA_20200701_210711.csv`.

2. files that contain all the housekeeping for each of the data sources regardless of an
   observation is running or not. All data that is collected during a test day will be stored in
   these files. Outside of an observation context there will be no CCD image data collected.
   These files are located in the `daily` sub-folder of the main data store location. The filename
   is constructed from the date, the site id and the data source identifier. An example for the
   same PUNA Hexapod file: `20200701_CSL_PUNA.csv`.

The timestamp that is used is the time of file creation.

"""
from __future__ import annotations

import abc
import datetime
import logging
import os
import shutil
import textwrap
from pathlib import Path
from pathlib import PurePath
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union

from egse.bits import humanize_bytes
from egse.command import ClientServerCommand
from egse.config import find_files
from egse.control import ControlServer
from egse.env import get_site_id
from egse.response import Failure
from egse.response import Response
from egse.response import Success
from egse.control import is_control_server_active
from egse.decorators import dynamic_interface
from egse.env import get_data_storage_location
from egse.exceptions import Error
from egse.obsid import ObservationIdentifier
from egse.obsid import TEST_LAB
from egse.persistence import PersistenceLayer
from egse.protocol import CommandProtocol
from egse.proxy import Proxy
from egse.proxy import REQUEST_TIMEOUT
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address
from egse.zmq_ser import connect_address

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent

CTRL_SETTINGS = Settings.load("Storage Control Server")
SITE_ID = get_site_id()
DEVICE_SETTINGS = COMMAND_SETTINGS = Settings.load(location=HERE, filename="storage.yaml")

__all__ = [
    "is_storage_manager_active",
    "get_status",
    "PersistenceLayer",
    "register_to_storage_manager",
    "unregister_from_storage_manager",
]


def is_storage_manager_active(timeout: float = 0.5):
    """Check if the Storage Manager is running.

    Returns:
        True if the Storage Manager is running and replied with the expected answer.
    """

    endpoint = connect_address(
        CTRL_SETTINGS.PROTOCOL, CTRL_SETTINGS.HOSTNAME, CTRL_SETTINGS.COMMANDING_PORT
    )

    return is_control_server_active(endpoint, timeout)


def register_to_storage_manager(origin: str, persistence_class: PersistenceLayer, prep: Dict):
    """
    Register the component to the Storage manager.

    For information on what should go into the `prep` keyword argument, please check the proper
    persistence class.

    Args:
        origin (str): the name of the component, by which it will be registered
        persistence_class: a concrete class that will be used to store the  data
        prep (dict): preparation meta data for the persistence class

    Raises:
        ConnectionError: when the storage manager can not be reached.
    """

    try:
        with StorageProxy() as proxy:
            rc = proxy.register(
                {
                    "origin": origin,
                    "persistence_class": persistence_class,
                    "prep": prep,
                }
            )
            if not rc.successful:
                logger.warning(f"Couldn't register to the Storage manager: {rc}")
            else:
                logger.info(rc)
    except ConnectionError as exc:
        logger.warning(f"Couldn't connect to the Storage manager for registration: {exc}")
        raise


def unregister_from_storage_manager(origin: str):
    """
    Unregister the component from the Storage manager.

    Args:
        origin (str): the name of the component, by which it will be registered

    Raises:
        ConnectionError: when the storage manager can not be reached.
    """

    try:
        with StorageProxy() as proxy:
            rc = proxy.unregister({"origin": origin})
            if not rc.successful:
                logger.warning(f"Couldn't unregister from the Storage manager: {rc}")
            else:
                logger.info(rc)
    except ConnectionError as exc:
        logger.warning(f"Couldn't connect to the Storage manager for de-registration: {exc}")
        raise


def store_housekeeping_information(origin: str, data: dict):
    """
    Send housekeeping information to the Storage manager. The housekeeping data is usually collected by the device
    control server and is a dictionary with key:value = parameters names and their values. The data dictionary shall
    at least contain a timestamp in the format generated by `format_datetime()`.

    Raises:
        ConnectionError: when the Storage manager can not be reached.
    """

    # logger.debug("Sending housekeeping data to storage manager.")

    try:
        with StorageProxy() as proxy:
            rc = proxy.save({"origin": origin, "data": data})
            if not rc.successful:
                logger.warning(f"Couldn't save data to the Storage manager for {origin=}, cause: {rc}")
    except ConnectionError as exc:
        logger.warning(f"Couldn't connect to the Storage manager to store housekeeping: {exc}")
        raise


def cycle_daily_files():
    """
    Create a new daily file for each registered item when no such file exists.
    """
    with StorageProxy() as storage:
        storage.cycle_daily_files()


class AlreadyRegisteredError(Error):
    """This error indicates that an item is already registered and cannot be registered again."""


class Registry:
    """
    A registry for registration of components in the system that need to save data through
    the Storage Manager.
    """

    def __init__(self):
        self._register = dict()

    def __contains__(self, name: str):
        """Returns True if an item with 'name' has been registered."""
        if isinstance(name, str):
            return name in self._register.keys()

        raise ValueError(
            f"You can only check if something is contained in the Registry "
            f"by a key of type string, item is of type '{type(name)}'."
        )

    def __len__(self):
        """Returns the number of registrations."""
        return len(self._register)

    def __iter__(self):
        return iter(self._register.keys())

    def get(self, name: str):
        """Returns the registered item for the given name (identifier)."""
        return self._register.get(name)

    def register(self, name: str, item):
        """Register the item by the given name in the register.

        Args:
            name (str): the key to identify this registration, usually the name of
                the control server or the class that registers
            item: an object that contains information about what information needs to be saved
                and how
        """
        if not isinstance(name, str):
            raise ValueError("The name of the item to register must be a string.")
        if name in self:
            raise AlreadyRegisteredError(
                f"An item with name '{name}' is already registered, please unregister first."
            )
        self._register[name] = item

    def unregister(self, name: str):
        """Unregister the item with the given name from the register.

        Args:
            name (str): the key by which the registration was done.
        """
        if not isinstance(name, str):
            raise ValueError("The name of the item to unregister must be a string.")
        if name not in self:
            raise KeyError(f"There is no item with name '{name}' in this Register.")
        del self._register[name]


class StoragePacket(metaclass=abc.ABCMeta):
    """Base packet for all data send to Storage."""

    def __init__(self, origin=None, data=None, metadata=None):
        self._timestamp = datetime.datetime.now(tz=datetime.timezone.utc)
        self._origin = origin
        self._data = data
        self._metadata = metadata

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def origin(self):
        return self._origin

    @property
    def data(self):
        return self._data

    @property
    def metadata(self):
        return self._metadata


class StorageInterface:
    """
    This interface is for control servers to register to the Storage Manager and for the
    configuration manager to start and stop an observation/test.

    The interface should be implemented by the StorageController and the StorageProxy (and
    possibly a StorageSimulator should we need that).
    """

    @dynamic_interface
    def save(self, item: dict) -> Response:
        """Saves the data part from the item.
        Args:
            item (dict): a dictionary that identifies the origin and the data to be stored.
        """
        raise NotImplementedError

    @dynamic_interface
    def read(self, item: dict) -> Response:
        """Reads data from storage defined by the `origin` in item.
        Args:
            item (dict): a dictionary that identifies the origin and an optional filter.
        """
        raise NotImplementedError

    @dynamic_interface
    def register(self, item: dict, use_counter: bool = False) -> Response:
        """Registers the item to the storage manager.

        The item shall have the following keys:

        * origin (str): the name of the item, by which it will be registered
        * persistence_class (class):

        Args:
            item (dict): a dictionary that identifies the component to be registered

        Returns:
            Success: when the item could be registered successfully
            Failure: when the registration fails, `Failure.cause` provides cause exception
        """
        raise NotImplementedError

    @dynamic_interface
    def unregister(self, item: dict) -> Response:
        """Unregisters the item from the storage manager.

        Args:
            item (dict): a dictionary that identifies the component to be registered

        Returns:
            Success: when the item could be unregistered successfully
            Failure: when the de-registration fails, `Failure.cause` provides cause exception
        """
        raise NotImplementedError

    @dynamic_interface
    def get_registry_names(self):
        """Returns the names of the registered components.

        Returns:
            a list of names/identifiers for the registered components.
        """
        raise NotImplementedError

    @dynamic_interface
    def start_observation(self, obsid: ObservationIdentifier, camera_name: str = None) -> Response:
        """ "Start an observation for the given obsid.

        When a new obsevation is started the following actions will be taken:

        * Housekeeping and telemetry from registered components (mainly control servers)
          will be forked into a newly created file for that component.
        * Camera data will be saved as follows:
            * SpaceWire packets will go into an HDF5 file for this observation
            * CCD data will be assembled into image data and saved in FITS format

        Args:
            camera_name: the name of the camera or None
            obsid: a unique observation identifier

        Returns:
            Success: when a new observation with the given obsid could be started properly.
            Failure: when the previous observation was not finished yet (no end_observation was
                send), or when a failure happened during the preparations for a new observation.
        """
        raise NotImplementedError

    @dynamic_interface
    def end_observation(self, obsid: ObservationIdentifier) -> Response:
        """Ends the currently running observation.

        When a running observation is ended, the following actions will be taken:

        * All files of registered components will be closed.
        * Housekeeping and telemetry will continue to be saved to the global repository

        Args:
            obsid: the observation identifier of the currently running observation

        Returns:
            Success: when the current observation could be ended successfully.
            Failure: when the given obsid doesn't match the current observation.

        """
        raise NotImplementedError

    @dynamic_interface
    def get_obsid(self):
        """Return the observation identifier."""
        pass

    @dynamic_interface
    def cycle_daily_files(self):
        pass

    @dynamic_interface
    def get_storage_location(self):
        pass

    @dynamic_interface
    def get_filenames(self, item: dict) -> List[Path]:
        """Return the filename(s) associated with this registered item."""
        pass

    @dynamic_interface
    def new_registration(self, item: dict, use_counter=False):
        """
        Create a new data file for the given item. If the item was previously registered, close that
        registration and open a new registration. The use_counter parameter determines if an
        incremented counter is used to construct a unique filename.

        Args:
            - item: Dictionary that identifies the component to be registered.
            - use_counter: Indicates whether or not a counter should be used in the filename.
        """

        pass

    @dynamic_interface
    def get_disk_usage(self):
        """ Return the total, used, and free disk space [bytes].

        Returns:
            - Total disk space [bytes].
            - Used disk space [bytes].
            - Free disk space [bytes].
        """

        pass


def _disentangle_filename(filename: Union[str, Path]) -> Tuple:
    """Disentangle the given filename and return the test identifier, the site id and the Setup id.

    It is assumed in this function that the filename is from a test observation and contains the
    correct fields to be extracted. Only very limited checking is done if that is indeed the case.

    Args:
        filename (str, Path): the filename of a test observation

    Returns:
        A tuple containing the test_id (int), site_id (str) and setup_id (int). If the filename is
        not recognized as a valid filename, the returned tuple contains all None.

    """
    filename = Path(filename).resolve()
    parts = filename.parts

    if parts[-2] != 'obs':
        name = parts[-1]
        if not (name.rsplit('_', 3)[0].endswith('_SPW') or name.rsplit('_', 2)[0].endswith('_SPW')):
            return None, None, None

    name = parts[-1]
    test_id, site_id, setup_id = name.split('_')[:3]
    return int(test_id), site_id, int(setup_id)


def _construct_filename(
        identifier: str, ext: str, obsid: ObservationIdentifier = None, use_counter=False,
        location: str = None, site_id: str = None, camera_name: str = None
) -> PurePath:
    """Construct a filename for the data source.

    We construct two types of filenames:

    1. the observational files which store all the data that are collected during an observation.
       There is one file per data source. The files are located in the `obs` sub-folder of the
       storage location.
    2. the daily files which store all the data from a data source regardless the state of an
       observation. There is one file per data source. The files are located in the `daily`
       sub-folder of the storage location.

    Args:
        identifier (str): an identifier for the source of the data, this string is usually what
            is sent in the `origin` of the item dictionary.
        ext (str): the extension of the file, this depends oon the persistence class that is
            used for storing the data.
        obsid (ObservationIdentifier): a unique identifier for the observation
        use_counter: Indicates whether or not a counter should be included in the filename.
    Returns:
        The full path to the file as a `PurePath`.
    """

    site_id = site_id or SITE_ID
    location = location or get_data_storage_location(site_id=site_id)

    if obsid:

        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

        prefix = obsid.create_id(order=TEST_LAB, camera_name=camera_name)
        location = location / Path("obs") / f"{prefix}"
        if not os.path.exists(location):
            os.makedirs(location)

        if use_counter:
            counter_file_path = location / f"{prefix}_{identifier}.count"
            if not counter_file_path.exists():
                pattern = f"{prefix}_{identifier}_{timestamp}_*.{ext}"
                counter = determine_counter_from_dir_list(location, pattern)
                _write_counter(counter, counter_file_path)
            else:
                counter = get_counter(counter_file_path)
            name = f"{prefix}_{identifier}_{counter:05d}_{timestamp}.{ext}"
        else:
            name = f"{prefix}_{identifier}_{timestamp}.{ext}"

    else:

        timestamp = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d")

        location = location / Path("daily") / timestamp
        if not os.path.exists(location):
            os.makedirs(location)

        if use_counter:
            counter_file_path = location / f"{timestamp}_{site_id}_{identifier}.count"
            if not counter_file_path.exists():
                pattern = f"{timestamp}_{site_id}_{identifier}_*.{ext}"
                counter = determine_counter_from_dir_list(location, pattern)
                _write_counter(counter, counter_file_path)
            else:
                counter = get_counter(counter_file_path)
            name = f"{timestamp}_{site_id}_{identifier}_{counter:05d}.{ext}"
        else:
            name = f"{timestamp}_{site_id}_{identifier}.{ext}"

    return Path(location) / name


def _write_counter(counter: int, file_path: Path):
    """
    Overwrites the given counter in the given file. The file contains nothing else then the counter.
    If the file didn't exist before, it will be created.

    Args:
        counter: the counter to save
        file_path: the file to which the counter shall be saved
    """
    with file_path.open('w') as fd:
        fd.write(f"{counter:d}")


def _read_counter(file_path: Path) -> int:
    """
    Reads a counter from the given file. The file shall only contain the counter which must
    be an integer on the first line of the file. If the given file doesn't exist, 0 is returned.

    Args:
        file_path: the full path of the file containing the counter

    Returns:
        The counter that is read from the file or 0 if file doesn't exist.
    """
    try:
        with file_path.open('r') as fd:
            counter = fd.read().strip()
    except FileNotFoundError:
        counter = 0
    return int(counter or 0)


def get_counter(file_path: Path) -> int:
    """
    Read the counter from a dedicated file, add one and save the counter back to the file..

    Args:
        - file_path: full pathname of the file that contains the required counter

    Returns:
        The value of the next counter, 1 if no previous files were found or if an error occurred.
    """

    counter = _read_counter(file_path)
    counter += 1
    _write_counter(counter, file_path)

    return counter


def determine_counter_from_dir_list(location, pattern, index: int = -1):
    """
    Determine counter for a new file at the given location and with the given pattern.
    The next counter is determined from the sorted list of files that match the given pattern.

    Args:
        - location: Location where the file should be stored.
        - pattern: Pattern for the filename.
        - index: the location of the counter in the filename after it is split on '_' [default=-1]

    Returns:
        The value of the next counter, 1 if no previous files were found or if an error occurred.
    """

    files = sorted(find_files(pattern=pattern, root=location))

    # No filenames found showing the given pattern -> start counting at 1

    if len(files) == 0:
        return 1

    last_file = files[-1]

    parts = last_file.name.split("_")

    try:

        # Observation files have the following pattern:
        #  <test ID>_<lab ID>_<setup ID>_<storage mnemonic>_<day YYYYmmdd>_<time HHMMSS>[_<counter>]
        # Daily files:
        #  <day>_<site ID>_<storage mnemonic>[_<counter>]

        counter = int(parts[index].split(".")[0]) + 1
        logger.debug(f"{counter = }")
        return counter

    except ValueError:
        logger.warning("ValueError", exc_info=True)
        return 1


class StorageController(StorageInterface):
    """
    The Storage Controller handles the registration of components, the start and end of an
    observation/test and the dispatching of the persistence functions in save.
    """

    def __init__(self):
        self._obsid: ObservationIdentifier | None = None
        self._camera_name: str | None = None
        self._registry = Registry()

    def start_observation(self, obsid: ObservationIdentifier, camera_name: str = None) -> Response:
        if self._obsid is not None:
            return Failure(
                "Can not start a new observation before the previous observation is ended."
            )

        self._obsid = obsid
        self._camera_name = camera_name

        # open a dedicated file for each registered item

        for registered_name in self._registry:
            registered_item = self._registry.get(registered_name)

            if "persistence_count" in registered_item:
                # no need to fork any files that contain persistence_counts
                continue

            # FIXME: create a list for all classes that need to be skipped here. Allow the list to be changed
            #        by a method call
            no_duplicates = tuple()
            if issubclass(registered_item["persistence_class"], no_duplicates):
                # do not duplicate HDF5 files during an observation - issue #1186
                continue

            # NOTE: The following lines of code contain tests for special treatment of HDF5 files
            # while the above check disables HDF5 files in OBS. We leave the code in for now until
            # a definite decision is taken.

            filename = _construct_filename(
                registered_item["origin"],
                registered_item["persistence_class"].extension,
                obsid,
                use_counter=issubclass(registered_item["persistence_class"], HDF5),
                camera_name=camera_name
            )

            # logger.debug(f"{filename = }, {camera_name = }")

            # we have more than one file open for this item DAILY and OBS.... take care of that

            # Special case for HDF5 files as they need to be copied instead of created

            if issubclass(registered_item["persistence_class"], HDF5):
                daily_file_object: HDF5 = registered_item["persistence_objects"][0]
                daily_file_path: Path = daily_file_object.get_filepath()
                logger.debug(f"Copying {daily_file_path} to {filename}")

                # Close the HDF5 file before copy, otherwise you will get
                # a 'bad object header version number' when opening the destination.

                daily_file_object.close()
                shutil.copy(daily_file_path, filename)
                daily_file_object.open(mode='a')

            persistence_obj = registered_item["persistence_class"](
                filename, prep=registered_item["prep"]
            )

            mode = "a" if persistence_obj.exists() else "w"
            persistence_obj.open(mode=mode)

            registered_item["persistence_objects"].append(persistence_obj)

        return Success("Storage successfully started observation.")

    def end_observation(self, obsid: ObservationIdentifier) -> Response:
        if obsid != self._obsid:
            return Failure(f"Given obsid doesn't match current obsid: {obsid} != {self._obsid}")

        # close the dedicated file for each registered item

        for registered_name in self._registry:
            registered_item = self._registry.get(registered_name)
            if "persistence_count" in registered_item:
                # no need to close any files that contain persistence_counts
                continue
            try:
                persistence_obj = registered_item["persistence_objects"].pop()
                persistence_obj.close()
            except IndexError as exc:
                logger.warning(f"Trying to close a persistent object for {registered_name}, {exc=}")

        self._obsid = None
        self._camera_name = None

        return Success("Storage successfully ended observation.")

    def get_obsid(self):
        return self._obsid

    def save(self, item: dict) -> Response:
        """Saves the data contained in this item to the right location and format.

        Args:
            item: dictionary with at least the following keywords - origin, data
        Returns:
            Success: when the data has been properly saved.
        """
        # TODO:
        #  this method might become a performance problem and the reason that we might have
        #  back pressure problem. Keep an eye on this and do performance tests.

        # What needs to be done:
        # * based on item['origin'], check if item component is registered
        # * get register entry for item
        # * for persistence in persistence list:
        #      persistence.create(data)

        registered_item = self._registry.get(item["origin"])

        if not registered_item:
            return Failure(
                f"Storage could not find a registration for {item['origin']}, no data saved."
            )

        for persistence_object in registered_item["persistence_objects"]:
            persistence_object.create(item["data"])

        return Success(f"Storage successfully saved the data for {item['origin']}.")

    def read(self, item: dict):

        registered_item = self._registry.get(item["origin"])

        if not registered_item:
            return Failure(
                f"Storage could not find a registration for {item['origin']}, no data saved."
            )

        # FIXME:
        #   * wat als meerdere persistence_objects bestaan? alleen de eerste, alleen de laatste,
        #     samenvoegen? een nieuw keyword in item?

        result = None
        for persistence_object in registered_item["persistence_objects"]:
            result = persistence_object.read(item["select"])

        return Success(f"Storage successfully read the data from {item['origin']}.", result)

    def register(self, item: dict, use_counter=False) -> Response:

        if not isinstance(item, dict):
            return Failure(
                f"Could not register item, item must be a dictionary (item={type(item)})."
            )

        prep = item.get("prep", {})

        # When we register an item, the file should always be 'created', unless this is a
        # persistence count and we just need to append to the file, always.

        # if "persistence_count" not in item:
        #     prep.update({"mode": "w"})

        if "origin" not in item or "persistence_class" not in item:
            return Failure("Could not register item, missing mandatory keyword(s).")

        try:
            self._registry.register(item["origin"], item)

            if "filename" in item:
                location = Path(get_data_storage_location(site_id=SITE_ID))
                filename = location / item["filename"]
            else:
                filename = _construct_filename(item["origin"], item["persistence_class"].extension,
                                               use_counter=use_counter)

            persistence_obj = item["persistence_class"](filename, prep=prep)
            mode = "a" if persistence_obj.exists() else "w"
            persistence_obj.open(mode=mode)

            # add the PersistenceLayer object to the registered item

            item["persistence_objects"] = [persistence_obj]

            # Special case when the components registration is done after an observation was
            # started, unless we are handling a persistence_count, in which case there is only one
            # file.

            if (
                self._obsid
                and "persistence_count" not in item
                and not issubclass(item["persistence_class"], HDF5)
            ):
                filename = _construct_filename(
                    item["origin"], item["persistence_class"].extension, self._obsid,
                    use_counter=use_counter, camera_name=self._camera_name
                )

                persistence_obj = item["persistence_class"](filename, prep=prep)
                mode = "a" if persistence_obj.exists() else "w"
                persistence_obj.open(mode=mode)

                item["persistence_objects"].append(persistence_obj)

            msg = f"Storage successfully registered {item['origin']}"
            logger.info(msg)
            return Success(msg)
        except AlreadyRegisteredError as exc:
            msg = f"Could not register {item['origin']}: {exc}"
            logger.error(msg)
            return Success(f"{item['origin']} is already registered.")
        except (ValueError, KeyError) as exc:
            # FIXME:
            #  Should I unregister here? and if yes, should I not call the
            #  self.unregister(item) method instead?
            self._registry.unregister(item["origin"])
            msg = f"Could not register {item['origin']}: {exc}"
            logger.error(msg)
            return Failure(f"Could not register {item['origin']}", exc)

    def unregister(self, item) -> Response:
        try:
            registered_item = self._registry.get(item["origin"])
            if registered_item is None:
                raise ValueError("The item is not registered.")

            # Probably also should close the file and some other things

            for persistence_obj in registered_item.get("persistence_objects", []):
                persistence_obj.close()

            self._registry.unregister(item["origin"])

            msg = f"Storage successfully unregistered {item['origin']}"
            logger.info(msg)
            return Success(msg)
        except (ValueError, KeyError) as exc:
            return Failure(f"Could not unregister {item['origin']}", exc)

    def get_registry_names(self):
        return list(self._registry)

    def cycle_daily_files(self):

        logger.info("Cycling daily files for Storage Manager")

        for reg_name in self._registry:
            item = self._registry.get(reg_name)
            if "persistence_count" in item:
                # no need to cycle any files that contain persistence_counts
                continue
            if "persistence_objects" in item:
                logger.info(f"Cycling daily file for {item['origin']}.")

                # The first item in the list is always the daily persistence object, however, for
                # the N-FEE_SPW origin, sometimes when the N-FEE is not ON, there is no persistence
                # object. (see issue #1458) So, we catch this and continue.

                try:
                    daily_persist_obj = item["persistence_objects"][0]
                    daily_persist_obj.close()
                except IndexError:
                    logger.info(f"I'm ignoring that there is no persistence_object "
                                f"for {item['origin']} at this time.")
                    continue

                # Create folder for the day
                filename = _construct_filename(item['origin'], item['persistence_class'].extension)

                persistence_obj: PersistenceLayer = item["persistence_class"](
                    filename, prep=item.get("prep")
                )
                mode = "a" if persistence_obj.exists() else "w"
                persistence_obj.open(mode=mode)

                # replace the previous daily persistence object with the current

                item["persistence_objects"][0] = persistence_obj

            else:
                # We should never get here, since when an item is registered, the 'file' is
                # opened and it should exist
                logger.error(
                    f"Found a registered item {item} that has no persistence objects.",
                    stack_info=True,
                )

    def get_storage_location(self):
        return get_data_storage_location(site_id=SITE_ID)

    def get_filenames(self, item: dict) -> List[Path]:
        registered_item = self._registry.get(item["origin"])

        if not registered_item:
            return []

        return [
            persistence_object.get_filepath()
            for persistence_object in registered_item["persistence_objects"]
        ]

    def new_registration(self, item: dict, use_counter=False) -> Response:
        if item["origin"] in self.get_registry_names():
            _ = self.unregister(item)

        response = self.register(item, use_counter=use_counter)
        logger.info(f"From register: {response=}")
        return response

    def get_disk_usage(self):

        location = Path(get_data_storage_location(site_id=SITE_ID))
        total, used, free = shutil.disk_usage(location)
        return total, used, free


class StorageCommand(ClientServerCommand):
    pass


class StorageProxy(Proxy, StorageInterface):
    """The StorageProxy class is used to connect to the Storage Manager (control server) and
    send commands remotely."""

    def __init__(
        self,
        protocol=CTRL_SETTINGS.PROTOCOL,
        hostname=CTRL_SETTINGS.HOSTNAME,
        port=CTRL_SETTINGS.COMMANDING_PORT,
        timeout=REQUEST_TIMEOUT,
    ):
        """
        Args:
            protocol: the transport protocol [default is taken from settings file]
            hostname: location of the control server (IP address)
                [default is taken from settings file]
            port: TCP port on which the control server is listening for commands
                [default is taken from settings file]
        """
        super().__init__(connect_address(protocol, hostname, port), timeout=timeout)


class StorageProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

        self.controller = StorageController()

        self.load_commands(COMMAND_SETTINGS.Commands, StorageCommand, StorageController)

        self.build_device_method_lookup_table(self.controller)

    def get_bind_address(self):
        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_status(self) -> dict:
        return super().get_status()

    def get_housekeeping(self) -> dict:
        return {
            "timestamp": format_datetime(),
        }


def get_status(full: bool = False):

    if is_storage_manager_active():
        with StorageProxy() as sm:
            text =  textwrap.dedent(
                f"""\
                Storage Manager:
                    Status: [green]active[/]
                    Hostname: {sm.get_ip_address()}
                    Monitoring port: {sm.get_monitoring_port()}
                    Commanding port: {sm.get_commanding_port()}
                    Service port: {sm.get_service_port()}
                    Storage location: {sm.get_storage_location()}
                    Registrations: {sm.get_registry_names()}
                """
            )
            if full:
                text += "Filenames for all registered items:\n"
                for origin in sm.get_registry_names():
                    fn = [x for x in sm.get_filenames({"origin": origin})]
                    text += f"  {origin:10s} ->  {fn}\n"
                if obsid := sm.get_obsid():
                    text += f"An observation is registered: {obsid}\n"
                else:
                    text += "No observation is registered.\n"

                total, used, free = sm.get_disk_usage()
                text += f"Total disk space: {humanize_bytes(total)}\n"
                text += f"Used disk space: {humanize_bytes(used)} ({(used / total * 100):.2f}%)\n"
                text += f"Free disk space: {humanize_bytes(free)} ({(free / total * 100):.2f}%)\n"

        return text

    else:
        return "Storage Manager Status: [red]not active"
