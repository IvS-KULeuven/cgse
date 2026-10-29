from lakeshore_tempcontrol.cgse_services import lakeshore336


def test_cgse_lakeshore336_subcommands():
    """The `cgse lakeshore336` subcommands are for the service lifecycle only. There is no simulator process, the
    simulator is used with `cgse lakeshore336 start --sim DEVICE_ID`."""
    names = [command.name for command in lakeshore336.registered_commands]

    assert names == ["start", "stop", "status"]
