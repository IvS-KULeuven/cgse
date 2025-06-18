"""
Test program for the registry server and clients.

Start the registry server as follows. We use these non-standard ports to be completely independent and not interfere
with running core services:

    $ uv run py -m egse.registry.server start --log-level DEBUG --req-port 15556 --pub-port 15557 --hb-port=15558 \
     --db-path test_service_registry.db

Start the clients as follows:

    $ uv run py libs/cgse-core/tests/script_test_registry_client_server.py --use-test-ports

    $ uv run py libs/cgse-core/tests/script_test_registry_client_server.py --use-asyncio --use-test-ports

Notes:
  - the `--use-test-ports` option is the same as using: `--req-port 15556 --pub-port 15557 --hb-port=15558`,
    but this only works for the test clients
  - make sure to use the `--db-path` option when starting the server, or you will use the same SQLite database
    as the core service.
  - you should be able to start several clients, both async and no-async.
  - if you want to get status of the test server, its sufficient to use:

    $  uv run py -m egse.registry.server status --req-port 15556

  - you can stop the test server with CTRL-C or with the command:

    $  uv run py -m egse.registry.server stop --req-port 15556

"""

import asyncio
import logging
import sys
import time

import typer

from egse.registry import DEFAULT_RS_HB_PORT
from egse.registry import DEFAULT_RS_PUB_PORT
from egse.registry import DEFAULT_RS_REQ_PORT
from egse.registry.client import AsyncRegistryClient
from egse.registry.client import RegistryClient


# Constants for testing
TEST_REQ_PORT = 15556
TEST_PUB_PORT = 15557
TEST_HB_PORT = 15558

# Wait timeout for the server to start (seconds)
SERVER_STARTUP_TIMEOUT = 5


def test_proper_termination_of_tasks_sync(
    req_port: int = DEFAULT_RS_REQ_PORT,
    pub_port: int = DEFAULT_RS_PUB_PORT,
    hb_port: int = DEFAULT_RS_HB_PORT,
    host: str = "localhost",
):
    client = RegistryClient(
        registry_req_endpoint=f"tcp://{host}:{req_port}",
        registry_sub_endpoint=f"tcp://{host}:{pub_port}",
        registry_hb_endpoint=f"tcp://{host}:{hb_port}",
        request_timeout=5000,  # 5 second timeout
    )
    client.connect()

    if not client.health_check():
        raise RuntimeError("Client failed to connect to server")

    service_id = client.register(
        name="sync-context-test-service",
        host="localhost",
        port=8080,
        service_type="context-test",
        metadata={"msg": "Hello, World!"},
        ttl=10,
    )

    client.start_heartbeat()

    response = client.get_service(service_id)

    print(response)

    assert response is not None
    assert response["name"] == "sync-context-test-service"
    assert response["metadata"]["msg"] == "Hello, World!"

    print("Sleeping for 10s to let some heartbeats come through...")
    time.sleep(50.0)

    client.stop_heartbeat()
    client.deregister(service_id)
    client.disconnect()


async def test_proper_termination_of_tasks_async(
    req_port: int = DEFAULT_RS_REQ_PORT,
    pub_port: int = DEFAULT_RS_PUB_PORT,
    hb_port: int = DEFAULT_RS_HB_PORT,
    host: str = "localhost",
):
    client = AsyncRegistryClient(
        registry_req_endpoint=f"tcp://{host}:{req_port}",
        registry_sub_endpoint=f"tcp://{host}:{pub_port}",
        registry_hb_endpoint=f"tcp://{host}:{hb_port}",
        request_timeout=5000,  # 5 second timeout
    )
    client.connect()

    # Verify client can connect to server
    health = await client.health_check()
    if not health:
        raise RuntimeError("Client failed to connect to server")

    service_id = await client.register(
        name="async-context-test-service",
        host="localhost",
        port=8080,
        service_type="context-test",
        metadata={"msg": "Hello, World!"},
        ttl=10,
    )

    await client.start_heartbeat()

    response = await client.get_service(service_id)

    print(response)

    assert response is not None
    assert response["name"] == "async-context-test-service"
    assert response["metadata"]["msg"] == "Hello, World!"

    print("Sleeping for 10s to let some heartbeats come through...")
    await asyncio.sleep(10.0)

    await client.stop_heartbeat()
    await client.deregister(service_id)
    client.disconnect()


app = typer.Typer()


@app.command()
def main(
    req_port: int = DEFAULT_RS_REQ_PORT,
    pub_port: int = DEFAULT_RS_PUB_PORT,
    hb_port: int = DEFAULT_RS_HB_PORT,
    host: str = "localhost",
    use_asyncio: bool = False,
    use_test_ports: bool = False,
):
    if use_test_ports:
        req_port = TEST_REQ_PORT
        pub_port = TEST_PUB_PORT
        hb_port = TEST_HB_PORT

    if use_asyncio:
        asyncio.run(test_proper_termination_of_tasks_async(req_port, pub_port, hb_port, host))
    else:
        test_proper_termination_of_tasks_sync(req_port, pub_port, hb_port, host)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(threadName)-12s %(levelname)-8s %(name)-12s %(lineno)5d:%(module)-20s %(message)s",
    )

    sys.exit(app())
