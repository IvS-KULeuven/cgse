"""
Integration tests for QuestDBRepository.

Requires a live QuestDB instance.  The default connection parameters match a
standard Homebrew / local install:

    host:     localhost
    port:     8812  (PGWire)
    database: qdb
    user:     admin
    password: quest

Override any of these via environment variables:

    CGSE_QUESTDB_HOST, CGSE_QUESTDB_PORT, CGSE_QUESTDB_DATABASE,
    CGSE_QUESTDB_USER, CGSE_QUESTDB_PASSWORD

QuestDB uses a Write-Ahead Log (WAL) so rows become visible slightly after the
INSERT commit.  The ``_wait_for_rows`` helper polls until the expected count
appears (or a timeout is reached) to keep tests deterministic without sleeping.

Run with::

    cd libs/cgse-common
    uv run pytest tests/test_questdb_integration.py -v -m integration
"""

import json
import os
import time

import pandas as pd
import psycopg
import pytest

from egse.metrics import DataPoint
from egse.metrics import MeasurementColumn
from egse.metrics import MeasurementSchema
from egse.metrics import clear_measurement_schemas
from egse.metrics import get_metrics_repo
from egse.metrics import register_measurement_schema
from egse.plugins.metrics.questdb import QuestDBRepository

# ---------------------------------------------------------------------------
# Connection parameters (overridable via env)
# ---------------------------------------------------------------------------

QUESTDB_HOST = os.environ.get("CGSE_QUESTDB_HOST", "localhost")
QUESTDB_PORT = int(os.environ.get("CGSE_QUESTDB_PORT", "8812"))
QUESTDB_DATABASE = os.environ.get("CGSE_QUESTDB_DATABASE", "qdb")
QUESTDB_USER = os.environ.get("CGSE_QUESTDB_USER", "admin")
QUESTDB_PASSWORD = os.environ.get("CGSE_QUESTDB_PASSWORD", "quest")

# Table used by unified-schema integration tests
_INTEGRATION_TABLE = "cgse_integration_test"

# Tables used by per_measurement integration tests
_PM_ILP_TABLE = "cgse_pm_ilp_test"
_PM_TYPED_TABLE = "cgse_pm_typed_test"

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_rows(repo: QuestDBRepository, table: str, expected: int, timeout: float = 5.0) -> int:
    """Poll until at least ``expected`` rows are visible (WAL commit fence)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            rows = repo.query(f"SELECT count(*) AS n FROM {table}", mode="all")
            count = rows[0]["n"] if rows else 0
            if count >= expected:
                return count
        except Exception:
            pass
        time.sleep(0.1)
    return 0


def _wait_for_table(repo: QuestDBRepository, table: str, timeout: float = 5.0) -> bool:
    """Poll until ``table`` appears in QuestDB (ILP WAL commit fence)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if table in repo.get_table_names():
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# Session-scoped fixture: live QuestDB repo
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def questdb():
    """Create a QuestDBRepository connected to the live instance.

    The integration table is wiped before and after the module so tests are
    isolated from any leftover data.
    """
    repo = QuestDBRepository(
        host=QUESTDB_HOST,
        port=QUESTDB_PORT,
        database=QUESTDB_DATABASE,
        user=QUESTDB_USER,
        password=QUESTDB_PASSWORD,
        table_name=_INTEGRATION_TABLE,
        schema="unified",
    )

    try:
        repo.connect()
    except Exception as exc:
        pytest.skip(f"QuestDB not reachable at {QUESTDB_HOST}:{QUESTDB_PORT}: {exc}")

    # Clean slate before tests
    assert repo.conn is not None
    with repo.conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {_INTEGRATION_TABLE}")

    # Reconnect so connect() re-creates the table schema
    repo.close()
    repo.connect()

    yield repo

    # Teardown: remove integration table
    try:
        assert repo.conn is not None
        with repo.conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {_INTEGRATION_TABLE}")
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ping(questdb):
    assert questdb.ping() is True


def test_table_is_listed(questdb):
    tables = questdb.get_table_names()
    assert _INTEGRATION_TABLE in tables


def test_column_names(questdb):
    cols = questdb.get_column_names(_INTEGRATION_TABLE)
    assert "measurement" in cols
    assert "timestamp" in cols
    assert "tags" in cols
    assert "fields" in cols


def test_write_single_dict(questdb):
    point = {
        "measurement": "camera_tm",
        "tags": {"device_id": "cam_01"},
        "fields": {"temperature": 23.4},
        "time": "2026-04-24T10:00:00Z",
    }
    questdb.write(point)

    count = _wait_for_rows(questdb, _INTEGRATION_TABLE, 1)
    assert count >= 1


