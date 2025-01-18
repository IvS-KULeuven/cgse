import os
from pathlib import Path

import pytest

import egse.env

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def default_env():

    os.environ['PROJECT'] = "CGSE"
    os.environ["SITE_ID"] = "LAB23"

    os.environ["CGSE_DATA_STORAGE_LOCATION"] = str(HERE / "data")

    egse.env.initialize()
