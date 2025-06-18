from pathlib import Path

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.device import DeviceConnectionState
from egse.hexapod.symetrie import ControllerFactory
from egse.hexapod.symetrie import get_hexapod_controller_pars
from egse.hexapod.symetrie import logger
from egse.hexapod.symetrie.puna import PunaInterface
from egse.hexapod.symetrie.puna import PunaSimulator

# from egse.hk import read_conversion_dict, convert_hk_names
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

_HERE = Path(__file__).parent

DEVICE_SETTINGS = Settings.load(filename="puna.yaml", location=_HERE)


class PunaCommand(ClientServerCommand):
    pass


class PunaProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer, device_id: str, simulator: bool = False):
        super().__init__(control_server)
        self.simulator = simulator
        self.device_id = device_id

        # FIXME: HK needs to be working
        # self.hk_conversion_table = read_conversion_dict(self.control_server.get_storage_mnemonic(), use_site=True)

        if self.simulator:
            self.hexapod = PunaSimulator()
        else:
            *_, device_type, controller_type = get_hexapod_controller_pars(device_id)

            factory = ControllerFactory()
            self.hexapod = factory.create(device_type, device_id=device_id)
            self.hexapod.add_observer(self)

        try:
            self.hexapod.connect()
        except ConnectionError:
            logger.warning("Couldn't establish a connection to the PUNA Hexapod, check the log messages.")

        self.load_commands(DEVICE_SETTINGS.Commands, PunaCommand, PunaInterface)
        self.build_device_method_lookup_table(self.hexapod)

        # self.metrics = define_metrics("PUNA")

    def get_bind_address(self):
        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_device(self):
        return self.hexapod

    def get_status(self):
        status = super().get_status()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return status

        mach_positions = self.hexapod.get_machine_positions()
        user_positions = self.hexapod.get_user_positions()
        actuator_length = self.hexapod.get_actuator_length()

        status.update({"mach": mach_positions, "user": user_positions, "alength": actuator_length})

        return status

    def get_housekeeping(self) -> dict:
        result = dict()
        result["timestamp"] = format_datetime()

        if self.state == DeviceConnectionState.DEVICE_NOT_CONNECTED and not self.simulator:
            return result

        mach_positions = self.hexapod.get_machine_positions()
        user_positions = self.hexapod.get_user_positions()
        actuator_length = self.hexapod.get_actuator_length()

        # The result of the previous calls might be None when e.g. the connection
        # to the device gets lost.

        if mach_positions is None or user_positions is None or actuator_length is None:
            if not self.hexapod.is_connected():
                logger.warning("Hexapod PUNA disconnected.")
                self.update_connection_state(DeviceConnectionState.DEVICE_NOT_CONNECTED)
            return result

        for idx, key in enumerate(["user_t_x", "user_t_y", "user_t_z", "user_r_x", "user_r_y", "user_r_z"]):
            result[key] = user_positions[idx]

        for idx, key in enumerate(["mach_t_x", "mach_t_y", "mach_t_z", "mach_r_x", "mach_r_y", "mach_r_z"]):
            result[key] = mach_positions[idx]

        for idx, key in enumerate(["alen_t_x", "alen_t_y", "alen_t_z", "alen_r_x", "alen_r_y", "alen_r_z"]):
            result[key] = actuator_length[idx]

        # TODO:
        #   the get_general_state() method should be refactored as to return a dict instead of a
        #   list. Also, we might want to rethink the usefulness of returning the tuple,
        #   it the first return value ever used?

        _, _ = self.hexapod.get_general_state()

        result["Homing done"] = self.hexapod.is_homing_done()
        result["In position"] = self.hexapod.is_in_position()

        return result  # convert_hk_names(result, self.hk_conversion_table)

    def is_device_connected(self):
        # FIXME(rik): There must be another way to check if the socket is still alive...
        #             This will send way too many VERSION requests to the controllers.
        #             According to SO [https://stackoverflow.com/a/15175067] the best way
        #             to check for a connection drop / close is to handle the exceptions
        #             properly.... so, no polling for connections by sending it a simple
        #             command.
        return self.hexapod.is_connected()
