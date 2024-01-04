"""
This script is as an administration script for the CGSE. The script provides commands to start, stop, and
get the status of the core services and any other service that is registered as a plugin.

The following main commands have been implemented:

$ cgse version

    Prints the installed version of the cgse-core and any other package that is registered under
    the entry points group 'cgse.version'.

$ cgse {start,stop} {core,service} NAME ARGS

    Starts, stops the core services or any service that is registered under the entry points
    group 'cgse.service.plugins'.

$ cgse status {core,service} NAME ARGS

    Prints the status of the core services or any service that is registered under the entry
    points group 'cgse.service.plugins'.

Other main commands can be added from external packages when they are provided as entry points with
the group name 'cgse.plugins'. The entry point needs to be a Click command.

"""
import subprocess

import click
import rich

from egse.plugin import entry_points
from egse.plugin import handle_click_plugins
from egse.process import SubProcess


@handle_click_plugins(entry_points("cgse.plugins"))
@click.group()
def cli():
    pass


@cli.command()
def version():
    """Prints the version of the cgse-core and other registered packages."""
    from egse.version import get_version_installed

    # if installed_version := get_version_installed("cgse-core"):
    #     rich.print(f"CGSE-CORE installed version = [bold default]{installed_version}[/]")

    for ep in sorted(entry_points("cgse.version"), key=lambda x: x.name):
        if installed_version := get_version_installed(ep.name):
            rich.print(f"{ep.name.upper()} installed version = [bold default]{installed_version}[/]")


@cli.group()
@click.pass_context
def start(ctx):
    """Start the service"""
    ctx.ensure_object(dict)

    ctx.obj['action'] = 'start'


@cli.group()
@click.pass_context
def stop(ctx):
    """Stop the service"""
    ctx.ensure_object(dict)

    ctx.obj['action'] = 'stop'


@cli.group()
@click.pass_context
def status(ctx):
    """Provide the status of the service"""
    ctx.ensure_object(dict)

    ctx.obj['action'] = 'status'


@start.command()
@click.pass_context
def core(ctx):
    print(f"executing: cgse {ctx.obj['action']} core")
    ctx.invoke(log_cs)
    ctx.invoke(sm_cs)
    ctx.invoke(cm_cs)
    ctx.invoke(pm_cs)


@handle_click_plugins(entry_points("cgse.service.plugins"))
@start.group()
@click.pass_context
def service(ctx):
    pass


stop.add_command(core)
stop.add_command(service)

status.add_command(core)
status.add_command(service)


@service.command()
@click.pass_context
def log_cs(ctx):
    print(f"executing: log_cs {ctx.obj['action']}")
    if ctx.obj['action'] == 'start':
        proc = SubProcess("log_cs", ["log_cs", "start"])
        proc.execute()
    elif ctx.obj['action'] == 'stop':
        proc = SubProcess("log_cs", ["log_cs", "stop"])
        proc.execute()
    elif ctx.obj['action'] == 'status':
        proc = SubProcess("log_cs", ["log_cs", "status"], stdout=subprocess.PIPE)
        proc.execute()
        output, _ = proc.communicate()
        rich.print(output, end='')
    else:
        rich.print(f"[red]ERROR: Unknown action '{ctx.obj['action']}'[/]")


@service.command()
@click.pass_context
def sm_cs(ctx):
    print(f"executing: sm_cs {ctx.obj['action']}")
    if ctx.obj['action'] == 'start':
        proc = SubProcess("sm_cs", ["sm_cs", "start"])
        proc.execute()
    elif ctx.obj['action'] == 'stop':
        proc = SubProcess("sm_cs", ["sm_cs", "stop"])
        proc.execute()
    elif ctx.obj['action'] == 'status':
        proc = SubProcess("sm_cs", ["sm_cs", "status"], stdout=subprocess.PIPE)
        proc.execute()
        output, _ = proc.communicate()
        rich.print(output, end='')
    else:
        rich.print(f"[red]ERROR: Unknown action '{ctx.obj['action']}'[/]")


@service.command()
@click.pass_context
def cm_cs(ctx):
    print(f"executing: cm_cs {ctx.obj['action']}")
    if ctx.obj['action'] == 'start':
        proc = SubProcess("cm_cs", ["cm_cs", "start"])
        proc.execute()
    elif ctx.obj['action'] == 'stop':
        proc = SubProcess("cm_cs", ["cm_cs", "stop"])
        proc.execute()
    elif ctx.obj['action'] == 'status':
        proc = SubProcess("cm_cs", ["cm_cs", "status"], stdout=subprocess.PIPE)
        proc.execute()
        output, _ = proc.communicate()
        rich.print(output, end='')
    else:
        rich.print(f"[red]ERROR: Unknown action '{ctx.obj['action']}'[/]")


@service.command()
@click.pass_context
def pm_cs(ctx):
    print(f"executing: pm_cs {ctx.obj['action']}")
    if ctx.obj['action'] == 'start':
        proc = SubProcess("pm_cs", ["pm_cs", "start"])
        proc.execute()
    elif ctx.obj['action'] == 'stop':
        proc = SubProcess("pm_cs", ["pm_cs", "stop"])
        proc.execute()
    elif ctx.obj['action'] == 'status':
        proc = SubProcess("pm_cs", ["pm_cs", "status"], stdout=subprocess.PIPE)
        proc.execute()
        output, _ = proc.communicate()
        rich.print(output, end='')
    else:
        rich.print(f"[red]ERROR: Unknown action '{ctx.obj['action']}'[/]")
