from kikusui_power_supply.cgse_services import pmx_a


def test_cgse_pmx_a_subcommands():
    """The `cgse pmx_a` subcommands are for the service lifecycle only. There is no simulator process, the
    simulator is used with `cgse pmx_a start --sim DEVICE_ID`."""
    names = [command.name for command in pmx_a.registered_commands]

    assert names == ["start", "stop", "status"]
