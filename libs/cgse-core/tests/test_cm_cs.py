import sys
import time
from typing import List

import pytest
import rich

from egse.confman import ConfigurationManagerProxy
from egse.confman import is_configuration_manager_active
from egse.confman.confman_cs import list_setups
from egse.process import SubProcess


def test_is_cm_cs_is_active():

    assert is_configuration_manager_active() in (False, True)  # Should not raise an exception


@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_list_setups():

    rich.print()

    with ConfigurationManagerProxy() as cm:
        setups = cm.list_setups()

    assert isinstance(setups, List)

    # FIXME: This check is dependent on the current environment that was set up to run the core services

    assert setups[0] == ('00000', 'VACUUM_LAB', 'Initial zero Setup for VACUUM_LAB', 'no sut_id')


@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_load_setup():

    with ConfigurationManagerProxy() as cm:
        setup = cm.load_setup(setup_id=0)
        assert setup.get_id() == '00000'

        # load_setup(..) does change the Setup that is loaded on the cm_cs

        setup = cm.load_setup(setup_id=1)
        assert setup.get_id() == '00001'

        setup = cm.get_setup()
        assert setup.get_id() == '00001'


@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_get_setup():

    with ConfigurationManagerProxy() as cm:
        setup = cm.load_setup(setup_id=0)
        assert setup.get_id() == '00000'

        # get_setup(..) doesn't change the Setup that is loaded on the cm_cs

        setup = cm.get_setup(setup_id=1)
        assert setup.get_id() == '00001'

        setup = cm.get_setup()
        assert setup.get_id() == '00000'


@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_listeners():

    dummy_dev = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy", "start-dev"])
    dummy_dev.execute()

    dummy_cs = SubProcess("Dummy CS", [sys.executable, "-m", "egse.dummy", "start-cs"])

    try:
        with ConfigurationManagerProxy() as cm:

            assert 'Dummy CS' not in cm.get_listener_names()

            dummy_cs.execute()

            time.sleep(0.5)  # Registration needs some time

            assert 'Dummy CS' in cm.get_listener_names()

            cm.load_setup(setup_id=1)

    finally:
        dummy_dev.quit()
        dummy_cs.quit()

        while dummy_dev.is_running():
            time.sleep(1.0)
