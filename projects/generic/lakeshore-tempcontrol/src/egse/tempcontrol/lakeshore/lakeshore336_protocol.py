import logging
from pathlib import Path

from egse.control import ControlServer
from egse.protocol import CommandProtocol
from egse.settings import Settings
from egse.setup import load_setup
from egse.system import format_datetime
from egse.tempcontrol.lakeshore.lakeshore336 import LakeShore336Interface, LakeShore336Simulator, LakeShore336Controller
from egse.tempcontrol.lakeshore.lakeshore336_devif import LakeShore336Command
from egse.zmq_ser import bind_address

logger = logging.getLogger(__name__)
_HERE = Path(__file__).parent
COMMAND_SETTINGS = Settings.load(filename="lakeshore336.yaml", location=_HERE)
CTRL_SETTINGS = Settings.load("LakeShore336 Control Server")
SITE_ID = Settings.load("SITE").ID


class LakeShore336Protocol(CommandProtocol):
    def __init__(self, control_server: ControlServer, device_id: str, simulator: bool = False):
        super().__init__(control_server)
        self.device_id = device_id
        self.simulator = simulator

        setup = load_setup()
        self.input_channels = setup.gse.tempcontrol.lakeshore336[device_id]["input_channels"]
        if isinstance(self.input_channels, str):
            self.input_channels = [self.input_channels]
        self.output_channels = setup.gse.tempcontrol.lakeshore336[device_id]["output_channels"]
        if isinstance(self.output_channels, int):
            self.output_channels = [self.output_channels]

        if self.simulator:
            self.lakeshore: LakeShore336Interface = LakeShore336Simulator(device_id)
        else:
            self.lakeshore: LakeShore336Interface = LakeShore336Controller(device_id)

        self.storage_mnemonic = self.control_server.get_storage_mnemonic()

        self.load_commands(COMMAND_SETTINGS.Commands, LakeShore336Command, LakeShore336Interface)

        self.build_device_method_lookup_table(self.lakeshore)

        # self.synoptics = SynopticsManagerProxy()

    def get_bind_address(self):
        return bind_address(
            self.control_server.get_communication_protocol(),
            self.control_server.get_commanding_port(),
        )

    def get_status(self):
        return super().get_status()

    def get_housekeeping(self) -> dict:
        hk_dict = dict()

        try:
            # Temperature sensors (input)

            for input_channel in self.input_channels:
                hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_T_{input_channel}"] = self.lakeshore.get_temperature(
                    input_channel=input_channel
                )

            # Heaters (output)

            # for output_channel in self.output_channels:
            for output_channel in self.output_channels:  # list(set(self.output_channels) & {1, 2}):
                if output_channel in {1, 2}:
                    pid_parameters = self.lakeshore.get_pid_parameters(output_channel)
                    hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_P_{output_channel}"] = pid_parameters[0]
                    hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_I_{output_channel}"] = pid_parameters[1]
                    hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_D_{output_channel}"] = pid_parameters[2]

                    hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_HEATER_{output_channel}"] = (
                        self.lakeshore.get_heater_output(output_channel)
                    )

                hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_SETPOINT_{output_channel}"] = (
                    self.lakeshore.get_temperature_setpoint(output_channel)
                )

            # hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_TEMP_A"] = self.lakeshore.get_temperature()
            # pid_params = self.lakeshore.get_pid_parameters(1)
            # hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_P_VALUE"] = pid_params[0]
            # hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_I_VALUE"] = pid_params[1]
            # hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_D_VALUE"] = pid_params[2]
            # hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_HEATER_VALUE"] = self.lakeshore.get_heater_output(
            #     output_channel=1)
            # hk_dict[f"G{SITE_ID}_{self.storage_mnemonic}_SETPOINT_VALUE"] = self.lakeshore.get_temperature_setpoint(
            #     output_channel=1)

            # for hk_name in metrics_dict.keys():
            #     index_lsci = hk_name.split("_")
            #     if (len(index_lsci) > 2):
            #         if int(index_lsci[2]) == int(self.device_id):
            #             metrics_dict[hk_name].set(hk_dict[hk_name])

            # # Send the HK acquired so far to the Synoptics Manager
            # self.synoptics.store_th_synoptics(hk_dict)
        except Exception as exc:
            logger.warning(f"failed to get HK ({exc})")
        hk_dict["timestamp"] = format_datetime()

        return hk_dict

    def quit(self):
        self.lakeshore.quit()
