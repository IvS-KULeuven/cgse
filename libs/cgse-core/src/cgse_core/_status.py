import asyncio
import sys

import rich


async def run_all_status(full: bool = False):
    tasks = [
        asyncio.create_task(status_rs_cs()),
        asyncio.create_task(status_log_cs()),
        asyncio.create_task(status_sm_cs(full)),
        asyncio.create_task(status_cm_cs()),
    ]

    await asyncio.gather(*tasks)


async def status_rs_cs():

    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'egse.registry.server', 'status',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_log_cs():

    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'egse.logger.log_cs', 'status',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_sm_cs(full: bool = False):

    cmd = [sys.executable, '-m', 'egse.storage.storage_cs', 'status']
    if full:
        cmd.append("--full" if full else "")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_cm_cs():

    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'egse.confman.confman_cs', 'status',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")
