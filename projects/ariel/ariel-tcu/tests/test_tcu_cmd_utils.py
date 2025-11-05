from egse.ariel.tcu.tcu_cmd_utils import create_crc16


def test_create_crc16():
    cmd_string = " 0340 0001 0004 0000 0000 0000 0000"
    expected_crc = "3998"

    assert create_crc16(cmd_string) == expected_crc
