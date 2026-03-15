import asyncio
from typing import cast

import pytest
from fixtures.helpers import capture_log_records

from egse.async_control import AsyncControlClient
from egse.async_control import AsyncControlServer
from egse.async_control import InitializationError
from egse.async_control import is_control_server_active
from egse.async_dummy import DummyAsyncControlClient
from egse.async_dummy import DummyAsyncControlServer
from egse.log import logging
from egse.system import type_name

# pytestmark = pytest.mark.skip("Implementation and tests are still a WIP")

logger = logging.getLogger("egse.tests.async_control")


@pytest.mark.asyncio
async def test_control_server(caplog):
    # First start the control server as a background task.
    server = AsyncControlServer()
    server_task = asyncio.create_task(server.start())

    await asyncio.sleep(0.5)  # give the server time to startup

    try:
        # Now create a control client that will connect to the above server.
        async with AsyncControlClient(service_type="async-control-server") as client:
            caplog.clear()

            # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
            await asyncio.sleep(5.0)

            assert "Sending status updates" in caplog.text  # this should there be 5 times actually

            response = await client.ping()
            logger.debug(f"{response = }")
            assert isinstance(response, str)
            assert response == "pong"

            response = await client.info()
            logger.debug(f"{response = }")
            assert isinstance(response, dict)
            assert "name" in response
            assert "hostname" in response
            assert "device commanding port" in response
            assert "service commanding port" in response

            assert await is_control_server_active(service_type="async-control-server")

            response = await client.stop_server()
            logger.debug(f"{response = }")
            assert isinstance(response, dict)
            assert response["status"] == "terminating"

            assert await is_control_server_active(service_type="async-control-server")
    except InitializationError as exc:
        logger.error(f"Could not create AsyncControlClient: {type_name(exc)}: {exc}")

    server_task.cancel()
    await server_task

    assert not await is_control_server_active(service_type="async-control-server")


@pytest.mark.asyncio
async def test_dummy_control_server():
    """Test DummyAsyncControlServer as an implementation example."""
    server = DummyAsyncControlServer()
    server_task = asyncio.create_task(server.start())

    await asyncio.sleep(0.5)  # give the server time to startup

    # Now create a control client that will connect to the above server.
    async with DummyAsyncControlClient() as client:
        response = await client.ping()
        logger.debug(f"{response = }")
        assert isinstance(response, str)
        assert response == "pong"

        response = await client.echo("dummy")
        logger.debug(f"{response = }")
        assert response == "dummy"

        response = await client.set_value("configured")
        logger.debug(f"{response = }")
        assert response == "configured"

        info_response = await client.info()
        logger.debug(f"{info_response = }")
        assert isinstance(info_response, dict)
        info_response = cast(dict[str, object], info_response)
        assert "name" in info_response
        assert "hostname" in info_response
        assert "device commanding port" in info_response
        assert "service commanding port" in info_response
        assert info_response["service type"] == DummyAsyncControlServer.service_type
        assert info_response["echo count"] == 1
        assert info_response["last value"] == "configured"

        health_response = await client.health()
        logger.debug(f"{health_response = }")
        assert isinstance(health_response, dict)
        assert health_response["status"] == "ok"
        assert health_response["echo count"] == 1
        assert health_response["last value"] == "configured"

    server_task.cancel()
    await server_task


if __name__ == "__main__":
    with capture_log_records("egse") as caplog:
        asyncio.run(test_control_server(caplog=caplog))