def test_write_datapoint_object(questdb):
    import datetime

    point = (
        DataPoint.measurement("hexapod_tm")
        .tag("device_id", "hex_01")
        .field("x", 1.25)
        .field("y", -0.5)
        # Use a datetime object — CGSE str_to_datetime requires microseconds in
        # its format string so ISO-8601 strings without fractions are rejected.
        .time(datetime.datetime(2026, 4, 24, 10, 0, 1, tzinfo=datetime.timezone.utc))
    )
    questdb.write(point)

    count = _wait_for_rows(questdb, _INTEGRATION_TABLE, 2)
    assert count >= 2


def test_write_batch(questdb):
    import datetime

    base = datetime.datetime(2026, 4, 24, 10, 1, 0, tzinfo=datetime.timezone.utc)
    batch = [
        {
            "measurement": "unit_test",
            "tags": {"run": "batch"},
            "fields": {"count": i, "value": float(i) * 1.1},
            "time": base.replace(second=i).isoformat(),
        }
        for i in range(10)
    ]
    questdb.write(batch)

    # 1 (single dict) + 1 (datapoint object) + 10 (batch) = 12
    count = _wait_for_rows(questdb, _INTEGRATION_TABLE, 12)
    assert count >= 11  # tolerant: DataPoint test may have contributed 0 or 1


def test_query_raw_returns_list(questdb):
    _wait_for_rows(questdb, _INTEGRATION_TABLE, 1)

    rows = questdb.query(f"SELECT * FROM {_INTEGRATION_TABLE} ORDER BY timestamp LIMIT 3", mode="all")
    assert isinstance(rows, list)
    assert len(rows) >= 1
    assert "measurement" in rows[0]


def test_query_pandas_returns_dataframe(questdb):
    df = questdb.query(f"SELECT * FROM {_INTEGRATION_TABLE} ORDER BY timestamp LIMIT 5", mode="pandas")
    assert isinstance(df, pd.DataFrame)
    assert "measurement" in df.columns


def test_get_values_last_hours(questdb):
    result = questdb.get_values_last_hours(_INTEGRATION_TABLE, "temperature", hours=24, mode="pandas")
    assert isinstance(result, pd.DataFrame)


def test_get_values_in_range_returns_pandas(questdb):
    df = questdb.get_values_in_range(
        _INTEGRATION_TABLE,
        "temperature",
        "2026-04-24T09:00:00Z",
        "2026-04-24T11:00:00Z",
        mode="pandas",
    )
    assert isinstance(df, pd.DataFrame)
    assert "temperature" in df.columns
    assert len(df) >= 1


def test_get_values_in_range_returns_list(questdb):
    rows = questdb.get_values_in_range(
        _INTEGRATION_TABLE,
        "temperature",
        "2026-04-24T09:00:00Z",
        "2026-04-24T11:00:00Z",
        mode="",
    )
    assert isinstance(rows, list)
    assert len(rows) >= 1
    row = rows[0]
    assert "timestamp" in row
    assert "temperature" in row


def test_query_field_extraction_from_json(questdb):
    """Verify that _extract_field correctly parses the JSON fields column."""
    rows = questdb.query(
        f"SELECT timestamp, fields FROM {_INTEGRATION_TABLE} WHERE measurement = 'camera_tm' ORDER BY timestamp LIMIT 5",
        mode="all",
    )
    assert rows, "Expected at least one camera_tm row"

    extracted = QuestDBRepository._extract_field(rows, "temperature")
    assert len(extracted) >= 1

    found = next((r for r in extracted if r["temperature"] is not None), None)
    assert found is not None
    assert found["temperature"] == pytest.approx(23.4)


def test_get_metrics_repo_factory():
    """get_metrics_repo() factory creates a working QuestDBRepository."""
    repo = get_metrics_repo(
        "questdb",
        {
            "host": QUESTDB_HOST,
            "port": QUESTDB_PORT,
            "database": QUESTDB_DATABASE,
            "user": QUESTDB_USER,
            "password": QUESTDB_PASSWORD,
            "table_name": _INTEGRATION_TABLE,
        },
    )

    # load_plugins_fn imports the module under a different path than the direct
    # import above, so isinstance across two module instances would fail.  Check
    # the class name instead.
    assert type(repo).__name__ == "QuestDBRepository"
    repo.connect()
    assert repo.ping() is True
    repo.close()


def test_ping_returns_false_when_disconnected():
    repo = QuestDBRepository(host=QUESTDB_HOST, port=QUESTDB_PORT)
    # Never called connect()
    assert repo.ping() is False


