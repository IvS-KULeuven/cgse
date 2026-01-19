import asyncio

import pytest

from egse.log import logger
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
# @pytest.mark.timeout(10)
@pytest.mark.asyncio
async def test_zmq_microservices_registration(registry_service):
    service = ZMQMicroservice("vanilla", "plain")

    service_task = asyncio.create_task(service.start())

    await asyncio.sleep(5.0)

    await service.stop()
    await service_task

    logger.info("Service task completed")

    service_task.cancel()
    try:
        await service_task
    except asyncio.CancelledError:
        logger.info("Service task was cancelled as expected.")
