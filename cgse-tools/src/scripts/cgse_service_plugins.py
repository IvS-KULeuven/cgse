# An example plugin for the `cgse {start,stop,status} service` command from `cgse-core`.

import click


@click.command()
@click.option("--xxx-plus", is_flag=True, help="some option")
@click.pass_context
def xxx(ctx, xxx_plus: bool = False):
    print(f"{ctx.obj['action']} XXX services with {xxx_plus = }")
