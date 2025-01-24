from dataclasses import dataclass

import pytest

from egse.env import set_default_environment
from fixtures.helpers import setup_conf_data
from fixtures.helpers import setup_data_storage_layout
from fixtures.helpers import teardown_conf_data
from fixtures.helpers import teardown_data_storage_layout


@dataclass
class DefaultEnvironment:
    project: str
    site_id: str
    data_root: str


@pytest.fixture(scope="session", autouse=True)
def default_env(tmp_path_factory):

    project = "CGSE"
    site_id = "LAB23"

    tmp_data_dir = tmp_path_factory.mktemp("data")

    set_default_environment(project, site_id, tmp_data_dir)

    data_root = setup_data_storage_layout(tmp_data_dir)
    setup_conf_data(tmp_data_dir)

    from egse.env import print_env
    print_env()

    yield DefaultEnvironment(project=project, site_id=site_id, data_root=str(data_root))

    teardown_conf_data(tmp_data_dir)
    teardown_data_storage_layout(tmp_data_dir)
