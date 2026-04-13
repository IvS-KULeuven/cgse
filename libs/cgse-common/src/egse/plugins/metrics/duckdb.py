__all__ = [
    "DuckDBRepository",
    "get_repository_class",
]
import json
from datetime import datetime
from typing import Any
from typing import Dict
from typing import List

import duckdb

from egse.metrics import DataPoint
from egse.metrics import TimeSeriesRepository


class DuckDBRepository(TimeSeriesRepository):
    """
    DuckDB TimeSeriesRepository implementation.

    DuckDB stores time-series data in a table with columns for:
    - measurement: The measurement name (like table name in InfluxDB)
    - timestamp: Time column
    - tags: JSON object storing tag key-value pairs
    - fields: JSON object storing field key-value pairs
    """

    def __init__(self, db_path: str, table_name: str = "timeseries"):
        """
        Initialize DuckDB repository.

        Args:
            db_path: Path to DuckDB database file (or ":memory:" for in-memory)
            table_name: Name of the main timeseries table
        """
        self.db_path = db_path
        self.table_name = table_name
        self.conn = None

    def connect(self) -> None:
        """Connect to DuckDB database and create schema."""
        try:
            self.conn = duckdb.connect(self.db_path)

            # Create main timeseries table if it doesn't exist
            self.conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    measurement VARCHAR NOT NULL,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    tags JSON,
                    fields JSON,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indices for better query performance
            self.conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_measurement
                ON {self.table_name}(measurement)
            """
            )

            self.conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_timestamp
                ON {self.table_name}(timestamp)
            """
            )

            # Create a view that flattens the JSON for easier querying
            self.conn.execute(
                f"""
                CREATE OR REPLACE VIEW {self.table_name}_flat AS
                SELECT
                    measurement,
                    timestamp,
                    tags,
                    fields,
                    created_at,
                    -- Extract all tag keys and values
                    json_extract_string(tags, '$.*') as tag_values,
                    -- Extract all field keys and values
                    json_extract_string(fields, '$.*') as field_values
                FROM {self.table_name}
            """
            )

        except Exception as e:
            raise ConnectionError(f"Failed to connect to DuckDB at {self.db_path}: {e}")

    def ping(self) -> bool:
        """Return True if the DuckDB connection is alive, False otherwise."""
        if self.conn is None:
            return False
        try:
            self.conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def write(self, points: DataPoint | dict | List[DataPoint | dict]) -> None:
        """Write data points to DuckDB.

        Accepts a single or a list of `DataPoint` objects or plain dicts in the `DataPoint.as_dict()`
        format, i.e. `{"measurement": ..., "tags": {...}, "fields": {...}, "time": ...}`.
        """
        if not self.conn:
            raise ConnectionError("Not connected. Call connect() first.")

        if not points:
            return

        if not isinstance(points, list):
            points = [points]

        # Prepare data for bulk insert
        data = []
        for point in points:
            if isinstance(point, dict):
                measurement = point.get("measurement", "unknown")
                # DataPoint.as_dict() uses "time"; allow "timestamp" as fallback
                timestamp = point.get("time") or point.get("timestamp")
                tags = point.get("tags") or {}
                fields = point.get("fields") or {}
            else:
                measurement = point.measurement
                timestamp = point.timestamp
                tags = point.tags or {}
                fields = point.fields or {}

            # Normalize timestamp to ISO string
            if timestamp is None:
                timestamp = datetime.now().isoformat()
            elif isinstance(timestamp, (int, float)):
                timestamp = datetime.fromtimestamp(timestamp).isoformat()
            elif isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    timestamp = dt.isoformat()
                except ValueError:
                    timestamp = datetime.now().isoformat()

            data.append(
                {
                    "measurement": measurement,
                    "timestamp": timestamp,
                    "tags": json.dumps(tags) if isinstance(tags, dict) else tags,
                    "fields": json.dumps(fields) if isinstance(fields, dict) else fields,
                }
            )

        try:
            # Use prepared statement for bulk insert
            placeholders = ", ".join(["(?, ?, ?, ?)"] * len(data))
            values = []
            for row in data:
                values.extend([row["measurement"], row["timestamp"], row["tags"], row["fields"]])

            self.conn.execute(
                f"""
                INSERT INTO {self.table_name} (measurement, timestamp, tags, fields)
                VALUES {placeholders}
            """,
                values,
            )

        except Exception as e:
            raise RuntimeError(f"Failed to write data points: {e}")

    def query(self, query_str: str) -> List[Dict]:
        """Execute SQL query and return results."""
        if self.conn is None:
            raise ConnectionError("Not connected. Call connect() first.")

        try:
            assert self.conn.description is not None  # for type checker

            result = self.conn.execute(query_str).fetchall()
            columns = [desc[0] for desc in self.conn.description]

            # Convert to list of dictionaries
            return [dict(zip(columns, row)) for row in result]

        except Exception as e:
            raise RuntimeError(f"Failed to execute query: {e}")

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    # Schema exploration methods
    def get_tables(self) -> List[str]:
        """Get all measurements (equivalent to tables)."""
        try:
            query = f"SELECT DISTINCT measurement FROM {self.table_name} ORDER BY measurement"
            results = self.query(query)
            return [row["measurement"] for row in results]
        except Exception as exc:
            print(f"Error getting measurements: {exc}")
            return []

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get column information for a measurement."""
        try:
            # Get basic schema
            columns = [
                {"column_name": "measurement", "data_type": "VARCHAR", "is_nullable": "NO"},
                {"column_name": "timestamp", "data_type": "TIMESTAMPTZ", "is_nullable": "YES"},
                {"column_name": "tags", "data_type": "JSON", "is_nullable": "YES"},
                {"column_name": "fields", "data_type": "JSON", "is_nullable": "YES"},
                {"column_name": "created_at", "data_type": "TIMESTAMPTZ", "is_nullable": "YES"},
            ]

            # Get unique tag keys for this measurement
            tag_query = f"""
                SELECT DISTINCT json_extract_string(tags, '$.' || key) as tag_key
                FROM {table_name},
                     unnest(json_object_keys(json(tags))) as key
                WHERE measurement = ?
                AND tags IS NOT NULL
                AND tags != '{{}}'
            """

            try:
                assert self.conn is not None  # for type checker

                tag_results = self.conn.execute(tag_query, [table_name]).fetchall()
                for row in tag_results:
                    if row[0]:  # tag_key is not null
                        columns.append(
                            {
                                "column_name": f"tag_{row[0]}",
                                "data_type": "VARCHAR",
                                "is_nullable": "YES",
                                "column_type": "tag",
                            }
                        )
            except Exception:
                pass  # If JSON extraction fails, skip tag columns

            # Get unique field keys for this measurement
            field_query = f"""
                SELECT DISTINCT json_extract_string(fields, '$.' || key) as field_key
                FROM {table_name},
                     unnest(json_object_keys(json(fields))) as key
                WHERE measurement = ?
                AND fields IS NOT NULL
                AND fields != '{{}}'
            """

            try:
                assert self.conn is not None  # for type checker

                field_results = self.conn.execute(field_query, [table_name]).fetchall()
                for row in field_results:
                    if row[0]:  # field_key is not null
                        columns.append(
                            {
                                "column_name": f"field_{row[0]}",
                                "data_type": "DOUBLE",
                                "is_nullable": "YES",
                                "column_type": "field",
                            }
                        )
            except Exception:
                pass  # If JSON extraction fails, skip field columns

            return columns

        except Exception as e:
            print(f"Error getting columns for {table_name}: {e}")
            return []

    def get_schema_info(self, table_name: str) -> Dict[str, Any]:
        """Get detailed schema information for a measurement."""
        columns = self.get_columns(table_name)

        schema = {
            "table_name": table_name,
            "time_column": None,
            "tag_columns": [],
            "field_columns": [],
            "other_columns": [],
        }

        for col in columns:
            col_name = col["column_name"]
            col_type = col.get("column_type", "")

            if col_name == "timestamp":
                schema["time_column"] = col
            elif col_type == "tag" or col_name.startswith("tag_"):
                schema["tag_columns"].append(col)
            elif col_type == "field" or col_name.startswith("field_"):
                schema["field_columns"].append(col)
            else:
                schema["other_columns"].append(col)

        # Add row count
        try:
            count_result = self.query(f"SELECT COUNT(*) as count FROM {table_name} WHERE measurement = '{table_name}'")
            schema["row_count"] = count_result[0]["count"] if count_result else 0
        except Exception:
            schema["row_count"] = 0

        return schema

    def inspect_database(self) -> Dict[str, Any]:
        """Get complete database schema information."""
        measurements = self.get_tables()

        database_info = {
            "database_path": self.db_path,
            "main_table": self.table_name,
            "total_measurements": len(measurements),
            "measurements": {},
        }

        # Get total row count
        try:
            total_rows = self.query(f"SELECT COUNT(*) as count FROM {self.table_name}")
            database_info["total_rows"] = total_rows[0]["count"] if total_rows else 0
        except Exception:
            database_info["total_rows"] = 0

        # Get schema info for each measurement
        for measurement in measurements:
            database_info["measurements"][measurement] = self.get_schema_info(measurement)

        return database_info

    def query_latest(self, measurement: str, limit: int = 20) -> List[Dict]:
        """Get latest records for a measurement."""
        try:
            assert self.conn is not None  # for type checker
            assert self.conn.description is not None  # for type checker

            query = f"""
                SELECT measurement, timestamp, tags, fields, created_at
                FROM {self.table_name}
                WHERE measurement = ?
                ORDER BY timestamp DESC, created_at DESC
                LIMIT ?
            """

            result = self.conn.execute(query, [measurement, limit]).fetchall()
            columns = [desc[0] for desc in self.conn.description]

            # Convert to list of dictionaries and parse JSON
            records = []
            for row in result:
                record = dict(zip(columns, row))

                # Parse JSON fields
                try:
                    record["tags"] = json.loads(record["tags"]) if record["tags"] else {}
                except (json.JSONDecodeError, TypeError):
                    record["tags"] = {}

                try:
                    record["fields"] = json.loads(record["fields"]) if record["fields"] else {}
                except (json.JSONDecodeError, TypeError):
                    record["fields"] = {}

                records.append(record)

            return records

        except Exception as e:
            print(f"Error getting latest records for {measurement}: {e}")
            return []

    def get_measurements_with_stats(self) -> List[Dict[str, Any]]:
        """Get measurements with statistics."""
        try:
            query = f"""
                SELECT
                    measurement,
                    COUNT(*) as record_count,
                    MIN(timestamp) as earliest_timestamp,
                    MAX(timestamp) as latest_timestamp,
                    COUNT(DISTINCT json_object_keys(json(tags))) as unique_tag_keys,
                    COUNT(DISTINCT json_object_keys(json(fields))) as unique_field_keys
                FROM {self.table_name}
                GROUP BY measurement
                ORDER BY record_count DESC
            """

            return self.query(query)

        except Exception as e:
            print(f"Error getting measurement statistics: {e}")
            return []

    def query_by_tags(self, measurement: str, tags: Dict[str, str], limit: int = 100) -> List[Dict]:
        """Query records by measurement and tag filters."""
        try:
            assert self.conn is not None  # for type checker
            assert self.conn.description is not None  # for type checker

            # Build tag filter conditions
            tag_conditions = []
            params = [measurement]

            for tag_key, tag_value in tags.items():
                tag_conditions.append(f"json_extract_string(tags, '$.{tag_key}') = ?")
                params.append(tag_value)

            where_clause = " AND ".join(tag_conditions)
            if where_clause:
                where_clause = f" AND {where_clause}"

            query = f"""
                SELECT measurement, timestamp, tags, fields, created_at
                FROM {self.table_name}
                WHERE measurement = ?{where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """

            params.append(limit)

            result = self.conn.execute(query, params).fetchall()
            columns = [desc[0] for desc in self.conn.description]

            # Convert to list of dictionaries and parse JSON
            records = []
            for row in result:
                record = dict(zip(columns, row))

                # Parse JSON fields
                try:
                    record["tags"] = json.loads(record["tags"]) if record["tags"] else {}
                except (json.JSONDecodeError, TypeError):
                    record["tags"] = {}

                try:
                    record["fields"] = json.loads(record["fields"]) if record["fields"] else {}
                except (json.JSONDecodeError, TypeError):
                    record["fields"] = {}

                records.append(record)

            return records

        except Exception as e:
            print(f"Error querying by tags: {e}")
            return []

    def aggregate_by_time(
        self, measurement: str, field_name: str, time_bucket: str = "1 hour", aggregation: str = "AVG"
    ) -> List[Dict]:
        """Aggregate field values by time buckets."""
        try:
            agg_func = aggregation.upper()
            if agg_func not in ["AVG", "SUM", "COUNT", "MIN", "MAX"]:
                raise ValueError(f"Unsupported aggregation function: {aggregation}")

            query = f"""
                SELECT
                    date_trunc('{time_bucket}', timestamp) as time_bucket,
                    {agg_func}(CAST(json_extract_string(fields, '$.{field_name}') AS DOUBLE)) as {field_name}_{agg_func.lower()}
                FROM {self.table_name}
                WHERE measurement = ?
                AND json_extract_string(fields, '$.{field_name}') IS NOT NULL
                GROUP BY date_trunc('{time_bucket}', timestamp)
                ORDER BY time_bucket
            """

            return self.query(query.replace("?", f"'{measurement}'"))

        except Exception as e:
            print(f"Error in time aggregation: {e}")
            return []


def get_repository_class() -> type[TimeSeriesRepository]:
    """Return the repository class for the plugin manager."""
    return DuckDBRepository
