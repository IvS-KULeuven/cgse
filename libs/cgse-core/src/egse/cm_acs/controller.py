"""Controller logic for the asynchronous Configuration Manager."""

from __future__ import annotations

import asyncio
import operator
import threading
from pathlib import Path
from typing import Any
from typing import Union

import egse.cm_acs as cm_acs_module
import egse.confman as confman_module
from egse.async_control import DeviceCommandRouter
from egse.command import stringify_function_call
from egse.confman import _add_setup_info_to_cache
from egse.confman import _construct_filename
from egse.confman import _get_description_for_setup
from egse.confman import _get_sut_id_for_setup
from egse.confman import _push_setup_to_repo
from egse.confman import create_obsid
from egse.confman import disentangle_filename
from egse.confman import find_file
from egse.confman import find_files
from egse.confman import get_conf_repo_location
from egse.confman import load_last_setup_id
from egse.confman import save_last_setup_id
from egse.env import get_conf_data_location
from egse.log import logging
from egse.notifyhub.event import NotificationEvent
from egse.notifyhub.services import EventPublisher
from egse.obsid import ObservationIdentifier
from egse.response import Failure
from egse.response import Response
from egse.response import Success
from egse.serialization import to_json_safe
from egse.settings import SettingsError
from egse.setup import Setup
from egse.system import duration
from egse.system import filter_by_attr
from egse.system import format_datetime
from egse.system import humanize_seconds
from egse.zmq_ser import zmq_json_response

logger = logging.getLogger("egse.cm_acs")

# Mutating operations are kept sequential to preserve controller state consistency.
SEQUENTIAL_CONTROLLER_METHODS = {
    "start_observation",
    "start_observation_async",
    "end_observation",
    "end_observation_async",
    "register_to_storage",
    "register_to_storage_async",
    "load_setup",
    "load_setup_async",
    "reload_setups",
    "reload_setups_async",
    "submit_setup",
    "submit_setup_async",
}

# No controller methods currently rely on generic whole-method thread offloading.
THREADED_CONTROLLER_METHODS: set[str] = set()


def _active_site_id() -> str:
    return cm_acs_module.get_active_site_id()


