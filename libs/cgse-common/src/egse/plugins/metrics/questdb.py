import json
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import cast

import pandas
import psycopg
import requests
from psycopg import sql
from psycopg.abc import Query
from psycopg.rows import dict_row

from egse.metrics import MeasurementSchema
from egse.metrics import PointLike
from egse.metrics import TimeSeriesRepository
from egse.metrics import get_measurement_schema
from egse.plugins.metrics.line_protocol import to_line_protocol

__all__ = [
    "QuestDBRepository",
    "get_repository_class",
]


SCHEMA_UNIFIED = "unified"
SCHEMA_PER_MEASUREMENT = "per_measurement"
SCHEMA_LINE_PROTOCOL = "line_protocol"


class QuestDBRepository(TimeSeriesRepository):
    """TimeSeriesRepository implementation backed by QuestDB over PGWire.

    Three schema modes are supported (`schema` parameter):

    `"unified"`
        All measurements are stored in a single table (`table_name`, default
        `"timeseries"`) with columns `(measurement SYMBOL, time TIMESTAMP,
        tags VARCHAR, fields VARCHAR)`.  Simple but mixes all measurements.
        Use this schema for maximum flexibility (e.g. when measurement schemas
        are not known in advance or may change frequently) or when you want
        to query across measurements. The `tags` and `fields` columns store
        JSON-encoded dictionaries of the respective values. Best for prototyping.

    `"per_measurement"`
        Each measurement gets its own table named after the measurement (e.g.
        `DAQ6510`), with columns `(time TIMESTAMP, tags VARCHAR, fields
        VARCHAR)` by default. When a measurement schema is declared in the
        shared metrics registry, the table is created with native typed columns
        and writes are validated/coerced via PGWire. If no schema is declared,
        points are written via line protocol ingestion so QuestDB infers typed
        columns.

    `"line_protocol"`
        Data points are serialized to line protocol and written through QuestDB's
        HTTP ingress endpoint. Tags become SYMBOL columns and fields become typed
        columns inferred by QuestDB from line protocol values.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8812,
        database: str = "qdb",
        user: str = "admin",
        password: str = "quest",
        table_name: str = "timeseries",
        schema: str = SCHEMA_PER_MEASUREMENT,
        ilp_port: int = 9000,
        ilp_path: str = "/write",
        ilp_timeout: float = 5.0,
        ilp_precision: str = "n",
    ):
        if schema not in (SCHEMA_UNIFIED, SCHEMA_PER_MEASUREMENT, SCHEMA_LINE_PROTOCOL):
            raise ValueError(
                "schema must be "
                f"'{SCHEMA_UNIFIED}', '{SCHEMA_PER_MEASUREMENT}', or '{SCHEMA_LINE_PROTOCOL}', "
                f"got {schema!r}"
            )
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
        self.ilp_port = int(ilp_port)
        self.ilp_path = ilp_path if ilp_path.startswith("/") else f"/{ilp_path}"
        self.ilp_timeout = float(ilp_timeout)
        self.ilp_precision = ilp_precision
        self.conn: psycopg.Connection[Any] | None = None
        self._ping_conn: psycopg.Connection[Any] | None = None
        self._created_tables: set[str] = set()

    def _ilp_url(self) -> str:
        return f"http://{self.host}:{self.ilp_port}{self.ilp_path}"

    def _write_line_protocol(self, payloads: list[dict[str, Any]]) -> None:
        # Accept payloads that use 'timestamp' as an alias of 'time'.
        normalized_payloads: list[dict[str, Any]] = []
        for payload in payloads:
            if "time" in payload or "timestamp" not in payload:
                normalized_payloads.append(payload)
                continue
            normalized = dict(payload)
            normalized["time"] = payload.get("timestamp")
            normalized_payloads.append(normalized)

        lines = [line for payload in normalized_payloads if (line := to_line_protocol(payload))]
        if not lines:
            return

        response = requests.post(
            self._ilp_url(),
            params={"precision": self.ilp_precision},
            data="\n".join(lines).encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=self.ilp_timeout,
        )

        if response.status_code >= 300:
            body = response.text.strip()
            details = f": {body}" if body else ""
            raise RuntimeError(f"QuestDB line protocol write failed with HTTP {response.status_code}{details}")

    def _make_connection(self) -> psycopg.Connection[Any]:
        """Create a new connection to QuestDB. This is used for both the main connection and the
        dedicated ping connection. Separating the ping connection allows us to transparently recover
        from idle timeouts on that connection without affecting the main connection used for writes
        and queries."""

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

    def _reconnect_main_conn(self) -> bool:
        """Recreate the main write connection after an unexpected server disconnect.

        QuestDB may close PGWire connections (e.g. due to a server restart or an
        internal error during DDL). This method attempts a transparent reconnect so
        that the next write can retry without requiring a MetricsHub restart.
        The _created_tables cache is kept intact because the tables still exist in
        QuestDB after a reconnect.
        """
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass
        self.conn = None

        try:
            self.conn = self._make_connection()
            return True
        except Exception:
            return False

    def connect(self) -> None:
        """Establish connection to QuestDB and create the unified table if using unified schema.
        For the per-measurement schema, tables are created lazily on first write.
        A separate connection is established for pinging to allow transparent recovery from
        idle timeouts without affecting the main connection used for writes and queries.
        """

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
                            timestamp TIMESTAMP,
                            tags VARCHAR,
                            fields VARCHAR
                        ) TIMESTAMP(timestamp) PARTITION BY DAY
                        """
                    ).format(sql.Identifier(self.table_name))
                )
            self._created_tables.add(self.table_name)

    def ping(self) -> bool:
        """Check if the connection to QuestDB is alive by executing a simple query on a dedicated ping connection.
        If the ping connection is not established or has been dropped (e.g. due to idle timeout), attempt
        to reconnect it. This allows transparent recovery from idle timeouts without affecting the main connection.
        """
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
        """Convert a value to a timezone-aware datetime in UTC."""
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
        """Convert a PointLike or dict to a dict. If it's already a dict, return it as-is."""
        if isinstance(point, dict):
            return point
        return point.as_dict()

    @staticmethod
    def _questdb_type(data_type: str) -> str:
        """Map a generic data type to a QuestDB-specific type for table creation."""
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
        """Coerce a value to the appropriate type for QuestDB based on the declared data type.
        This is used for typed writes in the per-measurement schema. If the value is None,
        return None (QuestDB will store it as NULL). For non-None values, coerce to the
        appropriate type based on the data_type string.

        If the value cannot be coerced, raise a ValueError.
        This ensures that data is stored in the correct format in QuestDB and that type errors are caught early.

        The supported data types are 'symbol', 'string', 'varchar' (all coerced to str),
        'long' (coerced to int), 'double' (coerced to float), 'boolean' (coerced to bool
        with flexible string parsing), and 'timestamp' (coerced to datetime).
        """
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
        """Validate that the tags and fields in the payload match the declared schema for the measurement.
        This is used for typed writes in the per-measurement schema. It checks that all tags and fields
        in the payload are declared in the schema, and raises a ValueError if there are any unknown tags or fields.
        This helps catch errors where the payload does not conform to the expected schema for the measurement,
        which could lead to data quality issues or failed inserts."""

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
        """Create a table for the measurement with typed columns based on the declared schema,
        if it doesn't exist yet (cached). If the table already exists but does not have the
        expected columns, raise an error to avoid silent data corruption from schema mismatches.
        """

        if measurement in self._created_tables:
            return

        columns: list[sql.Composable] = [sql.SQL("timestamp TIMESTAMP")]
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
                    ) TIMESTAMP(timestamp) PARTITION BY DAY
                    """
                ).format(sql.Identifier(measurement), sql.SQL(", ").join(columns))
            )

        # Verify that the table actually has the expected columns.  If the table
        # pre-existed with a different layout (e.g. a prior generic-fallback table
        # with 'tags'/'fields' JSON columns) the CREATE above is a no-op and
        # subsequent typed INSERTs will fail with confusing errors.
        expected = {"timestamp"} | {c.name for c in schema.tags} | {c.name for c in schema.fields}
        actual = set(self.get_column_names(measurement))

        missing = expected - actual
        if missing:
            raise RuntimeError(
                f"Table {measurement!r} exists but is missing expected columns {sorted(missing)}. "
                f"The table may have been created with a different schema (e.g. a generic fallback "
                f"table). Drop the table or rename your measurement to continue with typed writes."
            )

        self._created_tables.add(measurement)

    def _write_schema_rows(self, measurement: str, schema: MeasurementSchema, payloads: list[dict[str, Any]]) -> None:
        """Write rows for a measurement with a declared schema. This is used for typed writes in
        the per-measurement schema.
        It validates each payload against the schema, coerces values to the appropriate types, and inserts them
        into the measurement's table. If any payload does not conform to the schema, a ValueError is raised
        and no data is written for that batch. This ensures data integrity by enforcing the declared schema
        for the measurement.
        """
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

        column_names = ["timestamp"]
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
        """Write one or more points to QuestDB.

        If the server closes the connection unexpectedly (e.g. during a DDL statement
        for a new measurement table), the connection is transparently re-established and
        the batch is retried once before raising.
        """
        if self.conn is None:
            raise ConnectionError("Not connected. Call connect() first.")

        if not points:
            return

        if not isinstance(points, list):
            points = [points]

        try:
            self._write_impl(points)
        except psycopg.OperationalError:
            if not self._reconnect_main_conn():
                raise
            self._write_impl(points)

    def _write_impl(self, points: list[PointLike | dict]) -> None:
        """Internal write implementation. Callers must ensure points is a non-empty list."""

        if self.schema == SCHEMA_LINE_PROTOCOL:
            payloads = [self._to_dict(point) for point in points]
            self._write_line_protocol(payloads)
            return

        if self.schema == SCHEMA_UNIFIED:
            rows: list[tuple[str, datetime, str, str]] = []
            for point in points:
                payload = self._to_dict(point)
                measurement = str(payload.get("measurement", "unknown"))
                timestamp = self._to_datetime(payload.get("time") or payload.get("timestamp"))
                tags = payload.get("tags") or {}
                fields = payload.get("fields") or {}
                rows.append((measurement, timestamp, json.dumps(tags), json.dumps(fields)))

            with self.conn.cursor() as cur:  # type: ignore[union-attr]
                cur.executemany(
                    sql.SQL("INSERT INTO {} (measurement, timestamp, tags, fields) VALUES (%s, %s, %s, %s)").format(
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

                # Fallback for measurements without a declared schema: write via
                # line protocol so QuestDB creates inferred typed columns.
                self._write_line_protocol(payloads)

    def query(
        self,
        query_str: str | Query,
        mode: str = "all",
        params: Sequence[Any] | None = None,
    ) -> Any:
        """Execute a SQL query against QuestDB and return the results. The query can be a string or a psycopg Query
        object. The mode parameter controls the format of the returned results: 'all' returns a list of dicts,
        while 'pandas' returns a pandas DataFrame. If params are provided, they are passed to the execute method
        for parameterized queries.

        This method can be used for ad-hoc queries or for more complex queries that are not covered by the other methods
        in this class.
        """
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

    def get_measurement_names(self) -> list[str]:
        """Return distinct measurement names.

        For `per_measurement` and `line_protocol` schemas this is the same as
        `get_table_names()`.
        For `unified` schema this queries the distinct values in the
        `measurement` column of the unified table.
        """
        if self.schema in {SCHEMA_PER_MEASUREMENT, SCHEMA_LINE_PROTOCOL}:
            return self.get_table_names()
        rows = self.query(
            sql.SQL("SELECT DISTINCT measurement FROM {} ORDER BY measurement").format(sql.Identifier(self.table_name)),
            mode="all",
        )
        return [row["measurement"] for row in rows]

    def get_table_names(self) -> list[str]:
        """Return the list of table names in QuestDB. For the per-measurement schema,
        each measurement has its own table, so this returns the list of measurements.
        For the unified schema, there is only one table (self.table_name), so this
        returns a list containing just that table name.
        """
        rows = self.query("SELECT table_name FROM tables()", mode="all")
        return [row["table_name"] for row in rows]

    def get_column_names(self, table_name: str) -> list[str]:
        """Return the list of column names for the given table.
        This queries the information_schema.columns view in QuestDB to get the column
        names for the specified table. This is used to verify that a table has the
        expected columns after creation, and can also be used for introspection or
        debugging purposes.
        """
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

        For the `unified` schema, *table_name* is the unified table name and
        *measurement* can be supplied to filter by a specific measurement.
        For the `per_measurement` and `line_protocol` schemas, *table_name* is
        the measurement name directly and *measurement* is ignored.
        """
        has_fields_json = "fields" in set(self.get_column_names(table_name))

        if has_fields_json and self.schema == SCHEMA_UNIFIED and measurement is not None:
            query = sql.SQL(
                """
                SELECT timestamp, fields
                FROM {}
                WHERE timestamp >= dateadd('h', -%s, now())
                  AND measurement = %s
                ORDER BY timestamp DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(int(hours), measurement))
        elif has_fields_json:
            query = sql.SQL(
                """
                SELECT timestamp, fields
                FROM {}
                WHERE timestamp >= dateadd('h', -%s, now())
                ORDER BY timestamp DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(int(hours),))
        else:
            query = sql.SQL(
                """
                SELECT timestamp, {}
                FROM {}
                WHERE timestamp >= dateadd('h', -%s, now())
                ORDER BY timestamp DESC
                """
            ).format(sql.Identifier(column_name), sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(int(hours),))

        parsed = self._extract_field(rows, column_name) if has_fields_json else self._extract_value(rows, column_name)
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

        For the `unified` schema, *table_name* is the unified table name and
        *measurement* can be supplied to filter by a specific measurement.
        For the `per_measurement` and `line_protocol` schemas, *table_name* is
        the measurement name directly and *measurement* is ignored.
        """
        has_fields_json = "fields" in set(self.get_column_names(table_name))

        if has_fields_json and self.schema == SCHEMA_UNIFIED and measurement is not None:
            query = sql.SQL(
                """
                SELECT timestamp, fields
                FROM {}
                WHERE timestamp >= %s
                  AND timestamp < %s
                  AND measurement = %s
                ORDER BY timestamp DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(start_time, end_time, measurement))
        elif has_fields_json:
            query = sql.SQL(
                """
                SELECT timestamp, fields
                FROM {}
                WHERE timestamp >= %s
                  AND timestamp < %s
                ORDER BY timestamp DESC
                """
            ).format(sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(start_time, end_time))
        else:
            query = sql.SQL(
                """
                SELECT timestamp, {}
                FROM {}
                WHERE timestamp >= %s
                  AND timestamp < %s
                ORDER BY timestamp DESC
                """
            ).format(sql.Identifier(column_name), sql.Identifier(table_name))
            rows = self.query(query, mode="all", params=(start_time, end_time))

        parsed = self._extract_field(rows, column_name) if has_fields_json else self._extract_value(rows, column_name)
        if mode == "pandas":
            return pandas.DataFrame(parsed)
        return parsed

    @staticmethod
    def _extract_value(rows: list[dict[str, Any]], column_name: str) -> list[dict[str, Any]]:
        """Extract a typed column value from query results."""
        return [{"timestamp": row.get("timestamp"), column_name: row.get(column_name)} for row in rows]

    @staticmethod
    def _extract_field(rows: list[dict[str, Any]], column_name: str) -> list[dict[str, Any]]:
        """Extract a specific field from the 'fields' JSON column in the query results.
        This is used by the get_values_last_hours and get_values_in_range methods to return a list of dicts
        containing the timestamp and the value of the specified field for each row in the result set.
        If the 'fields' column is not a valid JSON string or does not contain the specified field,
        the value will be returned as None for that row.
        """
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

            result.append({"timestamp": row.get("timestamp"), column_name: fields.get(column_name)})

        return result

    def close(self) -> None:
        """Close the connections to QuestDB. This should be called when the repository is
        no longer needed to clean up resources."""
        if self._ping_conn:
            self._ping_conn.close()
            self._ping_conn = None
        if self.conn:
            self.conn.close()
            self.conn = None


def get_repository_class() -> type[TimeSeriesRepository]:
    """Return the TimeSeriesRepository class implemented by this plugin."""
    return QuestDBRepository
