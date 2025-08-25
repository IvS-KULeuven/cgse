import sys
import time
from typing import List

import pytest
import rich

from egse.confman import ConfigurationManagerProxy
from egse.confman import is_configuration_manager_active
from egse.dummy import is_dummy_cs_active
from egse.process import SubProcess
from egse.system import Timer
from egse.system import waiting_for


def test_is_cm_cs_is_active():
    assert is_configuration_manager_active() in (False, True)  # Should not raise an exception


@pytest.mark.skipif(not is_configuration_manager_active(), reason="core service cm_cs not running")
def test_list_setups():
    rich.print()

    with ConfigurationManagerProxy() as cm:
        setups = cm.list_setups()

    assert isinstance(setups, List)

    # FIXME: This check is dependent on the current environment that was set up to run the core services

    assert setups[0] == ("00000", "VACUUM_LAB", "Initial zero Setup for VACUUM_LAB", "no sut_id")


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
def test_listeners():
    dummy_dev = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy", "start-dev"])
    dummy_dev.execute()

    try:
        with ConfigurationManagerProxy() as cm:
            assert "Dummy CS" not in cm.get_listener_names()

            dummy_cs = SubProcess("Dummy CS", [sys.executable, "-m", "egse.dummy", "start-cs"])
            dummy_cs.execute()

            # It takes ~1.5s to startup on my MacBook Pro M2, why is this such a long time?
            with Timer(name="Dummy CS startup timer"):
                waiting_for(is_dummy_cs_active, timeout=5.0)

            assert "Dummy CS" in cm.get_listener_names()

            cm.load_setup(setup_id=1)

            dummy_cs_stop = SubProcess("Dummy CS", [sys.executable, "-m", "egse.dummy"], ["stop-cs"])
            dummy_cs_stop.execute()

            # It takes ~1.5s to startup on my MacBook Pro M2, why is this such a long time?
            with Timer(name="Dummy CS shutdown timer"):
                waiting_for(lambda: not is_dummy_cs_active(), timeout=5.0)

    finally:
        dummy_dev_stop = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["stop-dev"])
        dummy_dev_stop.execute()

        time.sleep(0.5)  # give the processes the time to shut down

        while dummy_dev.is_running():
            time.sleep(1.0)
