from aim_tti_awg.cgse_services import tgf4000


def test_cgse_tgf4000_subcommands():
    """The `cgse tgf4000` subcommands are for the service lifecycle only. There is no simulator process, the
    simulator is used with `cgse tgf4000 start --sim DEVICE_ID`."""
    names = [command.name for command in tgf4000.registered_commands]

    assert names == ["start", "stop", "status"]
