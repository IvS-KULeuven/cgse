# An example plugin for the `cgse {start,stop,status} service` command from `cgse-core`.
import subprocess
import sys

import click
import rich
from egse.process import SubProcess


@click.command()
@click.option("--simulator", "--sim", is_flag=True,
              help="Start the Hexapod PUNA Simulator as the backend.")
@click.pass_context
def puna_cs(ctx, simulator):
    if ctx.obj['action'] == 'start':
        proc = SubProcess("puna_cs", ["puna_cs", "start", f"{'--sim' if simulator else ''}"], stderr=sys.stderr)
        proc.execute()
    elif ctx.obj['action'] == 'stop':
        proc = SubProcess("puna_cs", ["puna_cs", "stop"], stderr=sys.stderr)
        proc.execute()
    elif ctx.obj['action'] == 'status':
        proc = SubProcess("puna_cs", ["puna_cs", "status"], stdout=subprocess.PIPE)
        proc.execute()
        output, _ = proc.communicate()
        rich.print(output)
    else:
        rich.print(f"[red]ERROR: Unknown action '{ctx.obj['action']}'[/]")
