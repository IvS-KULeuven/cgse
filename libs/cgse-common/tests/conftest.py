import os
from dataclasses import dataclass
from pathlib import Path

import pytest

import egse.env
from helpers import setup_data_storage_layout, teardown_data_storage_layout

HERE = Path(__file__).parent


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

    egse.env.set_default_environment(project, site_id, tmp_data_dir)

    data_root = setup_data_storage_layout(tmp_data_dir)

    yield DefaultEnvironment(project=project, site_id=site_id, data_root=str(data_root))

    teardown_data_storage_layout(tmp_data_dir)
