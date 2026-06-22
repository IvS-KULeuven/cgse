import datetime

import pandas
import pytest

from egse.metrics import MeasurementColumn
from egse.metrics import MeasurementSchema
from egse.metrics import clear_measurement_schemas
from egse.metrics import register_measurement_schema
from egse.plugins.metrics.questdb import QuestDBRepository
from egse.plugins.metrics.questdb import get_repository_class


def _query_text(query) -> str:
    if isinstance(query, str):
        return query
    text = str(query)
    if text and text != repr(query):
        return text
    return repr(query)


def _query_contains(query: str, literal_sql: str, identifier: str | None = None) -> bool:
    if literal_sql in query:
        return True
    if identifier and f"Identifier('{identifier}')" in query:
        return True
    return False


def _has_column_definition(query: str, column_name: str, data_type: str) -> bool:
    if f'"{column_name}" {data_type}' in query:
        return True
    return f"Identifier('{column_name}')" in query and f"SQL('{data_type}')" in query


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, query, params=None):
        query_text = _query_text(query)
        self.conn.executed.append((query_text, params))
        self.description = [("col",)]

        if "SELECT 1" in query_text:
            self.conn.rows = [{"?column?": 1}]
        elif "SELECT table_name FROM tables()" in query_text:
            self.conn.rows = [{"table_name": "timeseries"}]
        elif "SHOW COLUMNS FROM" in query_text:
            # Let tests control per-measurement columns via schema_columns dict.
            for table_name, cols in self.conn.schema_columns.items():
                if f'"{table_name}"' in query_text or f"Identifier('{table_name}')" in query_text:
                    self.conn.rows = [{"column": c} for c in cols]
                    return
            if "typed_metrics" in query_text:
                self.conn.rows = [{"column": "timestamp"}, {"column": "temperature"}]
            else:
                self.conn.rows = [{"column": "measurement"}, {"column": "timestamp"}, {"column": "fields"}]
        elif "SELECT timestamp, fields" in query_text:
            self.conn.rows = [
                {
                    "timestamp": datetime.datetime(2026, 4, 24, 12, 0, tzinfo=datetime.timezone.utc),
                    "fields": '{"temperature": 22.5}',
                }
            ]
        elif (
            "SELECT timestamp" in query_text
            and "fields" not in query_text
            and ("temperature" in query_text or "Identifier('temperature')" in query_text)
        ):
            self.conn.rows = [
                {
                    "timestamp": datetime.datetime(2026, 4, 24, 12, 0, tzinfo=datetime.timezone.utc),
                    "temperature": 22.5,
                }
            ]
        else:
            self.conn.rows = []
            self.description = None

    def executemany(self, query, rows):
        self.conn.executed_many.append((_query_text(query), rows))

    def fetchall(self):
        return self.conn.rows

    def fetchone(self):
        if self.conn.rows:
            return self.conn.rows[0]
        return None


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.executed_many = []
        self.rows = []
        self.closed = False
        # Map measurement name -> list of column_name strings that the fake
        # 'information_schema.columns' query will return.  Populated by tests
        # that register schemas so the column-existence check always passes.
        self.schema_columns: dict[str, list[str]] = {}

    def cursor(self, row_factory=None):
        return FakeCursor(self)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clear_registry():
    clear_measurement_schemas()
    yield
    clear_measurement_schemas()


def test_connect_creates_table(monkeypatch):
    fake_conn = FakeConnection()

    def fake_connect(**kwargs):
        assert kwargs["host"] == "localhost"
        assert kwargs["port"] == 8812
        return fake_conn

    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", fake_connect)

    repo = QuestDBRepository(schema="unified")
    repo.connect()

    assert repo.conn is fake_conn
    assert any(
        _query_contains(query, 'CREATE TABLE IF NOT EXISTS "timeseries"', "timeseries")
        for query, _ in fake_conn.executed
    )


