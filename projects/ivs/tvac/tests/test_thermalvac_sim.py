"""Tests for the status of the ThermalVac OPC UA simulator and the `cgse tvac` subcommands."""

import socket

import pytest

from egse.ivs.tvac.tvac_sim import ThermalVacSimulator
from egse.ivs.tvac.tvac_sim import read_status
from ivs_tvac.cgse_services import tvac


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_read_status_of_a_running_simulator():
    port = free_port()

    async with ThermalVacSimulator(hostname="127.0.0.1", port=port):
        info = await read_status(hostname="127.0.0.1", port=port)

    assert info["server_url"] == f"opc.tcp://127.0.0.1:{port}"
    assert info["tvac_state"] == "Idle"
    assert -25.0 < info["avg_temperature"] < 25.0
    assert 0.0 < info["vessel_pressure"] < 1100.0
    assert info["data_logging_active"] is False


async def test_read_status_when_the_simulator_is_not_running():
    with pytest.raises(OSError):
        await read_status(hostname="127.0.0.1", port=free_port(), timeout=2.0)


def test_cgse_tvac_subcommands():
    names = [command.name for command in tvac.registered_commands]

    assert names == ["start", "stop", "status", "start-sim", "stop-sim", "status-sim"]
