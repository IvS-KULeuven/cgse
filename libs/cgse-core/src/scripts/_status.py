import asyncio
# import subprocess
import sys

import rich


async def run_all_status():
    tasks = [
        status_log_cs(),
        status_sm_cs(),
        status_cm_cs(),
    ]

    await asyncio.gather(*tasks)


async def status_log_cs():

    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'egse.logger.log_cs', 'status',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    # proc = subprocess.Popen(
    #     [sys.executable, '-m', 'egse.logger.log_cs', 'status'],
    #     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    # )
    #
    # stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end='')
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_sm_cs():

    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'egse.storage.storage_cs', 'status',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    # proc = subprocess.Popen(
    #     [sys.executable, '-m', 'egse.storage.storage_cs', 'status'],
    #     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    # )
    #
    # stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end='')
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_cm_cs():

    proc = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'egse.confman.confman_cs', 'status',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    # proc = subprocess.Popen(
    #     [sys.executable, '-m', 'egse.confman.confman_cs', 'status'],
    #     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    # )
    #
    # stdout, stderr = proc.communicate()

    rich.print(stdout.decode(), end='')
    if stderr:
        rich.print(f"[red]{stderr.decode()}[/]")
