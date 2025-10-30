import random

from egse.ariel.tcu import TcuMode
from egse.ariel.tcu.tcu import TcuInterface
from egse.ariel.tcu.tcu_cmd_utils import (
    CommandAddress,
    GeneralCommandIdentifier,
    TSMCommandIdentifier,
    TCU_LOGICAL_ADDRESS,
    DATA_LENGTH,
    format_value,
    PacketType,
    M2MDCommandIdentifier,
    HKCommandIdentifier,
)
import logging

from egse.device import DeviceTransport
from egse.mixin import DynamicCommandMixin

LOGGER = logging.getLogger("egse.ariel.tcu.tcu")

EXPECTED_TRANSACTION_ID = -1

###############################
# Test building command strings
###############################


class TcuTestInterface(DeviceTransport):
    """Dummy device transport for testing."""

    def trans(self, command: str) -> bytes:
        """Returns the given command string as bytes.

        This is used to test whether the command string is built correctly (and the transaction identifier is
        incremented for each command call).

        Args:
            command (str): Command string to encode.

        Returns:
            Encoded command string.
        """

        global EXPECTED_TRANSACTION_ID
        EXPECTED_TRANSACTION_ID += 1

        return command.encode()


class TcuTest(TcuInterface, DynamicCommandMixin):
    """Dummy TCU interface for testing."""

    def __init__(self):
        super().__init__()
        self.transport = self.tcu = TcuTestInterface()


TCU_TEST = TcuTest()


TRANSACTION_ID_OFFSET = 5
DATA_LENGTH_OFFSET = 10
ADDRESS_OFFSET = 15
CMD_ID_OFFSET = 20
CARGO1_OFFSET = 25
CARGO2_OFFSET = 30


def is_tcu_read_cmd(cmd_string: str) -> bool:
    """Checks whether the given command is a TCU read command.

    Args:
        cmd_string (str): Command string to check.

    Returns:
        True of the given command is a TCU read command; False otherwise.
    """

    expected_prefix = f"{TCU_LOGICAL_ADDRESS}{PacketType.READ.value}"
    return cmd_string.startswith(expected_prefix)


def is_tcu_write_cmd(cmd_string: str) -> bool:
    """Checks whether the given command is a TCU write command.

    Args:
        cmd_string (str): Command string to check.

    Returns:
        True of the given command is a TCU write command; False otherwise.
    """

    expected_prefix = f"{TCU_LOGICAL_ADDRESS}{PacketType.WRITE.value}"
    return cmd_string.startswith(expected_prefix)


def get_transaction_id(cmd_string: str) -> str:
    """Extracts the transaction identifier from the given TCU command string.

    Args:
        cmd_string (str): Command string to extract the transaction identifier from.

    Returns:
        Transaction identifier.
    """

    transaction_id_hex_str = cmd_string[TRANSACTION_ID_OFFSET : TRANSACTION_ID_OFFSET + 4]

    return transaction_id_hex_str


def get_data_length(cmd_string: str) -> str:
    """Extracts the data length from the given TCU command string.

    Args:
        cmd_string (str): Command string to extract the data length from.

    Returns:
        Data length.
    """

    return cmd_string[DATA_LENGTH_OFFSET : DATA_LENGTH_OFFSET + 4]


def get_address(cmd_string: str) -> str:
    """Extracts the command address from the given TCU command string.

    Args:
        cmd_string (str): Command string to extract the command address from.

    Returns:
        Command address.
    """

    return cmd_string[ADDRESS_OFFSET : ADDRESS_OFFSET + 4]


def get_cmd_id(cmd_string: str) -> str:
    """Extracts the command identifier from the given TCU command string.

    Args:
        cmd_string (str): Command string to extract the command identifier from.

    Returns:
        Command identifier.
    """

    return cmd_string[CMD_ID_OFFSET : CMD_ID_OFFSET + 4]


def get_cargo1(cmd_string: str) -> str:
    """Extracts the cargo1 argument from the given TCU command string.

    Args:
        cmd_string (str): Command string to extract the cargo1 argument from.

    Returns:
        Cargo1 argument from the given TCU command string.
    """

    return cmd_string[CARGO1_OFFSET : CARGO1_OFFSET + 4]


