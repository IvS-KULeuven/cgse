import pytest

from egse.env import get_conf_repo_location
from egse.env import initialize as env_initialize
from egse.env import get_conf_data_location
from egse.env import get_data_storage_location
from egse.env import get_local_settings
from egse.env import get_local_settings_env_name
from egse.env import get_log_file_location
from egse.env import set_conf_data_location
from egse.env import set_conf_repo_location
from egse.env import set_data_storage_location
from egse.env import set_local_settings
from egse.env import set_log_file_location
from egse.system import env_var


def test_get_data_storage_location():

    print()

    with (env_var(PROJECT="TEST"),
          env_var(SITE_ID="ESA"),
          env_var(TEST_DATA_STORAGE_LOCATION="/data/test")):

        env_initialize()

        assert get_data_storage_location() == '/data/test/ESA'

        # the site_id argument takes precedence over the SITE_ID environment variable

        assert get_data_storage_location(site_id="KUL") == "/data/test/KUL"

    with (env_var(PROJECT=None)):
        with (pytest.warns(UserWarning, match=r"environment variable \w+ is not set"),
              pytest.raises(ValueError) as exc):
            env_initialize()
            get_data_storage_location()
        print(f"{exc.typename}: {exc.value}")

    with env_var(SITE_ID=None):
        with (pytest.warns(UserWarning, match=r"environment variable \w+ is not set"),
              pytest.raises(ValueError) as exc):
            env_initialize()
            get_data_storage_location()
        print(f"{exc.typename}: {exc.value}")


def test_set_data_storage_location():

    with env_var(PROJECT="PLATO"):
        env_initialize()

        with pytest.warns(UserWarning, match="PLATO_DATA_STORAGE_LOCATION"):
            set_data_storage_location("/tmp/data")

        assert get_data_storage_location(site_id="KUL") == "/tmp/data/KUL"


def test_get_conf_data_location():

    with (env_var(PROJECT="TEST"),
          env_var(SITE_ID="ESA"),
          env_var(TEST_CONF_DATA_LOCATION="/data/conf"),
          env_var(TEST_DATA_STORAGE_LOCATION="/storage")):

        env_initialize()

        assert get_conf_data_location() == '/data/conf'
        assert get_conf_data_location(site_id="KUL") == '/data/conf'

        with env_var(TEST_CONF_DATA_LOCATION=None):
            env_initialize()

            assert get_conf_data_location() == '/storage/ESA/conf'
            assert get_conf_data_location(site_id="KUL") == '/storage/KUL/conf'

            with env_var(TEST_DATA_STORAGE_LOCATION=None):
                env_initialize()

                with pytest.raises(ValueError, match="Could not determine the location"):
                    assert get_conf_data_location() == '/storage/ESA/conf'


def test_set_conf_data_location():

    with env_var(PROJECT="PLATO"):
        env_initialize()

        with pytest.warns(UserWarning, match="PLATO_CONF_DATA_LOCATION"):
            set_conf_data_location("/tmp/data")

        assert get_conf_data_location(site_id="KUL") == "/tmp/data"
        assert get_conf_data_location() == "/tmp/data"


def test_get_log_file_location():

    with (env_var(PROJECT="TEST"),
          env_var(SITE_ID="ESA"),
          env_var(TEST_LOG_FILE_LOCATION="/data/logs"),
          env_var(TEST_DATA_STORAGE_LOCATION="/storage")):

        env_initialize()

        assert get_log_file_location() == '/data/logs'
        assert get_log_file_location(site_id="KUL") == '/data/logs'

        with env_var(TEST_LOG_FILE_LOCATION=None):

            env_initialize()

            assert get_log_file_location() == '/storage/ESA/log'
            assert get_log_file_location(site_id="KUL") == '/storage/KUL/log'


def test_set_log_file_location():

    with env_var(PROJECT="PLATO"):
        env_initialize()

        with pytest.warns(UserWarning, match="PLATO_LOG_FILE_LOCATION"):
            set_log_file_location("/tmp/data/log")

        assert get_log_file_location(site_id="KUL") == "/tmp/data/log"
        assert get_log_file_location() == "/tmp/data/log"


def test_get_local_settings():

    with env_var(PROJECT="CGSE"), env_var(CGSE_LOCAL_SETTINGS="/tmp/local_settings.yaml"):
        env_initialize()

        with pytest.warns(UserWarning, match="local settings for your project will not be loaded"):
            assert get_local_settings_env_name() == "CGSE_LOCAL_SETTINGS"
            assert get_local_settings() == "/tmp/local_settings.yaml"


def test_set_local_settings():

    with env_var(PROJECT="CGSE"):
        env_initialize()

        with pytest.warns(UserWarning, match="CGSE_LOCAL_SETTINGS"):
            set_local_settings("/tmp/data/local_settings.yaml")

        with pytest.warns(UserWarning, match="As a result, the local settings for your project will not be loaded"):
            assert get_local_settings() == "/tmp/data/local_settings.yaml"


def test_get_conf_repo_location():

    with env_var(PROJECT="CGSE"), env_var(CGSE_CONF_REPO_LOCATION="/tmp/git/conf-repo"):
        env_initialize()
        with pytest.warns(UserWarning, match="The location of the configuration data repository doesn't exist: "
                                             "/tmp/git/conf-repo"):
            assert get_conf_repo_location() == "/tmp/git/conf-repo"

    with env_var(PROJECT="CGSE"), env_var(CGSE_CONF_REPO_LOCATION=None):
        env_initialize()
        assert get_conf_repo_location() is None


def test_set_conf_repo_location():

    with env_var(PROJECT="CGSE"):
        env_initialize()

        with pytest.warns(UserWarning, match="CGSE_CONF_REPO_LOCATION"):
            set_conf_repo_location("/tmp/data/conf-repo")

        with pytest.warns(UserWarning, match="location of the configuration data repository doesn't exist"):
            assert get_conf_repo_location() == "/tmp/data/conf-repo"


def test_main(capsys):

    from egse.env import main as env_main

    with env_var(PROJECT="CUBESPEC"), env_var(PYTHONSTARTUP="my_script.py"):
        env_initialize()

        env_main()

        captured = capsys.readouterr()

        assert 'PROJECT = CUBESPEC' in captured.out  # noqa

        # The following shall only be output with '--full'
        assert 'PYTHONSTARTUP=my_script.py' not in captured.out  # noqa

        env_main(["--full"])

        captured = capsys.readouterr()

        assert 'PYTHONSTARTUP=my_script.py' in captured.out  # noqa
