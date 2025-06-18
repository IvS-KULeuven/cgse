import logging

from egse.tempcontrol.lakeshore.lakeshore336 import LakeShore336Simulator, SelfTestResult

MODULE_LOGGER = logging.getLogger(__name__)


def test_constructor():
    lakeshore = LakeShore336Simulator("TEST")
    assert lakeshore.device_id == "TEST"
    assert lakeshore.is_connected()


def test_disconnect():
    lakeshore = LakeShore336Simulator("TEST")
    assert lakeshore.is_connected()

    lakeshore.disconnect()
    assert not lakeshore.is_connected()


def test_reconnect():
    lakeshore = LakeShore336Simulator("TEST")

    lakeshore.reconnect()
    assert lakeshore.is_connected()


def test_info():
    lakeshore = LakeShore336Simulator("TEST")
    info = lakeshore.info()

    assert type(info) == tuple
    assert info[0] == "LakeShore"
    assert info[1] == "LSCI336"
    assert info[2] == "1234567/1234567"
    assert info[3] == 1.0


def test_get_temperature():
    with LakeShore336Simulator("TEST") as sim:
        assert -100.0 < sim.get_temperature("A") < 25.0


def test_get_pid_parameters():
    with LakeShore336Simulator("TEST") as sim:
        for output_channel in [1, 2]:
            sim.set_pid_parameters(output_channel, 1 * output_channel, 2 * output_channel, 3 * output_channel)
            assert sim.get_pid_parameters(output_channel) == (
                1 * output_channel,
                2 * output_channel,
                3 * output_channel,
            )


def test_get_heater_output():
    with LakeShore336Simulator("TEST") as sim:
        for output_channel in [1, 2]:
            sim.set_heater_output(output_channel, 3 * output_channel)
            assert sim.get_heater_output(output_channel) == 3 * output_channel


def test_get_selftest_result():
    with LakeShore336Simulator("TEST") as sim:
        assert sim.get_selftest_result() == SelfTestResult.NO_ERRORS_FOUND.value
