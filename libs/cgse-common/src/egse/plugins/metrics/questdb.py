import json
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import cast

import pandas
import psycopg
from psycopg import sql
from psycopg.abc import Query
from psycopg.rows import dict_row

from egse.metrics import MeasurementSchema
from egse.metrics import PointLike
from egse.metrics import TimeSeriesRepository
from egse.metrics import get_measurement_schema

__all__ = [
    "QuestDBRepository",
    "get_repository_class",
]


SCHEMA_UNIFIED = "unified"
SCHEMA_PER_MEASUREMENT = "per_measurement"


class QuestDBRepository(TimeSeriesRepository):
    """TimeSeriesRepository implementation backed by QuestDB over PGWire.

    Two schema modes are supported (``schema`` parameter):

    ``"unified"`` (default)
        All measurements are stored in a single table (``table_name``, default
        ``"timeseries"``) with columns ``(measurement SYMBOL, time TIMESTAMP,
        tags VARCHAR, fields VARCHAR)``.  Simple but mixes all measurements.

    ``"per_measurement"``
        Each measurement gets its own table named after the measurement (e.g.
        ``DAQ6510``), with columns ``(time TIMESTAMP, tags VARCHAR, fields
        VARCHAR)`` by default. When a measurement schema is declared in the
        shared metrics registry, the table is created with native typed columns
        instead. This preserves the generic fallback while allowing stable
        measurements to be stored efficiently.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8812,
        database: str = "qdb",
        user: str = "admin",
        password: str = "quest",
        table_name: str = "timeseries",
        schema: str = SCHEMA_UNIFIED,
    ):
        if schema not in (SCHEMA_UNIFIED, SCHEMA_PER_MEASUREMENT):
            raise ValueError(f"schema must be '{SCHEMA_UNIFIED}' or '{SCHEMA_PER_MEASUREMENT}', got {schema!r}")
        # QuestDB requires timestamps to be inserted in strictly increasing order.
        # Concurrent flushes can arrive out-of-order, so we must serialize writes.
        self.max_flush_concurrency: int = 1
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table_name = table_name
        self.schema = schema
        self.conn: psycopg.Connection[Any] | None = None
        self._ping_conn: psycopg.Connection[Any] | None = None
        self._created_tables: set[str] = set()

    def _make_connection(self) -> psycopg.Connection[Any]:
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            row_factory=cast(Any, dict_row),
            autocommit=True,
        )

    def _reconnect_ping_conn(self) -> bool:
        """Recreate the dedicated ping connection.

        QuestDB may drop idle PGWire connections. Status checks should recover
        from that transparently instead of permanently reporting unreachable.
        """
        try:
            if self._ping_conn is not None:
                self._ping_conn.close()
        except Exception:
            pass

        try:
            self._ping_conn = self._make_connection()
            return True
        except Exception:
            self._ping_conn = None
            return False

    def connect(self) -> None:
        self.conn = self._make_connection()
        self._ping_conn = self._make_connection()

        assert self.conn is not None
        if self.schema == SCHEMA_UNIFIED:
            with self.conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            measurement SYMBOL,
                            time TIMESTAMP,
                            tags VARCHAR,
                            fields VARCHAR
                        ) TIMESTAMP(time) PARTITION BY DAY
                        """
                    ).format(sql.Identifier(self.table_name))
                )
            self._created_tables.add(self.table_name)

    def ping(self) -> bool:
        if self.conn is None:
            return False

        if self._ping_conn is None and not self._reconnect_ping_conn():
            return False

        for _ in range(2):
            try:
                assert self._ping_conn is not None
                with self._ping_conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                return True
            except Exception:
                if not self._reconnect_ping_conn():
                    break

        return False

    @staticmethod
    def _to_datetime(value: Any) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)

        if isinstance(value, datetime):
            return value

        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)

        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.now(timezone.utc)

        return datetime.now(timezone.utc)

    @staticmethod
    def _to_dict(point: PointLike | dict) -> dict[str, Any]:
        if isinstance(point, dict):
            return point
        return point.as_dict()

    @staticmethod
    def _questdb_type(data_type: str) -> str:
        mapping = {
            # SYMBOL is a QuestDB-native type only supported via ILP; when writing
            # via PGWire DDL, use VARCHAR instead so the column is created and
            # accessible correctly.  Data is coerced to str either way.
            "symbol": "VARCHAR",
            "string": "VARCHAR",
            "varchar": "VARCHAR",
            "long": "LONG",
            "double": "DOUBLE",
            "boolean": "BOOLEAN",
            "timestamp": "TIMESTAMP",
        }
        normalized = data_type.strip().lower()
        if normalized not in mapping:
            raise ValueError(f"Unsupported QuestDB data type {data_type!r}")
        return mapping[normalized]

    @staticmethod
    def _coerce_value(value: Any, data_type: str) -> Any:
        if value is None:
            return None

        normalized = data_type.strip().lower()
        if normalized in ("symbol", "string", "varchar"):
            return str(value)
        if normalized == "long":
            return int(value)
        if normalized == "double":
            return float(value)
        if normalized == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in ("true", "1", "yes", "on"):
                    return True
                if lowered in ("false", "0", "no", "off"):
                    return False
                raise ValueError(f"Cannot coerce {value!r} to boolean")
            return bool(value)
        if normalized == "timestamp":
            return QuestDBRepository._to_datetime(value)

        raise ValueError(f"Unsupported QuestDB data type {data_type!r}")

    @staticmethod
    def _validate_schema_payload(measurement: str, payload: dict[str, Any], schema: MeasurementSchema) -> None:
        tags = payload.get("tags") or {}
        fields = payload.get("fields") or {}
        tag_names = {column.name for column in schema.tags}
        field_names = {column.name for column in schema.fields}

        unknown_tags = sorted(set(tags) - tag_names)
        unknown_fields = sorted(set(fields) - field_names)
        if unknown_tags or unknown_fields:
            raise ValueError(
                f"Measurement {measurement!r} does not match declared schema; "
                f"unknown tags={unknown_tags}, unknown fields={unknown_fields}"
            )

    def _ensure_schema_table(self, measurement: str, schema: MeasurementSchema) -> None:
        if measurement in self._created_tables:
            return

        columns: list[sql.Composable] = [sql.SQL("time TIMESTAMP")]
        for column in schema.tags:
            columns.append(
                sql.SQL("{} {}").format(
                    sql.Identifier(column.name), sql.SQL(cast(Any, self._questdb_type(column.data_type)))
                )
            )
        for column in schema.fields:
            columns.append(
                sql.SQL("{} {}").format(
                    sql.Identifier(column.name), sql.SQL(cast(Any, self._questdb_type(column.data_type)))
                )
            )

        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        {}
                    ) TIMESTAMP(time) PARTITION BY DAY
                    """
                ).format(sql.Identifier(measurement), sql.SQL(", ").join(columns))
            )

        # Verify that the table actually has the expected columns.  If the table
        # pre-existed with a different layout (e.g. a prior generic-fallback table
        # with 'tags'/'fields' JSON columns) the CREATE above is a no-op and
        # subsequent typed INSERTs will fail with confusing errors.
        expected = {"time"} | {c.name for c in schema.tags} | {c.name for c in schema.fields}
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                (measurement,),
            )
            actual = {row["column_name"] for row in cur.fetchall()}

        missing = expected - actual
        if missing:
            raise RuntimeError(
                f"Table {measurement!r} exists but is missing expected columns {sorted(missing)}. "
                f"The table may have been created with a different schema (e.g. a generic fallback "
                f"table). Drop the table or rename your measurement to continue with typed writes."
            )

        self._created_tables.add(measurement)

    def _write_schema_rows(self, measurement: str, schema: MeasurementSchema, payloads: list[dict[str, Any]]) -> None:
        assert self.conn is not None

        rows: list[tuple[Any, ...]] = []
        for payload in payloads:
            self._validate_schema_payload(measurement, payload, schema)
            tags = payload.get("tags") or {}
            fields = payload.get("fields") or {}
            timestamp = self._to_datetime(payload.get("time") or payload.get("timestamp"))
            row: list[Any] = [timestamp]
            for column in schema.tags:
                row.append(self._coerce_value(tags.get(column.name), column.data_type))
            for column in schema.fields:
                row.append(self._coerce_value(fields.get(column.name), column.data_type))
            rows.append(tuple(row))

        column_names = ["time"]
        column_names.extend(column.name for column in schema.tags)
        column_names.extend(column.name for column in schema.fields)

        with self.conn.cursor() as cur:
            cur.executemany(
                sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(measurement),
                    sql.SQL(", ").join(sql.Identifier(name) for name in column_names),
                    sql.SQL(", ").join(sql.Placeholder() for _ in column_names),
                ),
                rows,
            )

    def write(self, points: PointLike | dict | list[PointLike | dict]) -> None:
        if self.conn is None:
            raise ConnectionError("Not connected. Call connect() first.")

        if not points:
            return

        if not isinstance(points, list):
            points = [points]

        if self.schema == SCHEMA_UNIFIED:
            rows: list[tuple[str, datetime, str, str]] = []
            for point in points:
                payload = self._to_dict(point)
                measurement = str(payload.get("measurement", "unknown"))
                timestamp = self._to_datetime(payload.get("time") or payload.get("timestamp"))
                tags = payload.get("tags") or {}
                fields = payload.get("fields") or {}
                rows.append((measurement, timestamp, json.dumps(tags), json.dumps(fields)))

            with self.conn.cursor() as cur:
                cur.executemany(
                    sql.SQL("INSERT INTO {} (measurement, time, tags, fields) VALUES (%s, %s, %s, %s)").format(
                        sql.Identifier(self.table_name)
                    ),
                    rows,
                )
        else:
            # Group by measurement so we can batch inserts per table
            by_measurement: dict[str, list[dict[str, Any]]] = {}
            for point in points:
                payload = self._to_dict(point)
                measurement = str(payload.get("measurement", "unknown"))
                by_measurement.setdefault(measurement, []).append(payload)

            for measurement, payloads in by_measurement.items():
                schema = get_measurement_schema(measurement)
                if schema is not None:
                    self._ensure_schema_table(measurement, schema)
                    self._write_schema_rows(measurement, schema, payloads)
                    continue

                mrows: list[tuple[datetime, str, str]] = []
                for payload in payloads:
                    timestamp = self._to_datetime(payload.get("time") or payload.get("timestamp"))
                    tags = payload.get("tags") or {}
                    fields = payload.get("fields") or {}
                    mrows.append((timestamp, json.dumps(tags), json.dumps(fields)))

                self._ensure_measurement_table(measurement)
                with self.conn.cursor() as cur:
                    cur.executemany(
                        sql.SQL("INSERT INTO {} (time, tags, fields) VALUES (%s, %s, %s)").format(
                            sql.Identifier(measurement)
                        ),
                        mrows,
                    )

    def query(
        self,
        query_str: str | Query,
        mode: str = "all",
        params: Sequence[Any] | None = None,
    ) -> Any:
        if self.conn is None:
            raise ConnectionError("Not connected. Call connect() first.")

        with self.conn.cursor() as cur:
            if params is None:
                cur.execute(cast(Any, query_str))
            else:
                cur.execute(cast(Any, query_str), params)
            rows = cur.fetchall() if cur.description else []

        if mode == "pandas":
            return pandas.DataFrame(rows)
        if mode in ("all", ""):
            return rows

        raise ValueError(f"Invalid mode '{mode}', use 'all', or 'pandas'.")

    def _ensure_measurement_table(self, measurement: str) -> None:
        """Create the per-measurement table if it doesn't exist yet (cached)."""
        if measurement in self._created_tables:
            return
        assert self.conn is not None
        with self.conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        time TIMESTAMP,
                        tags VARCHAR,
                        fields VARCHAR
                    ) TIMESTAMP(time) PARTITION BY DAY
                    """
                ).format(sql.Identifier(measurement))
            )
        self._created_tables.add(measurement)

    def get_measurement_names(self) -> list[str]:
        """Return distinct measurement names.

        For ``per_measurement`` schema this is the same as ``get_table_names()``.
        For ``unified`` schema this queries the distinct values in the
        ``measurement`` column of the unified table.
        """
        if self.schema == SCHEMA_PER_MEASUREMENT:
            return self.get_table_names()
        rows = self.query(
            sql.SQL("SELECT DISTINCT measurement FROM {} ORDER BY measurement").format(sql.Identifier(self.table_name)),
            mode="all",
        )
        return [row["measurement"] for row in rows]

    def get_table_names(self) -> list[str]:
        rows = self.query("SELECT table_name FROM tables()", mode="all")
        return [row["table_name"] for row in rows]

    def get_column_names(self, table_name: str) -> list[str]:
        rows = self.query(
            sql.SQL("SHOW COLUMNS FROM {}").format(sql.Identifier(table_name)),
            mode="all",
        )
        return [row["column"] for row in rows if "column" in row]

    def get_values_last_hours(
        self,
        table_name: str,
        column_name: str,
        hours: int,
        mode: str = "pandas",
        measurement: str | None = None,
    ) -> Any:
        """Return rows from the last *hours* hours.

        For the ``unified`` schema, *table_name* is the unified table name and
        *measurement* can be supplied to filter by a specific measurement.
        For the ``per_measurement`` schema, *table_name* is the measurement
        name directly and *measurement* is ignored.
        """
        if self.schema == SCHEMA_UNIFIED and measurement is not None:
            query = sql.SQL(
                """
                SELECT time, fields
                FROM {}
                WHERE time >= dateadd('h', -%s, now())
                  AND measurement = %s
                ORDER BY time DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(int(hours), measurement))
        else:
            query = sql.SQL(
                """
                SELECT time, fields
                FROM {}
                WHERE time >= dateadd('h', -%s, now())
                ORDER BY time DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(int(hours),))
        parsed = self._extract_field(rows, column_name)
        if mode == "pandas":
            return pandas.DataFrame(parsed)
        return parsed

    def get_values_in_range(
        self,
        table_name: str,
        column_name: str,
        start_time: str,
        end_time: str,
        mode: str = "pandas",
        measurement: str | None = None,
    ) -> Any:
        """Return rows between *start_time* and *end_time*.

        For the ``unified`` schema, *table_name* is the unified table name and
        *measurement* can be supplied to filter by a specific measurement.
        For the ``per_measurement`` schema, *table_name* is the measurement
        name directly and *measurement* is ignored.
        """
        if self.schema == SCHEMA_UNIFIED and measurement is not None:
            query = sql.SQL(
                """
                SELECT time, fields
                FROM {}
                WHERE time >= %s
                  AND time < %s
                  AND measurement = %s
                ORDER BY time DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(start_time, end_time, measurement))
        else:
            query = sql.SQL(
                """
                SELECT time, fields
                FROM {}
                WHERE time >= %s
                  AND time < %s
                ORDER BY time DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(start_time, end_time))
        parsed = self._extract_field(rows, column_name)
        if mode == "pandas":
            return pandas.DataFrame(parsed)
        return parsed

    @staticmethod
    def _extract_field(rows: list[dict[str, Any]], column_name: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows:
            fields = row.get("fields")
            if isinstance(fields, str):
                try:
                    fields = json.loads(fields)
                except json.JSONDecodeError:
                    fields = {}
            if not isinstance(fields, dict):
                fields = {}

            result.append({"time": row.get("time"), column_name: fields.get(column_name)})

        return result

    def close(self) -> None:
        if self._ping_conn:
            self._ping_conn.close()
            self._ping_conn = None
        if self.conn:
            self.conn.close()
            self.conn = None


def get_repository_class() -> type[TimeSeriesRepository]:
    return QuestDBRepository
