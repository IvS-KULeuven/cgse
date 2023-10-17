# An example plugin for a major command on the `cgse` script in `cgse-core`.
import click


@click.command()
@click.option("--full", is_flag=True, help="some option")
def foo(full: bool = False):
    """Example of major command plugin for `cgse`."""
    print(f"execute foo --{full=}")
