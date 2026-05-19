import datetime

import pytest

from egse.metrics import MeasurementColumn
from egse.metrics import MeasurementSchema
from egse.metrics import clear_measurement_schemas
from egse.metrics import register_measurement_schema
from egse.plugins.metrics.duckdb import DuckDBRepository


class FakeDuckConnection:
    def __init__(self):
        self.executed: list[tuple[str, object]] = []
        self.description = [("col",)]
        self._rows: list[tuple] = []
        self.closed = False

    def execute(self, query: str, params=None):
        self.executed.append((query, params))

        lower = query.strip().lower()
        if lower.startswith("select 1"):
            self.description = [("one",)]
            self._rows = [(1,)]
        return self

    def fetchall(self):
        return self._rows

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clear_registry():
    clear_measurement_schemas()
    yield
    clear_measurement_schemas()


def test_write_uses_declared_measurement_schema(monkeypatch):
    fake_conn = FakeDuckConnection()
    monkeypatch.setattr("egse.plugins.metrics.duckdb.duckdb.connect", lambda *args, **kwargs: fake_conn)

    register_measurement_schema(
        MeasurementSchema(
            name="synthetic_load",
            tags=(MeasurementColumn("device_id", "symbol"), MeasurementColumn("profile", "symbol")),
            fields=(MeasurementColumn("temperature", "double"), MeasurementColumn("sample_idx", "long")),
        )
    )

    repo = DuckDBRepository(db_path=":memory:")
    repo.connect()
    repo.write(
        {
            "measurement": "synthetic_load",
            "tags": {"device_id": "srcA_000", "profile": "source-A"},
            "fields": {"temperature": 21.5, "sample_idx": 42},
            "time": "2026-04-24T12:00:00Z",
        }
    )

    create_queries = [q for q, _ in fake_conn.executed if 'CREATE TABLE IF NOT EXISTS "synthetic_load"' in q]
    assert len(create_queries) == 1
    assert '"device_id" VARCHAR' in create_queries[0]
    assert '"profile" VARCHAR' in create_queries[0]
    assert '"temperature" DOUBLE' in create_queries[0]
    assert '"sample_idx" BIGINT' in create_queries[0]

    insert_ops = [(q, p) for q, p in fake_conn.executed if 'INSERT INTO "synthetic_load"' in q]
    assert len(insert_ops) == 1
    _, params = insert_ops[0]
    assert params is not None
    assert params[1:] == ["srcA_000", "source-A", 21.5, 42]


def test_write_falls_back_to_generic_table_without_schema(monkeypatch):
    fake_conn = FakeDuckConnection()
    monkeypatch.setattr("egse.plugins.metrics.duckdb.duckdb.connect", lambda *args, **kwargs: fake_conn)

    repo = DuckDBRepository(db_path=":memory:")
    repo.connect()
    repo.write(
        {
            "measurement": "camera_tm",
            "tags": {"device_id": "cam_01"},
            "fields": {"temperature": 19.0},
            "time": datetime.datetime(2026, 4, 24, 12, 0, tzinfo=datetime.timezone.utc),
        }
    )

    generic_insert = [q for q, _ in fake_conn.executed if "INSERT INTO timeseries" in q]
    assert len(generic_insert) == 1
