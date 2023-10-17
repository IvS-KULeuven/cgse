import logging

from egse.command import ClientServerCommand
from egse.control import ControlServer
from egse.hexapod.symetrie.zonda import ZondaController
from egse.hexapod.symetrie.zonda import ZondaInterface
from egse.hexapod.symetrie.zonda import ZondaSimulator
from egse.hk import read_conversion_dict, convert_hk_names
from egse.metrics import define_metrics
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.system import format_datetime
from egse.zmq_ser import bind_address

logger = logging.getLogger(__name__)

ctrl_settings = Settings.load("Hexapod ZONDA Control Server")
zonda_settings = Settings.load(filename="zonda.yaml")


class ZondaCommand(ClientServerCommand):
    pass


class ZondaProtocol(CommandProtocol):
    def __init__(self, control_server: ControlServer):
        super().__init__()
        self.control_server = control_server

        self.hk_conversion_table = read_conversion_dict(self.control_server.get_storage_mnemonic(), use_site=True)

        if Settings.simulation_mode():
            self.hexapod = ZondaSimulator()
        else:
            self.hexapod = ZondaController()

        self.hexapod.connect()

        self.load_commands(zonda_settings.Commands, ZondaCommand, ZondaInterface)

        self.build_device_method_lookup_table(self.hexapod)

        self.metrics = define_metrics("ZONDA")

    def get_bind_address(self):
        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_status(self):

        status = super().get_status()

        mach_positions = self.hexapod.get_machine_positions()
        user_positions = self.hexapod.get_user_positions()
        actuator_length = self.hexapod.get_actuator_length()

        status.update({"mach": mach_positions, "user": user_positions, "alength": actuator_length})

        return status

    def get_housekeeping(self) -> dict:

        result = dict()
        result["timestamp"] = format_datetime()

        mach_positions = self.hexapod.get_machine_positions()
        user_positions = self.hexapod.get_user_positions()
        actuator_length = self.hexapod.get_actuator_length()
        actuator_temperature = self.hexapod.get_temperature()

        # TODO If you change these names, please, also change them in egse.fov.fov_hk!
        for idx, key in enumerate(
            ["user_t_x", "user_t_y", "user_t_z", "user_r_x", "user_r_y", "user_r_z"]
        ):
            result[key] = user_positions[idx]

        for idx, key in enumerate(
            ["mach_t_x", "mach_t_y", "mach_t_z", "mach_r_x", "mach_r_y", "mach_r_z"]
        ):
            result[key] = mach_positions[idx]

        for idx, key in enumerate(
            ["alen_t_x", "alen_t_y", "alen_t_z", "alen_r_x", "alen_r_y", "alen_r_z"]
        ):
            result[key] = actuator_length[idx]

        for idx, key in enumerate(
            ["atemp_1", "atemp_2", "atemp_3", "atemp_4", "atemp_5", "atemp_6"]
        ):
            result[key] = actuator_temperature[idx]

        # # TODO:
        # #   the get_general_state() method should be refactored as to return a dict instead of a
        # #   list. Also, we might want to rethink the usefulness of returning the tuple,
        # #   it the first return value ever used?
        #
        # _, _ = self.hexapod.get_general_state()
        #
        result["Homing done"] = self.hexapod.is_homing_done()
        result["In position"] = self.hexapod.is_in_position()

        hk_dict = convert_hk_names(result, self.hk_conversion_table)

        for key, value in hk_dict.items():
            if key != "timestamp":
                self.metrics[key].set(value)

        return hk_dict

    def is_connected(self):
        # FIXME(rik): There must be another way to check if the socket is still alive...
        #             This will send way too many VERSION requests to the controllers.
        #             According to SO [https://stackoverflow.com/a/15175067] the best way
        #             to check for a connection drop / close is to handle the exceptions
        #             properly.... so, no polling for connections by sending it a simple
        #             command.
        return self.hexapod.is_connected()