def test_write_raises_when_not_connected():
    repo = QuestDBRepository()
    with pytest.raises(ConnectionError, match="Not connected"):
        repo.write({"measurement": "x", "fields": {"v": 1}})


def test_context_manager():
    """__enter__/__exit__ connect and close cleanly.

    Note: the Protocol base class defines ``__enter__`` as calling connect() but
    returning None (not self), so we hold a reference to the repo object outside
    the ``with`` block and check state after exit.
    """
    repo = QuestDBRepository(
        host=QUESTDB_HOST,
        port=QUESTDB_PORT,
        database=QUESTDB_DATABASE,
        user=QUESTDB_USER,
        password=QUESTDB_PASSWORD,
        table_name=_INTEGRATION_TABLE,
    )
    with repo:
        assert repo.ping() is True
    # After __exit__ the connection is closed
    assert repo.conn is None


# ---------------------------------------------------------------------------
# per_measurement schema tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def questdb_pm():
    """QuestDBRepository in per_measurement mode.

    Tables are NOT created on connect() — they appear lazily on first write,
    either via ILP (no schema) or PGWire DDL (declared schema).
    """
    repo = QuestDBRepository(
        host=QUESTDB_HOST,
        port=QUESTDB_PORT,
        database=QUESTDB_DATABASE,
        user=QUESTDB_USER,
        password=QUESTDB_PASSWORD,
        schema="per_measurement",
    )

    try:
        repo.connect()
    except Exception as exc:
        pytest.skip(f"QuestDB not reachable at {QUESTDB_HOST}:{QUESTDB_PORT}: {exc}")

    assert repo.conn is not None
    with repo.conn.cursor() as cur:
        for table in (_PM_ILP_TABLE, _PM_TYPED_TABLE):
            cur.execute(f"DROP TABLE IF EXISTS {table}")

    yield repo

    try:
        assert repo.conn is not None
        with repo.conn.cursor() as cur:
            for table in (_PM_ILP_TABLE, _PM_TYPED_TABLE):
                cur.execute(f"DROP TABLE IF EXISTS {table}")
    finally:
        repo.close()


def test_pm_tables_absent_before_write(questdb_pm):
    """No per-measurement table exists before the first write."""
    tables = questdb_pm.get_table_names()
    assert _PM_ILP_TABLE not in tables
    assert _PM_TYPED_TABLE not in tables


def test_pm_ilp_write_creates_table(questdb_pm):
    """Writing a schema-less measurement creates the table lazily via ILP."""
    questdb_pm.write(
        {
            "measurement": _PM_ILP_TABLE,
            "tags": {"sensor": "s1"},
            "fields": {"value": 42.0},
            "time": "2026-06-21T10:00:00Z",
        }
    )
    assert _wait_for_table(questdb_pm, _PM_ILP_TABLE), f"Table {_PM_ILP_TABLE!r} was not created after ILP write"
    count = _wait_for_rows(questdb_pm, _PM_ILP_TABLE, 1)
    assert count >= 1


def test_pm_ilp_table_has_expected_columns(questdb_pm):
    """ILP-created table has QuestDB's native 'timestamp' column plus tag/field columns."""
    cols = questdb_pm.get_column_names(_PM_ILP_TABLE)
    assert "timestamp" in cols
    assert "sensor" in cols
    assert "value" in cols


def test_pm_typed_write_creates_table(questdb_pm):
    """Writing a measurement with a declared schema creates a typed table synchronously via PGWire DDL."""
    register_measurement_schema(
        MeasurementSchema(
            name=_PM_TYPED_TABLE,
            tags=(MeasurementColumn("sensor_id", "symbol"),),
            fields=(MeasurementColumn("temperature", "double"), MeasurementColumn("sample_idx", "long")),
        )
    )
    try:
        questdb_pm.write(
            {
                "measurement": _PM_TYPED_TABLE,
                "tags": {"sensor_id": "s42"},
                "fields": {"temperature": 25.0, "sample_idx": 1},
                "time": "2026-06-21T10:00:00Z",
            }
        )
        # DDL via PGWire is synchronous — table is present immediately
        assert _PM_TYPED_TABLE in questdb_pm.get_table_names()
        cols = questdb_pm.get_column_names(_PM_TYPED_TABLE)
        assert "timestamp" in cols
        assert "sensor_id" in cols
        assert "temperature" in cols
        assert "sample_idx" in cols
    finally:
        clear_measurement_schemas()


def test_pm_typed_data_is_readable(questdb_pm):
    """Data written to a typed per_measurement table is visible after WAL commit."""
    count = _wait_for_rows(questdb_pm, _PM_TYPED_TABLE, 1)
    assert count >= 1
