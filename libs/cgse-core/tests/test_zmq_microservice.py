import pytest

from egse.registry.service import ZMQMicroservice
from egse.system import get_host_ip


@pytest.mark.asyncio
async def test_zmq_microservice_initialization():
    print()

    service = ZMQMicroservice("vanilla", "plain")

    assert service.service_name == "vanilla"
    assert service.service_type == "plain"
    assert service.host_ip == get_host_ip()

    print(f"{service.rep_port = }")

    assert service.rep_port != 0

    await service._cleanup()


# Registration to the service registry will time out in 5s
@pytest.mark.timeout(10)
@pytest.mark.asyncio
async def test_zmq_microservices_registration(caplog):
    print()

    service = ZMQMicroservice("vanilla", "plain")

    caplog.clear()
    await service.start()
    assert "Failed to register with the service registry" in caplog.text