def get_cargo2(cmd_string: str) -> str:
    """Extracts the cargo2 argument from the given TCU command string.

    Args:
        cmd_string (str): Command string to extract the cargo2 argument from.

    Returns:
        Cargo2 argument from the given TCU command string.
    """

    return cmd_string[CARGO2_OFFSET : CARGO2_OFFSET + 4]


def get_random_hex(strip_off_0x: bool = True) -> str:
    """Generates a random hex string of maximum length 4, without leading "0x".

    Args:
        strip_off_0x (bool): Whether to strip off leading "0x".

    Returns:
        Random hex string of maximum length 4, without leading "0x".
    """

    random_hex = f"0x{random.getrandbits(16):X}"

    return random_hex[2:] if strip_off_0x else random_hex


def hex_to_int(hex_value: str) -> int:
    """Converts a hex string to an integer.

    Args:
        hex_value (str): Hex string to convert.

    Returns:
        Given hex string as an integer
    """

    if hex_value.startswith("0x"):
        hex_value = hex_value[2:]  # Strip off leading "0x"

    return int(hex_value.zfill(4), 16)


def get_expected_transaction_id_as_hex() -> str:
    """Returns the expected transaction identifier.

    The leading "0x" is stripped off and the transaction identifier is padded with leading zeros to ensure it is
    always 4 characters long.

    Returns:
        Expected transaction identifier.
    """

    return f"{EXPECTED_TRANSACTION_ID:X}".zfill(4)


def test_tcu_firmware_id():
    cmd_string = TCU_TEST.tcu_firmware_id().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_FIRMWARE_ID.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0000 0000 0000 0000")


def test_get_tcu_mode():
    cmd_string = TCU_TEST.get_tcu_mode().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_MODE.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0000 0001 0000 0000")


def test_set_tcu_mode():
    for tcu_mode in TcuMode:
        cmd_string = TCU_TEST.set_tcu_mode(tcu_mode=tcu_mode).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == CommandAddress.GENERAL.value
        assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_MODE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(tcu_mode)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0001 0000 {format_value(tcu_mode)}"
        )

    for tcu_mode in TcuMode:
        cmd_string = TCU_TEST.set_tcu_mode(tcu_mode=tcu_mode.value).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == CommandAddress.GENERAL.value
        assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_MODE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(tcu_mode)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0001 0000 {format_value(tcu_mode)}"
        )


def test_tcu_status():
    cmd_string = TCU_TEST.tcu_status().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_STATUS.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0000 0002 0000 0000")


def test_tcu_simulated():
    simulated = get_random_hex()
    cmd_string = TCU_TEST.tcu_simulated(cargo2=simulated).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_SIMULATED.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(simulated)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0003 0000 {format_value(simulated)}"
    )

    simulated = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.tcu_simulated(cargo2=simulated).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_SIMULATED.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(simulated)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0003 0000 {format_value(simulated)}"
    )

    simulated = get_random_hex(False)
    cmd_string = TCU_TEST.tcu_simulated(cargo2=simulated).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.TCU_SIMULATED.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(simulated)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0003 0000 {format_value(simulated)}"
    )


def test_restart_links_period_latch():
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.restart_links_period_latch(cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.RESTART_LINKS_PERIOD_LATCH.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0004 0000 {format_value(cargo2)}"
    )

    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.restart_links_period_latch(cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.RESTART_LINKS_PERIOD_LATCH.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0004 0000 {format_value(cargo2)}"
    )

    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.restart_links_period_latch(cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.RESTART_LINKS_PERIOD_LATCH.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0004 0000 {format_value(cargo2)}"
    )


def test_get_restart_links_period():
    cmd_string = TCU_TEST.get_restart_links_period().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.RESTART_LINKS_PERIOD.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0000 0005 0000 0000")


def test_set_restart_links_period():
    link_period = get_random_hex()
    cmd_string = TCU_TEST.set_restart_links_period(link_period=link_period).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.RESTART_LINKS_PERIOD.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(link_period)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0005 0000 {format_value(link_period)}"
    )

    link_period = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.set_restart_links_period(link_period=link_period).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.RESTART_LINKS_PERIOD.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(link_period)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0005 0000 {format_value(link_period)}"
    )

    link_period = get_random_hex(False)
    cmd_string = TCU_TEST.set_restart_links_period(link_period=link_period).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.GENERAL.value
    assert get_cmd_id(cmd_string) == GeneralCommandIdentifier.RESTART_LINKS_PERIOD.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == format_value(link_period)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0000 0005 0000 {format_value(link_period)}"
    )


