import asyncio
import logging
import time

import rich

from egse.decorators import async_timer
from egse.decorators import timer
from egse.registry.client import AsyncRegistryClient
from egse.registry.client import RegistryClient

logging.basicConfig(level=logging.INFO)


@timer()
def main(count: int = 1):
    for _ in range(count):
        with RegistryClient() as reg:
            if reg.health_check():
                rich.print("[green]registry server is healthy.")
            else:
                rich.print("[red]error: health check failed.[/]")

            service_id = reg.register("stress-test", "localhost", 1234, "testing")
            if service_id is None:
                rich.print("[red]error: Couldn't register stress-test[/]")

            endpoint = reg.get_endpoint("testing")
            if endpoint is None:
                rich.print("[red]error: no endpoint for testing[/]")

            service = reg.get_service(service_id)
            if service is None:
                rich.print(f"[red]error: no service {service_id} found[/]")

            if not reg.deregister(service_id):
                rich.print("[red]error: Couldn't de-register stress-test[/]")


@async_timer()
async def amain(count: int = 1):
    for _ in range(count):
        with AsyncRegistryClient() as reg:
            if await reg.health_check():
                rich.print("[green]registry server is healthy.")
            else:
                rich.print("[red]error: health check failed.[/]")

            service_id = await reg.register("stress-test", "localhost", 1234, "testing")
            if service_id is None:
                rich.print("[red]error: Couldn't register stress-test[/]")

            endpoint = await reg.get_endpoint("testing")
            if endpoint is None:
                rich.print("[red]error: no endpoint for testing[/]")

            service = await reg.get_service(service_id)
            if service is None:
                rich.print(f"[red]error: no service {service_id} found[/]")

            if not await reg.deregister(service_id):
                rich.print("[red]error: Couldn't de-register stress-test[/]")


if __name__ == '__main__':

    with RegistryClient() as reg:
        service_id = reg.register("stress-test-heartbeat", "localhost", 5678)
        reg.start_heartbeat(3)

        main()

        time.sleep(10)
        response = reg.server_status()
        rich.print(response)
        time.sleep(10)

        asyncio.run(amain())

        reg.stop_heartbeat()
        reg.deregister(service_id)

        response = reg.server_status()
        rich.print(response)

        if reg.terminate_registry_server():
            rich.print("[green]Registry Server terminated successfully[/]")
        else:
            rich.print("[red]error: Couldn't terminate registry server..[/]")
