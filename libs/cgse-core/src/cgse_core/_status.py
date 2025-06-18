import asyncio
import sys

import rich


async def run_all_status(full: bool = False, suppress_errors: bool = True):
    tasks = [
        asyncio.create_task(status_rm_cs(suppress_errors)),
        asyncio.create_task(status_log_cs(suppress_errors)),
        asyncio.create_task(status_sm_cs(full, suppress_errors)),
        asyncio.create_task(status_cm_cs(suppress_errors)),
        asyncio.create_task(status_pm_cs(suppress_errors)),
    ]

    await asyncio.gather(*tasks)


async def status_rm_cs(suppress_errors):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "egse.registry.server",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr and not suppress_errors:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_log_cs(suppress_errors):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "egse.logger.log_cs",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr and not suppress_errors:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_sm_cs(full: bool = False, suppress_errors: bool = True):
    cmd = [sys.executable, "-m", "egse.storage.storage_cs", "status"]
    if full:
        cmd.append("--full" if full else "")

    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr and not suppress_errors:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_cm_cs(suppress_errors):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "egse.confman.confman_cs",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr and not suppress_errors:
        rich.print(f"[red]{stderr.decode()}[/]")


async def status_pm_cs(suppress_errors):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "egse.procman.procman_cs",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    rich.print(stdout.decode().rstrip())
    if stderr and not suppress_errors:
        rich.print(f"[red]{stderr.decode()}[/]")
