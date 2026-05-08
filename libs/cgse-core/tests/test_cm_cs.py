import time
from typing import List

import pytest
import rich
from egse.env import setup_env
from egse.log import logger

from egse.confman import ConfigurationManagerProxy
from egse.confman import is_configuration_manager_active

setup_env()  # Ensure the environment is set up for the tests, e.g. SITE_ID is set


def test_is_cm_cs_is_active():
    assert is_configuration_manager_active() in (False, True)  # Should not raise an exception


@pytest.mark.integration
@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_list_setups():
    rich.print()

    with ConfigurationManagerProxy() as cm:
        setups = cm.list_setups()

    assert isinstance(setups, List)

    # FIXME: This check is dependent on the current environment that was set up to run the core services

    assert setups[0] == ("00000", "VACUUM_LAB", "Initial zero Setup for VACUUM_LAB", "no sut_id")


@pytest.mark.integration
@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_load_setup():
    with ConfigurationManagerProxy() as cm:
        setup = cm.load_setup(setup_id=0)
        assert setup.get_id() == "00000"

        # load_setup(..) does change the Setup that is loaded on the cm_cs

        setup = cm.load_setup(setup_id=1)
        assert setup.get_id() == "00001"

        setup = cm.get_setup()
        assert setup.get_id() == "00001"


@pytest.mark.integration
@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_get_setup():
    with ConfigurationManagerProxy() as cm:
        setup = cm.load_setup(setup_id=0)
        assert setup.get_id() == "00000"

        # get_setup(..) doesn't change the Setup that is loaded on the cm_cs

        setup = cm.get_setup(setup_id=1)
        assert setup.get_id() == "00001"

        setup = cm.get_setup()
        assert setup.get_id() == "00000"


@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_start_observation():
    from egse.obsid import ObservationIdentifier

    with ConfigurationManagerProxy() as cm:
        setup = cm.load_setup(setup_id=0)
        assert setup.get_id() == "00000"

        response = cm.start_observation({"description": "Test observation"})

        logger.info(f"Observation started with response: {response}, {response.return_code}")
        assert response.message.startswith("Returning the OBSID")
        assert isinstance(response.return_code, ObservationIdentifier)

        time.sleep(1.0)

        response = cm.end_observation()
        logger.info(f"Observation ended with response: {response}")
        assert response.message == "Successfully ended the observation."
        assert response.return_code is None
