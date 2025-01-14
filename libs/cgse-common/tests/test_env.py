import os
import warnings

import pytest

import egse.env
from egse.env import get_conf_data_location
from egse.env import get_data_storage_location
from egse.env import get_log_file_location
from egse.system import env_var


def test_get_data_storage_location():

    print()

    with (env_var(PROJECT="TEST"),
          env_var(SITE_ID="ESA"),
          env_var(TEST_DATA_STORAGE_LOCATION="/data/test")):

        egse.env.initialize()

        assert get_data_storage_location() == '/data/test/ESA'

        # the site_id argument takes precedence over the SITE_ID environment variable

        assert get_data_storage_location(site_id="KUL") == "/data/test/KUL"


    with (env_var(PROJECT=None)):
        with (pytest.warns(UserWarning, match=r"environment variable \w+ is not set"),
              pytest.raises(ValueError) as exc):
            egse.env.initialize()
            get_data_storage_location()
        print(f"{exc.typename}: {exc.value}")

    with env_var(SITE_ID=None):
        with (pytest.warns(UserWarning, match=r"environment variable \w+ is not set"),
              pytest.raises(ValueError) as exc):
            egse.env.initialize()
            get_data_storage_location()
        print(f"{exc.typename}: {exc.value}")


def test_get_conf_data_location():

    with (env_var(PROJECT="TEST"),
          env_var(SITE_ID="ESA"),
          env_var(TEST_CONF_DATA_LOCATION="/data/conf"),
          env_var(TEST_DATA_STORAGE_LOCATION="/storage")):

        egse.env.initialize()

        assert get_conf_data_location() == '/data/conf'
        assert get_conf_data_location(site_id="KUL") == '/data/conf'

        with env_var(TEST_CONF_DATA_LOCATION=None):

            egse.env.initialize()

            assert get_conf_data_location() == '/storage/ESA/conf'
            assert get_conf_data_location(site_id="KUL") == '/storage/KUL/conf'


def test_get_log_file_location():

    with (env_var(PROJECT="TEST"),
          env_var(SITE_ID="ESA"),
          env_var(TEST_LOG_FILE_LOCATION="/data/logs"),
          env_var(TEST_DATA_STORAGE_LOCATION="/storage")):

        egse.env.initialize()

        assert get_log_file_location() == '/data/logs'
        assert get_log_file_location(site_id="KUL") == '/data/logs'

        with env_var(TEST_LOG_FILE_LOCATION=None):

            egse.env.initialize()

            assert get_log_file_location() == '/storage/ESA/log'
            assert get_log_file_location(site_id="KUL") == '/storage/KUL/log'
