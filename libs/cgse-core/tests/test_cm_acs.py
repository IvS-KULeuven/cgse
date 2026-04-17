import asyncio

from egse.setup import Setup
import pytest

from egse.cm_acs.client import AsyncConfigurationManagerClient
from egse.cm_acs.server import AsyncConfigurationManagerControlServer

# The environment for this test is loaded by a fixture (default_env.py) at module-level that is configured
# in the conftest.py of the cgse-core tests and resides in the `fixtures` folder..


@pytest.mark.asyncio
async def test_server(caplog):
    from rich.console import Console

    console = Console()

    # First start the control server as a background task.
    server = AsyncConfigurationManagerControlServer()
    server_task = asyncio.create_task(server.start())

    await asyncio.sleep(0.5)  # give the server time to startup

    try:
        # Now create a control client that will connect to the above server.
        async with AsyncConfigurationManagerClient() as client:
            caplog.clear()

            response = await client.ping()  # just to check that the client can communicate with the server
            assert response == "pong", f"Expected 'Pong' response from the control server, but got '{response}'"

            # Sleep some time, so we can see the control server in action, e.g. status reports, housekeeping, etc
            await asyncio.sleep(3.0)

            setups = await client.list_setups()
            console.print(setups)
            assert setups is not None, "Expected to receive a list of setups from the control server, but got None."
            assert len(setups) > 0, (
                "Expected to receive at least one setup from the control server, but got an empty list."
            )
            assert "00028" in [x[0] for x in setups], (
                "Expected to find setup '00028' in the list of setups, but it was not found."
            )

            response = await client.load_setup(28)
            console.print(response)
            assert response is not None, (
                "Expected to receive a response from the control server when loading setup, but got None."
            )
            assert "history" in response
            assert "28" in response.get("history", {})
            assert response.get("site_id") == "LAB23"

            response = await client.get_setup()
            assert isinstance(response, Setup), f"Expected Setup instance, but got {type(response)}"
            assert response.get_id() == "00028", f"Expected setup ID '00028', but got '{response.get_id()}'"
            assert response.has_private_attribute("_filename")

    except Exception as exc:
        pytest.fail(f"An unexpected exception occurred: {exc}")
    finally:
        server.stop()
        await server_task
