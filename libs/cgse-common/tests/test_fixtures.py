from egse.env import get_conf_data_location
from egse.env import get_data_storage_location
from egse.env import get_log_file_location


def test_data_storage_layout(default_env):

    data_root = default_env

    assert get_data_storage_location() == str(data_root)
    assert get_conf_data_location() == str(data_root / "conf")
    assert get_log_file_location() == str(data_root / "log")
