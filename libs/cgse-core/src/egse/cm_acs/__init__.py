"""Async Configuration Manager (CM-ACS) module.

This module is intentionally separated from ``egse.confman`` so async and sync
configuration manager implementations can coexist during migration.
"""

from __future__ import annotations

from pathlib import Path

from egse.env import get_site_id
from egse.settings import Settings

HERE = Path(__file__).parent

settings = Settings.load("Configuration Manager Async Control Server")

PROCESS_NAME = settings.get("PROCESS_NAME", "cm_acs")
PROTOCOL = settings.get("PROTOCOL", "tcp")
HOSTNAME = settings.get("HOSTNAME", "localhost")
COMMANDING_PORT = settings.get("COMMANDING_PORT", 0)
SERVICE_PORT = settings.get("SERVICE_PORT", 0)
MONITORING_PORT = settings.get("MONITORING_PORT", 0)
STORAGE_MNEMONIC = settings.get("STORAGE_MNEMONIC", "CM_ASYNC")
SERVICE_TYPE = settings.get("SERVICE_TYPE", "cm_acs")

PROXY_TIMEOUT = 10.0


def get_active_site_id() -> str:
    """Return the current SITE_ID from the environment."""

    site_id = get_site_id()
    if site_id is None:
        raise ValueError("SITE_ID is not set in the environment.")
    return site_id
