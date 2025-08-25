import contextlib
import logging
import re
import sys
import time

import pytest

from egse.confman import is_configuration_manager_active
from egse.dummy import DummyProxy
from egse.dummy import is_dummy_cs_active
from egse.dummy import is_dummy_dev_active
from egse.process import SubProcess
from egse.proxy import Proxy
from egse.response import Failure
from egse.system import Timer
from egse.system import type_name
from egse.system import waiting_for

logger = logging.getLogger("egse.tests")


def is_service_running(services: list) -> bool:
    is_active = False

    try:
        if "cm" in services:
            if is_configuration_manager_active():
                is_active = True
            else:
                logger.warning("Configuration Manager is not running.")
                is_active = False
    except Exception as exc:
        logger.error(f"Caught {type_name(exc)}: {exc}")
        is_active = False

    return is_active


# Skip entire module if service not running
if not is_service_running(["cm"]):
    pytest.skip("Core service 'cm' not available", allow_module_level=True)


@contextlib.contextmanager
def dummy_service():
    dummy_dev = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["start-dev"])
    dummy_dev.execute()

    with Timer(name="Dummy Dev startup timer"):
        waiting_for(is_dummy_dev_active, timeout=5.0)

    dummy_cs = SubProcess("Dummy CS", [sys.executable, "-m", "egse.dummy"], ["start-cs"])
    dummy_cs.execute()

    processes = [dummy_dev, dummy_cs]

    # It takes ~1.5s to startup on my MacBook Pro M2, why is this such a long time?
    with Timer(name="Dummy CS startup timer"):
        waiting_for(is_dummy_cs_active, timeout=5.0)

    yield processes

    dummy_cs_stop = SubProcess("Dummy CS", [sys.executable, "-m", "egse.dummy"], ["stop-cs"])
    dummy_cs_stop.execute()

    # It takes ~1.5s to startup on my MacBook Pro M2, why is this such a long time?
    with Timer(name="Dummy CS shutdown timer"):
        waiting_for(lambda: not is_dummy_cs_active(), timeout=5.0)

    dummy_dev_stop = SubProcess("Dummy Device", [sys.executable, "-m", "egse.dummy"], ["stop-dev"])
    dummy_dev_stop.execute()

    with Timer(name="Dummy Dev shutdown timer"):
        waiting_for(lambda: not is_dummy_dev_active(), timeout=5.0)


def is_valid_ip_address_format(string):
    pattern = r"^\d{0,3}\.\d{0,3}\.\d{0,3}\.\d{0,3}$"
    return bool(re.match(pattern, string))


def test_proxy_without_cs():
    proxy = DummyProxy()

    assert proxy.is_cs_connected() is False
    assert proxy.has_commands() is False
    assert proxy.get_commands() == []

    with pytest.raises(NotImplementedError):
        assert proxy.info()


def test_device_commands():
    with dummy_service():
        with DummyProxy() as dummy:
            with Timer("info", log_level=logging.WARNING, precision=6):
                assert dummy.info().startswith("Dummy Device")

            with Timer("get_value", log_level=logging.WARNING, precision=6):
                assert 0.0 <= dummy.get_value() < 1.0

            assert dummy.division(144, 12) == 12
            response = dummy.division(33, 0)
            assert isinstance(response, Failure)
            assert response.successful is False
            assert response.message == "Executing division failed: : division by zero"
            assert isinstance(response.cause, ZeroDivisionError)


def test_protocol_commands():
    with dummy_service():
        with DummyProxy() as dummy:
            with Timer("ping", log_level=logging.WARNING, precision=6):
                assert dummy.ping() is True

            assert dummy.get_commanding_port() == 4443
            assert dummy.get_service_port() == 4444
            assert dummy.get_monitoring_port() == 4445

            assert dummy.get_endpoint() == "tcp://localhost:4443"

            assert dummy.has_commands() is True

            for cmd in "info", "get_value", "handle_event":
                assert cmd in dummy.get_commands()

            assert is_valid_ip_address_format(dummy.get_ip_address())

            assert isinstance(dummy.get_service_proxy(), Proxy)
            assert dummy.is_cs_connected() is True


def test_dummy_service():
    print()

    with dummy_service() as procs:
        for proc in procs:
            print(f"{proc.is_running()=}")

        with DummyProxy() as dummy:
            assert dummy.ping() is True

    for proc in procs:
        print(f"{proc.is_running()=}")
