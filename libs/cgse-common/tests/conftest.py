import os
from pathlib import Path

import pytest

import egse.env
from helpers import create_data_storage_layout

HERE = Path(__file__).parent


@pytest.fixture(scope="session")
def default_env(tmp_path_factory):

    os.environ['PROJECT'] = "CGSE"
    os.environ["SITE_ID"] = "LAB23"

    egse.env.initialize()

    tmp_data_dir = tmp_path_factory.mktemp("data")

    data_root = create_data_storage_layout(tmp_data_dir)

    return data_root
