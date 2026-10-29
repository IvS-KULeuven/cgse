from rs_pro_power_supply.cgse_services import rsd3305p


def test_cgse_rsd3305p_subcommands():
    """The `cgse rsd3305p` subcommands are for the service lifecycle only. There is no simulator process, the
    simulator is used with `cgse rsd3305p start --sim DEVICE_ID`."""
    names = [command.name for command in rsd3305p.registered_commands]

    assert names == ["start", "stop", "status"]
