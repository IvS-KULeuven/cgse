import time
from logging import warning

import pytest

from egse.process import SubProcess
from egse.process import is_process_running
from egse.system import waiting_for

from fixtures.helpers import is_process_not_running


# #### WARNING #####
#
# The fixtures below test for specific process names if these processes are running. The test checks if
# a process name like 'feesim' is present 'in' the cmdline of the process. Therefore, do not use these
# names in your test functions because they will also show up in the cmdline of the pytest process if you
# run that particular test function, e.g. 'pytest test_bla.py::test_feesim'.
#
# names tested are: dpu_cs, feesim, log_cs, sm_cs, cm_cs, pm_cs, syn_cs

# ##### TIP #####
#
# If you want to see which fixtures are started, run the pytest with the option '--setup-show'.


@pytest.fixture(scope="module")
def setup_log_service():
    """This fixture starts the CGSE log service."""

    if is_process_running(items=["log_cs"]):
        pytest.xfail("The logging manager is already running")

    # Starting the logging manager ------------------------------------------------------------------------------------

    log_cs = SubProcess("Logging Manager", ["log_cs", "start"])
    log_cs.execute()

    try:
        waiting_for(is_process_running, ["log_cs"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't start the logging manager within the given time of 5s.") from exc

    time.sleep(0.5)  # give the process some time to startup

    yield

    # Stopping the logging manager ------------------------------------------------------------------------------------

    log_cs_stop = SubProcess("Logging Manager", ["log_cs", "stop"])
    log_cs_stop.execute()

    try:
        waiting_for(is_process_not_running, ["log_cs", "start"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        warning("Couldn't stop the logging manager within the given time of 5s. Quiting...")
        log_cs.quit()


@pytest.fixture(scope="module")
def setup_core_services():
    """This fixture starts the CGSE core services."""

    from egse.confman import is_configuration_manager_active
    from egse.procman import is_process_manager_cs_active

    if is_process_running(items=["log_cs"]):
        pytest.xfail("The logging manager is already running")

    if is_process_running(items=["sm_cs"]):
        pytest.xfail("The storage manager is already running")

    if is_process_running(items=["cm_cs"]):
        pytest.xfail("The configuration manager is already running")

    if is_process_running(items=["pm_cs"]):
        pytest.xfail("The process manager is already running")

    if is_process_running(items=["syn_cs"]):
        pytest.xfail("The synoptics manager is already running")

    # Starting the logging manager ------------------------------------------------------------------------------------

    log_cs = SubProcess("Logging Manager", ["log_cs", "start"])
    log_cs.execute()

    try:
        waiting_for(is_process_running, ["log_cs"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't start the logging manager within the given time of 5s.") from exc

    # Starting the storage manager ------------------------------------------------------------------------------------

    sm_cs = SubProcess("Storage Manager", ["sm_cs", "start"])
    sm_cs.execute()

    try:
        waiting_for(is_process_running, ["sm_cs"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't start the storage manager within the given time of 5s.") from exc

    # Starting the configuration manager ------------------------------------------------------------------------------

    cm_cs = SubProcess("Configuration Manager", ["cm_cs", "start"])
    cm_cs.execute()

    try:
        waiting_for(is_process_running, ["cm_cs"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't start the configuration manager within the given time of 5s.") from exc

    # We know that the cm_cs will not respond to Proxy requests until it is fully initialised, so wait for that too!

    try:
        waiting_for(is_configuration_manager_active, timeout=30.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't connect to configuration manager even after a timeout of 30s.") from exc

    # Starting the process manager ------------------------------------------------------------------------------------

    pm_cs = SubProcess("Process Manager", ["pm_cs", "start"])
    pm_cs.execute()

    try:
        waiting_for(is_process_running, ["pm_cs"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't start the process manager within the given time of 5s.") from exc

    try:
        waiting_for(is_process_manager_cs_active, timeout=30.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't connect to process manager even after a timeout of 30s.") from exc

    # Starting the synoptics manager ----------------------------------------------------------------------------------

    syn_cs = SubProcess("Synoptics Manager", ["syn_cs", "start"])
    syn_cs.execute()

    try:
        waiting_for(is_process_running, ["syn_cs"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        raise RuntimeError("Couldn't start the synoptics manager within the given time of 5s.") from exc

    yield

    # Stop the processes in reverse order as they were started

    # Stopping the synoptics manager ----------------------------------------------------------------------------------

    syn_cs_stop = SubProcess("Synoptics Manager", ["syn_cs", "stop"])
    syn_cs_stop.execute()

    try:
        waiting_for(is_process_not_running, ["syn_cs", "start"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        warning("Couldn't stop the synoptics manager within the given time of 5s. Quiting...")
        syn_cs.quit()

    # Stopping the process manager ------------------------------------------------------------------------------------

    pm_cs_stop = SubProcess("Process Manager", ["pm_cs", "stop"])
    pm_cs_stop.execute()

    try:
        waiting_for(is_process_not_running, ["pm_cs", "start"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        warning("Couldn't stop the process manager within the given time of 5s. Quiting...")
        pm_cs.quit()

    # Stopping the configuration manager ------------------------------------------------------------------------------

    cm_cs_stop = SubProcess("Configuration Manager", ["cm_cs", "stop"])
    cm_cs_stop.execute()

    try:
        waiting_for(is_process_not_running, ["cm_cs", "start"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        warning("Couldn't stop the configuration manager within the given time of 5s. Quiting...")
        cm_cs.quit()

    # Stopping the storage manager ------------------------------------------------------------------------------------

    sm_cs_stop = SubProcess("Storage Manager", ["sm_cs", "stop"])
    sm_cs_stop.execute()

    try:
        waiting_for(is_process_not_running, ["sm_cs", "start"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        warning("Couldn't stop the storage manager within the given time of 5s. Quiting...")
        sm_cs.quit()

    # Stopping the logging manager ------------------------------------------------------------------------------------

    log_cs_stop = SubProcess("Logging Manager", ["log_cs", "stop"])
    log_cs_stop.execute()

    try:
        waiting_for(is_process_not_running, ["log_cs", "start"], interval=1.0, timeout=5.0)
    except TimeoutError as exc:
        warning("Couldn't stop the logging manager within the given time of 5s. Quiting...")
        log_cs.quit()