class AsyncConfigurationManagerController(DeviceCommandRouter):
    """Native controller for async confman command handling."""

    def __init__(self, control_server):
        super().__init__(control_server)
        self._obsid: ObservationIdentifier | None = None
        self._obsid_start_dt: str | None = None
        self._setup: Setup | None = None
        self._setup_id: int | None = None
        self._sut_id: str | None = None
        self._storage = None

        self.register_to_storage()

        location = get_conf_data_location()
        if location:
            self._data_conf_location = Path(location).expanduser()
        else:
            raise ValueError("The location for the configuration data is not defined. Please check your environment.")

        # Populate the cache with information from the available Setups. This will also load each
        # Setup and cache them with the lru_cache decorator. Since this takes about 5s for 100
        # Setups, we run this function in a daemon thread in order not to block the cm_cs from
        # reacting to command requests.

        cache_thread = threading.Thread(target=confman_module._populate_cached_setup_info, daemon=True)
        cache_thread.start()

        setup_id = load_last_setup_id()
        self.load_setup(setup_id)

    def quit(self):
        if self._storage:
            self._storage.disconnect_cs()

    def register_default_handlers(self):
        super().register_default_handlers()  # say, block
        self.add_handler("start_observation", self._do_start_observation)
        self.add_handler("end_observation", self._do_end_observation)
        self.add_handler("get_obsid", self._do_get_obsid)
        self.add_handler("load_setup", self._do_load_setup)
        self.add_handler("get_setup", self._do_get_setup)
        self.add_handler("reload_setups", self._do_reload_setups)
        self.add_handler("list_setups", self._do_list_setups)
        self.add_handler("submit_setup", self._do_submit_setup)
        self.add_handler("get_setup_for_obsid", self._do_get_setup_for_obsid)

    async def _run_controller_call(self, method_name: str, *args, **kwargs):
        method = getattr(self, method_name)

        if asyncio.iscoroutinefunction(method):
            return await method(*args, **kwargs)

        if method_name in THREADED_CONTROLLER_METHODS:
            return await asyncio.to_thread(method, *args, **kwargs)

        return method(*args, **kwargs)

    def _controller_result_to_payload(self, method_name: str, result: Any) -> dict[str, Any]:
        if isinstance(result, Success):
            return {
                "success": True,
                "message": result.message,
                "return_code": to_json_safe(result.return_code),
                "result_type": "Success",
            }

        if isinstance(result, Failure):
            payload: dict[str, Any] = {
                "success": False,
                "message": str(result),
                "result_type": "Failure",
            }
            if result.cause is not None:
                payload["cause"] = repr(result.cause)
            return payload

        if isinstance(result, Response):
            return {
                "success": result.successful,
                "message": str(result),
                "result_type": type(result).__name__,
            }

        return {
            "success": True,
            "message": f"{method_name} completed",
            "return_code": to_json_safe(result),
            "result_type": type(result).__name__,
        }

    async def _handle_controller_call(self, method_name: str, *args, **kwargs) -> list:
        async def operation():
            return await self._run_controller_call(method_name, *args, **kwargs)

        try:
            if method_name in SEQUENTIAL_CONTROLLER_METHODS:
                result = await self._control_server._execute_sequential(operation())
            else:
                result = await operation()
            payload = self._controller_result_to_payload(method_name, result)
        except Exception as exc:
            logger.exception("Controller command failed", extra={"method_name": method_name})
            payload = {
                "success": False,
                "message": f"{type(exc).__name__}: {exc}",
                "result_type": "Exception",
                "method": method_name,
            }

        return zmq_json_response(payload)

    async def _do_start_observation(self, cmd: dict[str, Any]) -> list:
        function_info = cmd.get("function_info") or {}
        if not isinstance(function_info, dict):
            function_info = {}
        return await self._handle_controller_call("start_observation_async", function_info)

    async def _do_end_observation(self, cmd: dict[str, Any]) -> list:
        return await self._handle_controller_call("end_observation_async")

    async def _do_get_obsid(self, cmd: dict[str, Any]) -> list:
        return await self._handle_controller_call("get_obsid")

    async def _do_load_setup(self, cmd: dict[str, Any]) -> list:
        return await self._handle_controller_call("load_setup_async", cmd.get("setup_id"))

    async def _do_get_setup(self, cmd: dict[str, Any]) -> list:
        return await self._handle_controller_call("get_setup_async", cmd.get("setup_id"))

    async def _do_reload_setups(self, cmd: dict[str, Any]) -> list:
        return await self._handle_controller_call("reload_setups_async")

    async def _do_list_setups(self, cmd: dict[str, Any]) -> list:
        attributes = cmd.get("attributes") or {}
        if not isinstance(attributes, dict):
            attributes = {}
        return await self._handle_controller_call("list_setups_async", **attributes)

    async def _do_submit_setup(self, cmd: dict[str, Any]) -> list:
        setup = cmd.get("setup")
        description = cmd.get("description", "")
        replace = bool(cmd.get("replace", True))
        return await self._handle_controller_call("submit_setup_async", setup, description, replace)

    async def _do_get_setup_for_obsid(self, cmd: dict[str, Any]) -> list:
        return await self._handle_controller_call("get_setup_for_obsid_async", cmd.get("obsid"))

    def start_observation(self, function_info: dict) -> Response:
        if self._obsid is not None:
            return Failure(
                "An new observation can not be started before the previous observation is finished. "
                "You will need to first send an end_observation request "
                "to the configuration manager."
            )

        last_obsid = None
        if self._storage:
            last_obsid_response = self._storage.read({"origin": "obsid", "select": "last_line"})
            last_obsid = last_obsid_response.return_code if isinstance(last_obsid_response, Success) else None

        if self._setup_id is None:
            return Failure("No setup loaded on configuration manager.")

        site_id = _active_site_id()
        self._obsid = create_obsid(last_obsid or "", site_id, self._setup_id)
        self._obsid_start_dt = format_datetime()

        if self._storage:
            response = self._storage.start_observation(self._obsid, self._sut_id)
        else:
            return Failure("Couldn't send start observation to Storage Manager, no Storage Manager available.")

        if not response.successful:
            self._obsid = None
            return Failure("Sending a start_observation to the Storage Manager Control Server failed", response)

        description = function_info.pop("description", "")
        cmd = stringify_function_call(function_info).replace("\n", " ")

        if description:
            cmd += f" [{description}]"

        response = self._storage.save(
            {
                "origin": "obsid",
                "data": f"{self._obsid.test_id:05d} "
                f"{self._obsid.lab_id} "
                f"{self._obsid.setup_id:05d} "
                f"{self._obsid_start_dt} "
                f"{cmd}",
            }
        )

        if isinstance(response, Failure):
            logger.warning(f"There was a Failure when saving to the obsid-table: {response}")
        else:
            logger.info(f"Successfully created an observation with obsid={self._obsid}.")

        return Success("Returning the OBSID", self._obsid)

    async def start_observation_async(self, function_info: dict) -> Response:
        if self._obsid is not None:
            return Failure(
                "An new observation can not be started before the previous observation is finished. "
                "You will need to first send an end_observation request "
                "to the configuration manager."
            )

        last_obsid = None
        if self._storage:
            last_obsid_response = await asyncio.to_thread(
                self._storage.read,
                {"origin": "obsid", "select": "last_line"},
            )
            last_obsid = last_obsid_response.return_code if isinstance(last_obsid_response, Success) else None

        if self._setup_id is None:
            return Failure("No setup loaded on configuration manager.")

        site_id = _active_site_id()
        self._obsid = create_obsid(last_obsid or "", site_id, self._setup_id)
        self._obsid_start_dt = format_datetime()

        if self._storage:
            response = await asyncio.to_thread(self._storage.start_observation, self._obsid, self._sut_id)
        else:
            return Failure("Couldn't send start observation to Storage Manager, no Storage Manager available.")

        if not response.successful:
            self._obsid = None
            return Failure("Sending a start_observation to the Storage Manager Control Server failed", response)

        description = function_info.pop("description", "")
        cmd = stringify_function_call(function_info).replace("\n", " ")

        if description:
            cmd += f" [{description}]"

        response = await asyncio.to_thread(
            self._storage.save,
            {
                "origin": "obsid",
                "data": f"{self._obsid.test_id:05d} "
                f"{self._obsid.lab_id} "
                f"{self._obsid.setup_id:05d} "
                f"{self._obsid_start_dt} "
                f"{cmd}",
            },
        )

        if isinstance(response, Failure):
            logger.warning(f"There was a Failure when saving to the obsid-table: {response}")
        else:
            logger.info(f"Successfully created an observation with obsid={self._obsid}.")

        return Success("Returning the OBSID", self._obsid)

    def end_observation(self) -> Response:
        if not self._obsid:
            return Failure("Received end_observation command while not currently in an observation context.")

        if self._storage:
            response = self._storage.end_observation(self._obsid)
        else:
            return Failure("Couldn't send end observation to Storage Manager, no Storage Manager available.")

        if not response.successful:
            return Failure("Sending an end_observation to the Storage Manager Control Server failed.", response)

        obsid_end_dt = format_datetime()
        if self._obsid_start_dt is None:
            return Failure("Observation start timestamp is not defined.")

        obs_duration = humanize_seconds(
            duration(self._obsid_start_dt, obsid_end_dt).total_seconds(), include_micro_seconds=False
        )
        logger.info(f"Successfully ended observation with obsid={self._obsid}, duration={obs_duration}.")

        self._obsid = None
        self._obsid_start_dt = None

        return Success("Successfully ended the observation.")

    async def end_observation_async(self) -> Response:
        if not self._obsid:
            return Failure("Received end_observation command while not currently in an observation context.")

        if self._storage:
            response = await asyncio.to_thread(self._storage.end_observation, self._obsid)
        else:
            return Failure("Couldn't send end observation to Storage Manager, no Storage Manager available.")

        if not response.successful:
            return Failure("Sending an end_observation to the Storage Manager Control Server failed.", response)

        obsid_end_dt = format_datetime()
        if self._obsid_start_dt is None:
            return Failure("Observation start timestamp is not defined.")

        obs_duration = humanize_seconds(
            duration(self._obsid_start_dt, obsid_end_dt).total_seconds(), include_micro_seconds=False
        )
        logger.info(f"Successfully ended observation with obsid={self._obsid}, duration={obs_duration}.")

        self._obsid = None
        self._obsid_start_dt = None

        return Success("Successfully ended the observation.")

    def get_obsid(self) -> Success:
        if self._obsid:
            msg = "Returning the current OBSID."
        else:
            msg = "No observation running. Use start_observation() to start an observation."
        return Success(msg, self._obsid)

    def register_to_storage(self):
        from egse.storage import StorageProxy
        from egse.storage import is_storage_manager_active
        from egse.storage.persistence import TYPES

        if is_storage_manager_active():
            self._storage = StorageProxy()
            response = self._storage.register(
                {
                    "origin": "obsid",
                    "persistence_class": TYPES["TXT"],
                    "prep": {"mode": "a", "ending": "\n"},
                    "persistence_count": True,
                    "filename": "obsid-table.txt",
                }
            )
            logger.info(response)
        else:
            self._storage = None
            logger.error("No Storage Manager available !!!!")

    async def register_to_storage_async(self):
        return await asyncio.to_thread(self.register_to_storage)

    def load_setup(self, setup_id: int | None = None) -> Union[Setup, Failure]:
        if setup_id is None:
            return Failure(
                "No Setup ID was given, cannot load a Setup into the configuration manager. "
                "If you wanted to get the current Setup from the configuration manager, "
                "use the get_setup() method instead."
            )

        if self._obsid:
            return Failure(
                f"A new Setup can not be loaded when an observation is running. "
                f"The current obsid is {self._obsid}. Use `end_observation()` before loading a new Setup."
            )

        site_id = _active_site_id()
        setup_files = list(find_files(pattern=f"SETUP_{site_id}_{setup_id:05d}_*.yaml", root=self._data_conf_location))

        if len(setup_files) != 1:
            return Failure("Loading Setup", ValueError(f"Expected 1 setup file, found {len(setup_files)}."))

        setup_file = setup_files[0]

        try:
            self._setup = Setup.from_yaml_file(setup_file)
            self._setup_id = setup_id
            self._sut_id = _get_sut_id_for_setup(self._setup)
            save_last_setup_id(self._setup_id)

            with EventPublisher() as pub:
                pub.publish(
                    NotificationEvent(
                        event_type="new_setup",
                        source_service="cm_acs",
                        data={"setup_id": self._setup_id},
                    )
                )

            logger.info(f"New Setup loaded from {setup_file}")
            return self._setup
        except SettingsError as exc:
            return Failure(f"The Setup file can not be loaded from {setup_file}.", exc)

    async def load_setup_async(self, setup_id: int | None = None) -> Union[Setup, Failure]:
        if setup_id is None:
            return Failure(
                "No Setup ID was given, cannot load a Setup into the configuration manager. "
                "If you wanted to get the current Setup from the configuration manager, "
                "use the get_setup() method instead."
            )

        if self._obsid:
            return Failure(
                f"A new Setup can not be loaded when an observation is running. "
                f"The current obsid is {self._obsid}. Use `end_observation()` before loading a new Setup."
            )

        site_id = _active_site_id()
        setup_files = list(
            await asyncio.to_thread(
                find_files,
                pattern=f"SETUP_{site_id}_{setup_id:05d}_*.yaml",
                root=self._data_conf_location,
            )
        )

        logger.debug(f"Pattern used for finding setup file: SETUP_{site_id}_{setup_id:05d}_*.yaml")
        logger.debug(f"Looking for setup files in {self._data_conf_location}")

        if len(setup_files) != 1:
            return Failure("Loading Setup", ValueError(f"Expected 1 setup file, found {len(setup_files)}."))

        setup_file = setup_files[0]

        try:
            setup = await asyncio.to_thread(Setup.from_yaml_file, setup_file)
            self._setup = setup
            self._setup_id = setup_id
            self._sut_id = _get_sut_id_for_setup(self._setup)
            await asyncio.to_thread(save_last_setup_id, self._setup_id)

            await asyncio.to_thread(self._publish_new_setup_event)

            logger.info(f"New Setup loaded from {setup_file}")
            return self._setup
        except SettingsError as exc:
            return Failure(f"The Setup file can not be loaded from {setup_file}.", exc)

    def get_setup(self, setup_id: int | None = None) -> Union[Setup, Failure]:
        if setup_id:
            site_id = _active_site_id()
            setup_files = list(
                find_files(pattern=f"SETUP_{site_id}_{setup_id:05d}_*.yaml", root=self._data_conf_location)
            )

            if len(setup_files) != 1:
                return Failure(
                    "Expected only one Setup.",
                    ValueError(f"Expected 1 setup file, found {len(setup_files)}."),
                )

            setup_file = setup_files[0]
            try:
                return Setup.from_yaml_file(setup_file)
            except SettingsError as exc:
                return Failure(f"The Setup file can not be loaded from {setup_file}.", exc)

        if self._setup:
            return self._setup
        return Failure("No Setup was loaded on the Configuration Manager.")

    async def get_setup_async(self, setup_id: int | None = None) -> Union[Setup, Failure]:
        if setup_id:
            site_id = _active_site_id()
            setup_files = list(
                await asyncio.to_thread(
                    find_files,
                    pattern=f"SETUP_{site_id}_{setup_id:05d}_*.yaml",
                    root=self._data_conf_location,
                )
            )

            if len(setup_files) != 1:
                return Failure(
                    "Expected only one Setup.",
                    ValueError(f"Expected 1 setup file, found {len(setup_files)}."),
                )

            setup_file = setup_files[0]
            try:
                return await asyncio.to_thread(Setup.from_yaml_file, setup_file)
            except SettingsError as exc:
                return Failure(f"The Setup file can not be loaded from {setup_file}.", exc)

        if self._setup:
            return self._setup
        return Failure("No Setup was loaded on the Configuration Manager.")

    def get_setup_id(self) -> int | None:
        return self._setup_id

    def get_site_id(self) -> str:
        return _active_site_id()

    def reload_setups(self):
        confman_module._reload_cached_setup_info()

    async def reload_setups_async(self):
        await asyncio.to_thread(confman_module._reload_cached_setup_info)

    def list_setups(self, **attr):
        setup_list = []

        setups = [Setup.from_yaml_file(info.path) for info in confman_module._cached_setup_info.values()]
        setups = filter_by_attr(setups, **attr)

        for setup in setups:
            setup_site, setup_id = disentangle_filename(str(setup.get_filename()))
            description = _get_description_for_setup(setup, int(setup_id))
            sut_id = _get_sut_id_for_setup(setup)
            setup_list.append((setup_id, setup_site, description, sut_id))

        return sorted(setup_list, key=operator.itemgetter(1, 0), reverse=False)

    async def list_setups_async(self, **attr):
        setup_list = []

        setup_infos = list(confman_module._cached_setup_info.values())
        setups = await asyncio.gather(*(asyncio.to_thread(Setup.from_yaml_file, info.path) for info in setup_infos))
        setups = filter_by_attr(setups, **attr)

        for setup in setups:
            setup_site, setup_id = disentangle_filename(str(setup.get_filename()))
            description = _get_description_for_setup(setup, int(setup_id))
            sut_id = _get_sut_id_for_setup(setup)
            setup_list.append((setup_id, setup_site, description, sut_id))

        return sorted(setup_list, key=operator.itemgetter(1, 0), reverse=False)

    def _publish_new_setup_event(self):
        with EventPublisher() as pub:
            pub.publish(
                NotificationEvent(
                    event_type="new_setup",
                    source_service="cm_acs",
                    data={"setup_id": self._setup_id},
                )
            )

    def get_setup_for_obsid(self, obsid):
        if not self._storage:
            return Failure("No Storage Manager available.")

        obsid = f"{obsid:05d}" if isinstance(obsid, int) else obsid
        rc = self._storage.read({"origin": "obsid", "select": ("startswith", obsid)})
        if not rc.successful:
            return Failure("Failed to read setup for obsid.")

        try:
            setup_id = int(rc.return_code[-1].split(maxsplit=3)[2])
            site_id = _active_site_id()
            setup_file = find_file(name=f"SETUP_{site_id}_{setup_id:05d}_*.yaml", root=self._data_conf_location)
            return Setup.from_yaml_file(setup_file)
        except Exception as exc:
            return Failure("Failed to resolve setup for obsid.", exc)

    async def get_setup_for_obsid_async(self, obsid):
        if not self._storage:
            return Failure("No Storage Manager available.")

        obsid = f"{obsid:05d}" if isinstance(obsid, int) else obsid
        rc = await asyncio.to_thread(self._storage.read, {"origin": "obsid", "select": ("startswith", obsid)})
        if not rc.successful:
            return Failure("Failed to read setup for obsid.")

        try:
            setup_id = int(rc.return_code[-1].split(maxsplit=3)[2])
            site_id = _active_site_id()
            setup_file = await asyncio.to_thread(
                find_file,
                name=f"SETUP_{site_id}_{setup_id:05d}_*.yaml",
                root=self._data_conf_location,
            )
            return await asyncio.to_thread(Setup.from_yaml_file, setup_file)
        except Exception as exc:
            return Failure("Failed to resolve setup for obsid.", exc)

    def submit_setup(self, setup: Setup, description: str, replace: bool = True) -> Setup | Failure:
        if self._obsid is not None:
            return Failure(
                "An new Setup can not be submitted when an observation is running. "
                "You will need to first send an end_observation request to the configuration manager."
            )

        site = getattr(setup, "site_id", _active_site_id())
        setup_id = self.get_next_setup_id_for_site(site)
        filename = _construct_filename(site, setup_id)

        history = getattr(setup, "history", None)
        if not isinstance(history, dict):
            history = {}
            setattr(setup, "history", history)

        history.update({f"{setup_id}": description})
        setup.set_private_attribute("_setup_id", setup_id)
        setup.to_yaml_file(self._data_conf_location / filename)

        if get_conf_repo_location():
            try:
                rc = _push_setup_to_repo(filename, description)
                if isinstance(rc, Failure):
                    return rc
                _add_setup_info_to_cache(setup)
            except Exception as exc:
                return Failure("Submit_setup could not send the new Setup to the repo.", exc)

        if replace:
            self._setup = setup
            self._setup_id = setup_id
            self._sut_id = _get_sut_id_for_setup(setup)
            save_last_setup_id(setup_id)

            self._publish_new_setup_event()

        return setup

    async def submit_setup_async(self, setup: Setup, description: str, replace: bool = True) -> Setup | Failure:
        if self._obsid is not None:
            return Failure(
                "An new Setup can not be submitted when an observation is running. "
                "You will need to first send an end_observation request to the configuration manager."
            )

        site = getattr(setup, "site_id", _active_site_id())
        setup_id = await asyncio.to_thread(self.get_next_setup_id_for_site, site)
        filename = _construct_filename(site, setup_id)

        history = getattr(setup, "history", None)
        if not isinstance(history, dict):
            history = {}
            setattr(setup, "history", history)

        history.update({f"{setup_id}": description})
        setup.set_private_attribute("_setup_id", setup_id)
        await asyncio.to_thread(setup.to_yaml_file, self._data_conf_location / filename)

        if get_conf_repo_location():
            try:
                rc = await asyncio.to_thread(_push_setup_to_repo, filename, description)
                if isinstance(rc, Failure):
                    return rc
                await asyncio.to_thread(_add_setup_info_to_cache, setup)
            except Exception as exc:
                return Failure("Submit_setup could not send the new Setup to the repo.", exc)

        if replace:
            self._setup = setup
            self._setup_id = setup_id
            self._sut_id = _get_sut_id_for_setup(setup)
            await asyncio.to_thread(save_last_setup_id, setup_id)
            await asyncio.to_thread(self._publish_new_setup_event)

        return setup

    def get_next_setup_id_for_site(self, site: str) -> int:
        site = site or _active_site_id()
        files = sorted(find_files(pattern=f"SETUP_{site}_*.yaml", root=self._data_conf_location))
        last_file = files[-1]
        _, setup_id = disentangle_filename(last_file.name)
        return int(setup_id) + 1

    def get_status(self) -> dict[str, Any]:
        """Return a compact status snapshot for service-info responses."""
        return {
            "obsid_active": self._obsid is not None,
            "obsid": to_json_safe(self._obsid),
            "setup_id": self._setup_id,
            "sut_id": self._sut_id,
            "storage_connected": self._storage is not None,
        }