def test_ping_query_and_close(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    repo = QuestDBRepository(schema="unified")
    repo.connect()

    assert repo.ping() is True

    rows = repo.query("SELECT table_name FROM tables()", mode="all")
    assert rows == [{"table_name": "timeseries"}]

    frame = repo.query("SELECT table_name FROM tables()", mode="pandas")
    assert isinstance(frame, pandas.DataFrame)
    assert list(frame["table_name"]) == ["timeseries"]

    with pytest.raises(ValueError, match="Invalid mode"):
        repo.query("SELECT 1", mode="unsupported")

    repo.close()
    assert fake_conn.closed is True


def test_write_and_helpers(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    repo = QuestDBRepository(table_name="metrics", schema="unified")
    repo.connect()

    repo.write(
        [
            {
                "measurement": "camera_tm",
                "tags": {"device_id": "cam_01"},
                "fields": {"temperature": 23.4},
                "time": "2026-04-24T12:00:00Z",
            }
        ]
    )

    assert len(fake_conn.executed_many) == 1
    insert_query, rows = fake_conn.executed_many[0]
    assert _query_contains(insert_query, 'INSERT INTO "metrics"', "metrics")
    assert len(rows) == 1
    assert rows[0][0] == "camera_tm"

    assert repo.get_table_names() == ["timeseries"]
    assert repo.get_column_names("metrics") == ["measurement", "timestamp", "fields"]

    values = repo.get_values_last_hours("metrics", "temperature", hours=1, mode="")
    assert len(values) == 1
    assert values[0]["temperature"] == 22.5

    values_range = repo.get_values_in_range("metrics", "temperature", "2026-04-24", "2026-04-25", mode="")
    assert len(values_range) == 1
    assert values_range[0]["temperature"] == 22.5


def test_get_repository_class():
    assert get_repository_class() is QuestDBRepository


def test_write_uses_declared_measurement_schema(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    register_measurement_schema(
        MeasurementSchema(
            name="synthetic_load",
            tags=(MeasurementColumn("device_id", "symbol"), MeasurementColumn("profile", "symbol")),
            fields=(MeasurementColumn("temperature", "double"), MeasurementColumn("sample_idx", "long")),
        )
    )

    # Pre-populate fake schema_columns so the column-existence verification in
    # _ensure_schema_table succeeds (simulates the table being freshly created).
    fake_conn.schema_columns["synthetic_load"] = ["timestamp", "device_id", "profile", "temperature", "sample_idx"]

    repo = QuestDBRepository(schema="per_measurement")
    repo.connect()
    repo.write(
        {
            "measurement": "synthetic_load",
            "tags": {"device_id": "srcA_000", "profile": "source-A"},
            "fields": {"temperature": 21.5, "sample_idx": 42},
            "time": "2026-04-24T12:00:00Z",
        }
    )

    create_queries = [
        query
        for query, _ in fake_conn.executed
        if "CREATE TABLE IF NOT EXISTS" in query
        and _query_contains(query, 'CREATE TABLE IF NOT EXISTS "synthetic_load"', "synthetic_load")
    ]
    assert len(create_queries) == 1
    # SYMBOL is mapped to VARCHAR for PGWire DDL compatibility
    assert _has_column_definition(create_queries[0], "device_id", "VARCHAR")
    assert _has_column_definition(create_queries[0], "profile", "VARCHAR")
    assert _has_column_definition(create_queries[0], "temperature", "DOUBLE")
    assert _has_column_definition(create_queries[0], "sample_idx", "LONG")

    insert_query, rows = fake_conn.executed_many[-1]
    assert _query_contains(
        insert_query,
        'INSERT INTO "synthetic_load" ("timestamp", "device_id", "profile", "temperature", "sample_idx")',
        "synthetic_load",
    )
    assert rows[0][1:] == ("srcA_000", "source-A", 21.5, 42)


def test_write_rejects_unknown_declared_fields(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    register_measurement_schema(
        MeasurementSchema(
            name="synthetic_load",
            tags=(MeasurementColumn("device_id", "symbol"),),
            fields=(MeasurementColumn("temperature", "double"),),
        )
    )

    fake_conn.schema_columns["synthetic_load"] = ["timestamp", "device_id", "temperature"]

    repo = QuestDBRepository(schema="per_measurement")
    repo.connect()

    with pytest.raises(ValueError, match="does not match declared schema"):
        repo.write(
            {
                "measurement": "synthetic_load",
                "tags": {"device_id": "srcA_000"},
                "fields": {"temperature": 21.5, "sample_idx": 42},
                "time": "2026-04-24T12:00:00Z",
            }
        )


def test_line_protocol_schema_is_supported(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    repo = QuestDBRepository(schema="line_protocol")
    repo.connect()

    assert repo.schema == "line_protocol"
    # line_protocol mode should not create unified table on connect.
    assert not any('CREATE TABLE IF NOT EXISTS "timeseries"' in query for query, _ in fake_conn.executed)


def test_write_line_protocol_posts_to_ilp_endpoint(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    class _Response:
        status_code = 204
        text = ""

    captured: dict[str, object] = {}

    def fake_post(url, params, data, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("egse.plugins.metrics.questdb.requests.post", fake_post)

    repo = QuestDBRepository(schema="line_protocol", host="questdb.local", ilp_port=9000)
    repo.connect()
    repo.write(
        {
            "measurement": "camera_tm",
            "tags": {"device_id": "cam_01"},
            "fields": {"temperature": 23.4, "counter": 3},
            "time": "2026-04-24T12:00:00Z",
        }
    )

    assert captured["url"] == "http://questdb.local:9000/write"
    assert captured["params"] == {"precision": "n"}
    assert captured["headers"] == {"Content-Type": "text/plain; charset=utf-8"}
    assert captured["timeout"] == 5.0
    body = captured["data"]
    assert isinstance(body, bytes)
    text_body = body.decode("utf-8")
    assert text_body.startswith("camera_tm,device_id=cam_01 ")
    assert "temperature=23.4" in text_body
    assert "counter=3i" in text_body


def test_write_line_protocol_raises_on_http_error(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    class _Response:
        status_code = 400
        text = "invalid line protocol"

    monkeypatch.setattr("egse.plugins.metrics.questdb.requests.post", lambda *args, **kwargs: _Response())

    repo = QuestDBRepository(schema="line_protocol")
    repo.connect()

    with pytest.raises(RuntimeError, match="QuestDB line protocol write failed"):
        repo.write({"measurement": "cpu", "fields": {"value": 1}})


def test_get_values_helpers_support_typed_tables(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    repo = QuestDBRepository(schema="per_measurement")
    repo.connect()

    values = repo.get_values_last_hours("typed_metrics", "temperature", hours=1, mode="")
    assert len(values) == 1
    assert values[0]["temperature"] == 22.5

    values_range = repo.get_values_in_range("typed_metrics", "temperature", "2026-04-24", "2026-04-25", mode="")
    assert len(values_range) == 1
    assert values_range[0]["temperature"] == 22.5


def test_per_measurement_fallback_uses_line_protocol(monkeypatch):
    fake_conn = FakeConnection()
    monkeypatch.setattr("egse.plugins.metrics.questdb.psycopg.connect", lambda **kwargs: fake_conn)

    class _Response:
        status_code = 204
        text = ""

    captured: dict[str, object] = {}

    def fake_post(url, params, data, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["data"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("egse.plugins.metrics.questdb.requests.post", fake_post)

    repo = QuestDBRepository(schema="per_measurement", host="questdb.local", ilp_port=9000)
    repo.connect()
    repo.write(
        {
            "measurement": "fallback_measurement",
            "tags": {"device_id": "cam_01"},
            "fields": {"temperature": 23.4},
            "timestamp": "2026-04-24T12:00:00Z",
        }
    )

    assert captured["url"] == "http://questdb.local:9000/write"
    assert captured["params"] == {"precision": "n"}
    assert captured["headers"] == {"Content-Type": "text/plain; charset=utf-8"}
    assert captured["timeout"] == 5.0
    body = captured["data"]
    assert isinstance(body, bytes)
    text_body = body.decode("utf-8")
    assert text_body.startswith("fallback_measurement,device_id=cam_01 ")
    assert "temperature=23.4" in text_body
    # No PGWire INSERTs should happen for fallback measurements.
    assert fake_conn.executed_many == []
