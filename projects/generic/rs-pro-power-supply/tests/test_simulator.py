from egse.power_supply.rs_pro import OperatingMode
from egse.power_supply.rs_pro.rsd3305p import Rsd3305pSimulator


def test_set_current():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    # No current set

    assert rsd3305p_sim.get_current_config(1) == 0.0
    assert rsd3305p_sim.get_current_config(2) == 0.0

    assert rsd3305p_sim.get_current_config(1) == 0.0
    assert rsd3305p_sim.get_current_config(2) == 0.0

    rsd3305p_sim.set_current(1, 2.225)
    assert rsd3305p_sim.get_current_config(1) == 2.225
    assert rsd3305p_sim.get_current_config(2) == 0.0

    rsd3305p_sim.set_current(1, 0)
    rsd3305p_sim.set_current(2, 2.225)
    assert rsd3305p_sim.get_current_config(1) == 0.0
    assert rsd3305p_sim.get_current_config(2) == 2.225


def test_set_voltage():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    # No voltage set

    assert rsd3305p_sim.get_voltage_config(1) == 0.0
    assert rsd3305p_sim.get_voltage_config(2) == 0.0

    assert rsd3305p_sim.get_voltage_config(1) == 0.0
    assert rsd3305p_sim.get_voltage_config(2) == 0.0

    rsd3305p_sim.set_voltage(1, 20.50)
    assert rsd3305p_sim.get_voltage_config(1) == 20.50
    assert rsd3305p_sim.get_voltage_config(2) == 0.0

    rsd3305p_sim.set_voltage(1, 0)
    rsd3305p_sim.set_voltage(2, 20.50)
    assert rsd3305p_sim.get_voltage_config(1) == 0.0
    assert rsd3305p_sim.get_voltage_config(2) == 20.50


def test_get_current():
    # TODO
    pass


def test_get_voltage():
    # TODO
    pass


def test_select_operating_mode():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    assert rsd3305p_sim.operating_mode == OperatingMode.INDEPENDENT

    for operating_mode in OperatingMode:
        rsd3305p_sim.select_operating_mode(operating_mode)
        assert rsd3305p_sim.operating_mode == operating_mode


def test_get_status():
    # TODO
    pass


def test_get_id():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    manufacturer, model, sw_version = rsd3305p_sim.get_id()

    assert manufacturer == "RS-D3305P"
    assert model.startswith("V")
    assert sw_version.startswith("SN:")


def test_enable_output():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    rsd3305p_sim.set_current(1, 2.225)
    rsd3305p_sim.set_voltage(1, 5.0)
    assert rsd3305p_sim.get_current_config(1) == 2.225
    assert rsd3305p_sim.get_current(1) == 0.0
    assert rsd3305p_sim.get_voltage_config(1) == 5.0
    assert 5 - 0.2 <= rsd3305p_sim.get_voltage(1) <= 5.0 + 0.2
    rsd3305p_sim.enable_output(1)
    assert 2.225 - 0.2 <= rsd3305p_sim.get_current(1) <= 2.225 + 0.2
    assert rsd3305p_sim.get_voltage_config(1) == 5.0
    assert 5 - 0.2 <= rsd3305p_sim.get_voltage(1) <= 5.0 + 0.2
    rsd3305p_sim.disable_output(1)
    assert rsd3305p_sim.get_current(1) == 0.0
    assert rsd3305p_sim.get_voltage_config(1) == 5.0
    assert 5 - 0.2 <= rsd3305p_sim.get_voltage(1) <= 5.0 + 0.2


def test_ip_address():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    assert rsd3305p_sim.get_ip_address() == "192.168.1.199"

    rsd3305p_sim.set_ip_address("192.168.1.200")
    assert rsd3305p_sim.get_ip_address() == "192.168.1.200"


def subnet_mask():
    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    assert rsd3305p_sim.get_subnet_mask() == "255.255.255.0"

    rsd3305p_sim.set_subnet_mask("255.255.255.1")
    assert rsd3305p_sim.get_subnet_mask() == "255.255.255.1"


def test_get_mac_address():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    assert rsd3305p_sim.get_mac_address() == "93-47-df-48-48-48"


def test_port():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    assert rsd3305p_sim.get_port() == 6325

    rsd3305p_sim.set_port(18190)
    assert rsd3305p_sim.get_port() == 18190


def test_baudrate():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    assert rsd3305p_sim.get_baudrate() == 9600

    rsd3305p_sim.set_baudrate(19200)
    assert rsd3305p_sim.get_baudrate() == 19200


def test_get_device_info():

    rsd3305p_sim = Rsd3305pSimulator("RSD1")

    device_info = rsd3305p_sim.get_device_info()

    assert device_info["DHCP"] == int(rsd3305p_sim.dhcp)
    assert device_info["IP"] == rsd3305p_sim.get_ip_address()
    assert device_info["NETMASK"] == rsd3305p_sim.get_subnet_mask()
    assert device_info["GW"] == rsd3305p_sim.get_gateway()
    assert device_info["PORT"] == rsd3305p_sim.get_port()
    assert device_info["BAUDRATE"] == rsd3305p_sim.get_baudrate()
