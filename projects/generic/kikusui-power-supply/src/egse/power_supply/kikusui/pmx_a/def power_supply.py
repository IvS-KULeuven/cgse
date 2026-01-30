from egse.power_supply.kikusui.pmx import IntSwitch
from egse.power_supply.kikusui.pmx_a.pmx_a import PmxAInterface
from egse.setup import load_setup


def power_supply_switch_on(device_ids: None | str | tuple[str, ...]):
    setup = load_setup()


def pmx_a_switch_on(device_id: str):
    setup = load_setup()

    psu: PmxAInterface = setup.gse.power_supply.pmx_a[device_id].device
    calibration = setup.gse.power_supply.pmx_a[device_id]

    psu.set_current(calibration.current)
    psu.set_ocp(calibration.ocp)

    psu.set_voltage(calibration.voltage)
    psu.set_ovp(calibration.ovp)

    psu.set_priority_mode(calibration.priority_mode)

    psu.set_output_status(IntSwitch.ON)


def pmx_a_switch_off(device_id: str):
    setup = load_setup()

    psu: PmxAInterface = setup.gse.power_supply.pmx_a[device_id].device

    psu.set_output_status(IntSwitch.OFF)