# noinspection PyTypeChecker
def test_ope_mng_command_func():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_command(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_COMMAND.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0000 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.ope_mng_command(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_COMMAND.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0000 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.ope_mng_command(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_COMMAND.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0000 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value

        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_command(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_COMMAND.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.ope_mng_command(axis=axis, cargo2=cargo2).decode()

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0000 0000 {format_value(cargo2)}"
        )

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_COMMAND.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0000 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.ope_mng_command(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_COMMAND.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0000 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_ope_mng_event_clear_protect_flag():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_event_clear_protect_flag(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0001 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.ope_mng_event_clear_protect_flag(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0001 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.ope_mng_event_clear_protect_flag(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0001 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_event_clear_protect_flag(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0001 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.ope_mng_event_clear_protect_flag(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0001 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.ope_mng_event_clear_protect_flag(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR_PROTECT_FLAG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0001 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_ope_mng_event_clear():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_event_clear(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0002 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.ope_mng_event_clear(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0002 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.ope_mng_event_clear(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0002 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_event_clear(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0002 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.ope_mng_event_clear(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0002 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.ope_mng_event_clear(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_CLEAR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 0002 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_ope_mng_status():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        # cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_status(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_STATUS.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0003 0000 0000")

        # cargo2 = hex_to_int(get_random_hex())
        # cmd_string = TCU_TEST.ope_mng_status(axis=axis, cargo2=cargo2).decode()
        #
        # assert is_tcu_read_cmd(cmd_string)
        # assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        # assert get_data_length(cmd_string) == str(DATA_LENGTH)
        # assert get_address(cmd_string) == format_value(axis)
        # assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_STATUS.value
        # assert get_cargo1(cmd_string) == "0000"
        # assert get_cargo2(cmd_string) == format_value(cargo2)
        #
        # assert cmd_string.startswith(
        #     f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0003 0000 {format_value(cargo2)}"
        # )
        #
        # cargo2 = get_random_hex(False)
        # cmd_string = TCU_TEST.ope_mng_status(axis=axis, cargo2=cargo2).decode()
        #
        # assert is_tcu_read_cmd(cmd_string)
        # assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        # assert get_data_length(cmd_string) == str(DATA_LENGTH)
        # assert get_address(cmd_string) == format_value(axis)
        # assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_STATUS.value
        # assert get_cargo1(cmd_string) == "0000"
        # assert get_cargo2(cmd_string) == format_value(cargo2)
        #
        # assert cmd_string.startswith(
        #     f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0003 0000 {format_value(cargo2)}"
        # )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        # cargo2 = get_random_hex()
        cmd_string = TCU_TEST.ope_mng_status(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_STATUS.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 0003 0000 0000")

        # cargo2 = hex_to_int(get_random_hex())
        # cmd_string = TCU_TEST.ope_mng_status(axis=axis, cargo2=cargo2).decode()
        #
        # assert is_tcu_read_cmd(cmd_string)
        # assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        # assert get_data_length(cmd_string) == str(DATA_LENGTH)
        # assert get_address(cmd_string) == format_value(axis)
        # assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_STATUS.value
        # assert get_cargo1(cmd_string) == "0000"
        # assert get_cargo2(cmd_string) == format_value(cargo2)
        #
        # assert cmd_string.startswith(
        #     f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 0003 0000 {format_value(cargo2)}"
        # )
        #
        # cargo2 = get_random_hex(False)
        # cmd_string = TCU_TEST.ope_mng_status(axis=axis, cargo2=cargo2).decode()
        #
        # assert is_tcu_read_cmd(cmd_string)
        # assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        # assert get_data_length(cmd_string) == str(DATA_LENGTH)
        # assert get_address(cmd_string) == format_value(axis)
        # assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_STATUS.value
        # assert get_cargo1(cmd_string) == "0000"
        # assert get_cargo2(cmd_string) == format_value(cargo2)
        #
        # assert cmd_string.startswith(
        #     f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 0003 0000 {format_value(cargo2)}"
        # )


# noinspection PyTypeChecker
def test_ope_mng_event_reg():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.ope_mng_event_reg(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_REG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 0004 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.ope_mng_event_reg(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.OPE_MNG_EVENT_REG.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 0004 0000 0000")


# noinspection PyTypeChecker
def test_get_acq_curr_off_corr():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.get_acq_curr_off_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1000 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.get_acq_curr_off_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 1000 0000 0000")


# noinspection PyTypeChecker
def test_set_acq_curr_off_corr():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_acq_curr_off_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1000 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_acq_curr_off_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1000 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_acq_curr_off_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1000 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_acq_curr_off_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1000 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_acq_curr_off_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1000 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_acq_curr_off_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_OFF_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1000 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_get_acq_curr_gain_corr():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.get_acq_curr_gain_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1001 0000 0000")

        cmd_string = TCU_TEST.get_acq_curr_gain_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1001 0000 0000")

        cmd_string = TCU_TEST.get_acq_curr_gain_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1001 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.get_acq_curr_gain_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 1001 0000 0000")

        cmd_string = TCU_TEST.get_acq_curr_gain_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 1001 0000 0000")

        cmd_string = TCU_TEST.get_acq_curr_gain_corr(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 1001 0000 0000")


# noinspection PyTypeChecker
def test_set_acq_curr_gain_corr():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_acq_curr_gain_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1001 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_acq_curr_gain_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1001 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_acq_curr_gain_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1001 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_acq_curr_gain_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_acq_curr_gain_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_acq_curr_gain_corr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_CURR_GAIN_CORR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)


# noinspection PyTypeChecker
def test_acq_axis_a_curr_read():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.acq_axis_a_curr_read(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AXIS_A_CURR_READ.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1002 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.acq_axis_a_curr_read(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AXIS_A_CURR_READ.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 1002 0000 0000")


# noinspection PyTypeChecker
def test_acq_axis_b_curr_read():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.acq_axis_b_curr_read(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AXIS_B_CURR_READ.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1003 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.acq_axis_b_curr_read(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AXIS_B_CURR_READ.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 1003 0000 0000")


# noinspection PyTypeChecker
def test_acq_ave_lpf_en():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_ave_lpf_en(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVE_LPF_EN.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1004 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_ave_lpf_en(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVE_LPF_EN.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1004 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_ave_lpf_en(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVE_LPF_EN.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1004 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_ave_lpf_en(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVE_LPF_EN.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1004 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_ave_lpf_en(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVE_LPF_EN.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1004 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_ave_lpf_en(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVE_LPF_EN.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1004 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_acq_ovc_cfg_filter():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_ovc_cfg_filter(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1005 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_ovc_cfg_filter(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1005 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_ovc_cfg_filter(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1005 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_ovc_cfg_filter(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1005 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_ovc_cfg_filter(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1005 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_ovc_cfg_filter(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_OVC_CFG_FILTER.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1005 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
# noinspection SpellCheckingInspection
def test_acq_avc_filt_time():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_avc_filt_time(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVC_FILT_TIME.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1006 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_avc_filt_time(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVC_FILT_TIME.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1006 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_avc_filt_time(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVC_FILT_TIME.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1006 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_avc_filt_time(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVC_FILT_TIME.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1006 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_avc_filt_time(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVC_FILT_TIME.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1006 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_avc_filt_time(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVC_FILT_TIME.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1006 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_acq_average_type():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_average_type(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVERAGE_TYPE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1007 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_average_type(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVERAGE_TYPE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1007 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_average_type(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVERAGE_TYPE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1007 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_average_type(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVERAGE_TYPE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1007 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_average_type(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVERAGE_TYPE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1007 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_average_type(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_AVERAGE_TYPE.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1007 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
# noinspection SpellCheckingInspection
def test_acq_spk_filt_counter_lim():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_spk_filt_counter_lim(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1008 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_spk_filt_counter_lim(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1008 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_spk_filt_counter_lim(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1008 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_spk_filt_counter_lim(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1008 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_spk_filt_counter_lim(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1008 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_spk_filt_counter_lim(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_COUNTER_LIM.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1008 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
# noinspection SpellCheckingInspection
def test_acq_spk_filt_incr_thr():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_spk_filt_incr_thr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1009 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_spk_filt_incr_thr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1009 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_spk_filt_incr_thr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 1009 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.acq_spk_filt_incr_thr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1009 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.acq_spk_filt_incr_thr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1009 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.acq_spk_filt_incr_thr(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.ACQ_SPK_FILT_INCR_THR.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 1009 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_get_prof_gen_axis_step():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.get_prof_gen_axis_step(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2000 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.get_prof_gen_axis_step(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 2000 0000 0000")


# noinspection PyTypeChecker
def test_set_prof_gen_axis_step():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_prof_gen_axis_step(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2000 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_prof_gen_axis_step(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2000 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_prof_gen_axis_step(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2000 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_prof_gen_axis_step(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2000 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_prof_gen_axis_step(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2000 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_prof_gen_axis_step(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STEP.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2000 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_get_prof_gen_axis_speed():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.get_prof_gen_axis_speed(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2001 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.get_prof_gen_axis_speed(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 2001 0000 0000")


# noinspection PyTypeChecker
def test_set_prof_gen_axis_speed():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_prof_gen_axis_speed(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2001 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_prof_gen_axis_speed(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2001 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_prof_gen_axis_speed(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2001 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_prof_gen_axis_speed(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2001 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_prof_gen_axis_speed(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2001 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_prof_gen_axis_speed(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_SPEED.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2001 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_get_prof_gen_axis_state_start():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cmd_string = TCU_TEST.get_prof_gen_axis_state_start(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2002 0000 0000")

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cmd_string = TCU_TEST.get_prof_gen_axis_state_start(axis=axis).decode()

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 2002 0000 0000")


# noinspection PyTypeChecker
def test_set_prof_gen_axis_state_start():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_prof_gen_axis_state_start(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2002 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_prof_gen_axis_state_start(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2002 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_prof_gen_axis_state_start(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 2002 0000 {format_value(cargo2)}"
        )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        cargo2 = get_random_hex()
        cmd_string = TCU_TEST.set_prof_gen_axis_state_start(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2002 0000 {format_value(cargo2)}"
        )

        cargo2 = hex_to_int(get_random_hex())
        cmd_string = TCU_TEST.set_prof_gen_axis_state_start(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2002 0000 {format_value(cargo2)}"
        )

        cargo2 = get_random_hex(False)
        cmd_string = TCU_TEST.set_prof_gen_axis_state_start(axis=axis, cargo2=cargo2).decode()

        assert is_tcu_write_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == format_value(axis)
        assert get_cmd_id(cmd_string) == M2MDCommandIdentifier.PROF_GEN_AXIS_STATE_START.value
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == format_value(cargo2)

        assert cmd_string.startswith(
            f"0320 {get_expected_transaction_id_as_hex()} 0004 {axis} 2002 0000 {format_value(cargo2)}"
        )


# noinspection PyTypeChecker
def test_sw_rs_xx_sw_rise():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        for position in range(1, 21):
            expected_cmd_id = f"{M2MDCommandIdentifier.SW_RS_XX_SW_RISE.value[:2]}{hex(position)[2:].zfill(2)}"
            cmd_string = TCU_TEST.sw_rs_xx_sw_rise(axis=axis, position=position).decode()

            assert is_tcu_read_cmd(cmd_string)
            assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
            assert get_data_length(cmd_string) == str(DATA_LENGTH)
            assert get_address(cmd_string) == format_value(axis)
            assert get_cmd_id(cmd_string) == expected_cmd_id
            assert get_cargo1(cmd_string) == "0000"
            assert get_cargo2(cmd_string) == "0000"

            assert cmd_string.startswith(
                f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 30{hex(position)[2:].zfill(2)} 0000 0000"
            )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value

        for position in range(1, 21):
            expected_cmd_id = f"{M2MDCommandIdentifier.SW_RS_XX_SW_RISE.value[:2]}{hex(position)[2:].zfill(2)}"

            cmd_string = TCU_TEST.sw_rs_xx_sw_rise(axis=axis, position=position).decode()

            assert is_tcu_read_cmd(cmd_string)
            assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
            assert get_data_length(cmd_string) == str(DATA_LENGTH)
            assert get_address(cmd_string) == format_value(axis)
            assert get_cmd_id(cmd_string) == expected_cmd_id
            assert get_cargo1(cmd_string) == "0000"
            assert get_cargo2(cmd_string) == "0000"

            assert cmd_string.startswith(
                f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 30{hex(position)[2:].zfill(2)} 0000 0000"
            )


# noinspection PyTypeChecker
def test_sw_rs_xx_sw_fall():
    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        offset = 21
        for position in range(1, 21):
            expected_cmd_id = f"{M2MDCommandIdentifier.SW_RS_XX_SW_FALL.value[:2]}{hex(position + offset)[2:].zfill(2)}"
            cmd_string = TCU_TEST.sw_rs_xx_sw_fall(axis=axis, position=position).decode()

            assert is_tcu_read_cmd(cmd_string)
            assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
            assert get_data_length(cmd_string) == str(DATA_LENGTH)
            assert get_address(cmd_string) == format_value(axis)
            assert get_cmd_id(cmd_string) == expected_cmd_id
            assert get_cargo1(cmd_string) == "0000"
            assert get_cargo2(cmd_string) == "0000"

            assert cmd_string.startswith(
                f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis.value} 30{hex(position + offset)[2:].zfill(2)} 0000 0000"
            )

    for axis in [CommandAddress.M2MD_1, CommandAddress.M2MD_2, CommandAddress.M2MD_3]:
        axis = axis.value
        offset = 21
        for position in range(1, 21):
            expected_cmd_id = f"{M2MDCommandIdentifier.SW_RS_XX_SW_FALL.value[:2]}{hex(position + offset)[2:].zfill(2)}"
            cmd_string = TCU_TEST.sw_rs_xx_sw_fall(axis=axis, position=position).decode()

            assert is_tcu_read_cmd(cmd_string)
            assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
            assert get_data_length(cmd_string) == str(DATA_LENGTH)
            assert get_address(cmd_string) == format_value(axis)
            assert get_cmd_id(cmd_string) == expected_cmd_id
            assert get_cargo1(cmd_string) == "0000"
            assert get_cargo2(cmd_string) == "0000"

            assert cmd_string.startswith(
                f"0340 {get_expected_transaction_id_as_hex()} 0004 {axis} 30{hex(position + offset)[2:].zfill(2)} 0000 0000"
            )


def test_tsm_latch():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.tsm_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 0000 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.tsm_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 0000 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.tsm_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 0000 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_get_tsm_current_value():
    cmd_string = TCU_TEST.get_tsm_current_value().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_VALUE.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 0001 0000 0000")


def test_set_tsm_current_value():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.set_tsm_current_value(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_VALUE.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 0001 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.set_tsm_current_value(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_VALUE.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 0001 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.set_tsm_current_value(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_VALUE.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 0001 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_get_tsm_current_offset():
    cmd_string = TCU_TEST.get_tsm_current_offset().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_OFFSET.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 0002 0000 0000")


def test_set_tsm_current_offset():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.set_tsm_current_offset(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_OFFSET.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 0002 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.set_tsm_current_offset(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_OFFSET.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.set_tsm_current_offset(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_CURRENT_OFFSET.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)


def test_tsm_adc_register_latch():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.tsm_adc_register_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_REGISTER_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1000 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.tsm_adc_register_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_REGISTER_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1000 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.tsm_adc_register_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_REGISTER_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1000 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_tsm_adc_id_register():
    cmd_string = TCU_TEST.tsm_adc_id_register().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_ID_REGISTER.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 1001 0000 0000")


def test_tsm_adc_configuration_register():
    cmd_string = TCU_TEST.tsm_adc_configuration_register().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_CONFIGURATION_REGISTER.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 1002 0000 0000")


def test_get_tsm_adc_hpf_register():
    cmd_string = TCU_TEST.get_tsm_adc_hpf_register().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_HPF_REGISTER.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 1003 0000 0000")


def test_set_tsm_adc_hpf_register():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.set_tsm_adc_hpf_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_HPF_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1003 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.set_tsm_adc_hpf_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_HPF_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1003 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.set_tsm_adc_hpf_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_HPF_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1003 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_get_tsm_adc_ofc_register():
    cmd_string = TCU_TEST.get_tsm_adc_ofc_register().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_OFC_REGISTER.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 1004 0000 0000")


def test_set_tsm_adc_ofc_register():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.set_tsm_adc_ofc_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_OFC_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1004 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.set_tsm_adc_ofc_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_OFC_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1004 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.set_tsm_adc_ofc_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_OFC_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1004 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_get_tsm_adc_fsc_register():
    cmd_string = TCU_TEST.get_tsm_adc_fsc_register().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_FSC_REGISTER.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 1006 0000 0000")


def test_set_tsm_adc_fsc_register():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.set_tsm_adc_fsc_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_FSC_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1006 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.set_tsm_adc_fsc_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_FSC_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1006 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.set_tsm_adc_fsc_register(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_FSC_REGISTER.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1006 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_tsm_adc_command_latch():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.tsm_adc_command_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_COMMAND_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1008 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.tsm_adc_command_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_COMMAND_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1008 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.tsm_adc_command_latch(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_COMMAND_LATCH.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1008 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_tsm_adc_command():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.tsm_adc_command(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_COMMAND.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1009 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.tsm_adc_command(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_COMMAND.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1009 {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.tsm_adc_command(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_COMMAND.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 1009 {format_value(cargo1)} {format_value(cargo2)}"
    )


def test_tsm_adc_calibration():
    cargo1 = get_random_hex()
    cargo2 = get_random_hex()
    cmd_string = TCU_TEST.tsm_adc_calibration(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_CALIBRATION.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 100A {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = hex_to_int(get_random_hex())
    cargo2 = hex_to_int(get_random_hex())
    cmd_string = TCU_TEST.tsm_adc_calibration(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_CALIBRATION.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 100A {format_value(cargo1)} {format_value(cargo2)}"
    )

    cargo1 = get_random_hex(False)
    cargo2 = get_random_hex(False)
    cmd_string = TCU_TEST.tsm_adc_calibration(cargo1=cargo1, cargo2=cargo2).decode()

    assert is_tcu_write_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ADC_CALIBRATION.value
    assert get_cargo1(cmd_string) == format_value(cargo1)
    assert get_cargo2(cmd_string) == format_value(cargo2)

    assert cmd_string.startswith(
        f"0320 {get_expected_transaction_id_as_hex()} 0004 0004 100A {format_value(cargo1)} {format_value(cargo2)}"
    )


# noinspection SpellCheckingInspection
def test_tsm_adc_value_xx_currentn():
    for sens_n in range(1, 48):
        sens_a = 4 * sens_n
        cmd_string = TCU_TEST.tsm_adc_value_xx_currentn(probe=sens_n).decode()
        expected_cmd_id = "20" + hex(sens_a)[2:].zfill(2)

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == CommandAddress.TSM.value
        assert get_cmd_id(cmd_string) == expected_cmd_id
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(
            f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 20{hex(4 * sens_n)[2:].zfill(2)} 0000 0000"
        )


# noinspection SpellCheckingInspection
def test_tsm_adc_value_xx_biasn():
    for sens_n in range(1, 48):
        sens_a = 4 * sens_n + 1
        cmd_string = TCU_TEST.tsm_adc_value_xx_biasn(probe=sens_n).decode()
        expected_cmd_id = "20" + hex(sens_a)[2:].zfill(2)

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == CommandAddress.TSM.value
        assert get_cmd_id(cmd_string) == expected_cmd_id
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(
            f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 20{hex(4 * sens_n + 1)[2:].zfill(2)} 0000 0000"
        )


# noinspection SpellCheckingInspection
def test_tsm_adc_value_xx_currentp():
    for sens_n in range(1, 48):
        sens_a = 4 * sens_n + 2
        cmd_string = TCU_TEST.tsm_adc_value_xx_currentp(probe=sens_n).decode()
        expected_cmd_id = "20" + hex(sens_a)[2:].zfill(2)

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == CommandAddress.TSM.value
        assert get_cmd_id(cmd_string) == expected_cmd_id
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(
            f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 20{hex(4 * sens_n + 2)[2:].zfill(2)} 0000 0000"
        )


# noinspection SpellCheckingInspection
def test_tsm_adc_value_xx_biasp():
    for sens_n in range(1, 48):
        sens_a = 4 * sens_n + 3
        cmd_string = TCU_TEST.tsm_adc_value_xx_biasp(probe=sens_n).decode()
        expected_cmd_id = "20" + hex(sens_a)[2:].zfill(2)

        assert is_tcu_read_cmd(cmd_string)
        assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
        assert get_data_length(cmd_string) == str(DATA_LENGTH)
        assert get_address(cmd_string) == CommandAddress.TSM.value
        assert get_cmd_id(cmd_string) == expected_cmd_id
        assert get_cargo1(cmd_string) == "0000"
        assert get_cargo2(cmd_string) == "0000"

        assert cmd_string.startswith(
            f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 20{hex(4 * sens_n + 3)[2:].zfill(2)} 0000 0000"
        )


def test_tsm_acq_counter():
    cmd_string = TCU_TEST.tsm_acq_counter().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.TSM.value
    assert get_cmd_id(cmd_string) == TSMCommandIdentifier.TSM_ACQ_COUNTER.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0004 20C0 0000 0000")


def test_vhk_psu_vmotor():
    cmd_string = TCU_TEST.vhk_psu_vmotor().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.VHK_PSU_VMOTOR.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0000 0000 0000")


def test_vhk_psu_vhi():
    cmd_string = TCU_TEST.vhk_psu_vhi().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.VHK_PSU_VHI.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0001 0000 0000")


def test_vhk_psu_vlow():
    cmd_string = TCU_TEST.vhk_psu_vlow().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.VHK_PSU_VLOW.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0002 0000 0000")


def test_vhk_psu_vmedp():
    cmd_string = TCU_TEST.vhk_psu_vmedp().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.VHK_PSU_VMEDP.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0003 0000 0000")


def test_vhk_psu_vmedn():
    cmd_string = TCU_TEST.vhk_psu_vmedn().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.VHK_PSU_VMEDN.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0004 0000 0000")


def test_ihk_psu_vmedn():
    cmd_string = TCU_TEST.ihk_psu_vmedn().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.IHK_PSU_VMEDN.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0005 0000 0000")


def test_ihk_psu_vmedp():
    cmd_string = TCU_TEST.ihk_psu_vmedp().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.IHK_PSU_VMEDP.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0006 0000 0000")


def test_ihk_psu_vlow():
    cmd_string = TCU_TEST.ihk_psu_vlow().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.IHK_PSU_VLOW.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0007 0000 0000")


def test_ihk_psu_vhi():
    cmd_string = TCU_TEST.ihk_psu_vhi().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.IHK_PSU_VHI.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0008 0000 0000")


def test_ihk_psu_vmotor():
    cmd_string = TCU_TEST.ihk_psu_vmotor().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.IHK_PSU_VMOTOR.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0009 0000 0000")


def test_thk_psu_first():
    cmd_string = TCU_TEST.thk_psu_first().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_PSU_FIRST.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 000A 0000 0000")


def test_thk_m2md_first():
    cmd_string = TCU_TEST.thk_m2md_first().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_M2MD_FIRST.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 000B 0000 0000")


def test_thk_psu_second():
    cmd_string = TCU_TEST.thk_psu_second().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_PSU_SECOND.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 000C 0000 0000")


def test_thk_m2md_second():
    cmd_string = TCU_TEST.thk_m2md_second().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_M2MD_SECOND.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 000D 0000 0000")


def test_thk_cts_q1():
    cmd_string = TCU_TEST.thk_cts_q1().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_CTS_Q1.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 000E 0000 0000")


def test_thk_cts_q2():
    cmd_string = TCU_TEST.thk_cts_q2().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_CTS_Q2.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 000F 0000 0000")


def test_thk_cts_q3():
    cmd_string = TCU_TEST.thk_cts_q3().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_CTS_Q3.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0010 0000 0000")


def test_thk_cts_q4():
    cmd_string = TCU_TEST.thk_cts_q4().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_CTS_Q4.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0011 0000 0000")


def test_thk_cts_fpga():
    cmd_string = TCU_TEST.thk_cts_fpga().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_CTS_FPGA.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0012 0000 0000")


def test_thk_cts_ads1282():
    cmd_string = TCU_TEST.thk_cts_ads1282().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.THK_CTS_ADS1282.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0013 0000 0000")


def test_vhk_ths_ret():
    cmd_string = TCU_TEST.vhk_ths_ret().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.VHK_THS_RET.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0014 0000 0000")


def test_hk_acq_counter():
    cmd_string = TCU_TEST.hk_acq_counter().decode()

    assert is_tcu_read_cmd(cmd_string)
    assert get_transaction_id(cmd_string) == get_expected_transaction_id_as_hex()
    assert get_data_length(cmd_string) == str(DATA_LENGTH)
    assert get_address(cmd_string) == CommandAddress.HK.value
    assert get_cmd_id(cmd_string) == HKCommandIdentifier.HK_ACQ_COUNTER.value
    assert get_cargo1(cmd_string) == "0000"
    assert get_cargo2(cmd_string) == "0000"

    assert cmd_string.startswith(f"0340 {get_expected_transaction_id_as_hex()} 0004 0005 0015 0000 0000")
