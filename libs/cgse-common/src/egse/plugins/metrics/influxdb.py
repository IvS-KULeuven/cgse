"""
A TimeSeriesRepository implementation for the InfluxDB3 database.

An example query:

    import os
    from egse.metrics import get_metrics_repo

    token = os.environ.get("INFLUXDB3_AUTH_TOKEN")
    project = os.environ.get("PROJECT")

    influxdb = get_metrics_repo("influxdb", {"host": "http://localhost:8181", "database": project, "token": token})
    influxdb.connect()

    df = influxdb.query("SELECT * FROM cm ORDER BY TIME LIMIT 20")

    influxdb.close()

Other queries:

    SHOW TABLES;
        - this is equivalent to using `get_table_names()`

    SHOW COLUMNS IN cm;
        - this is equivalent to using `get_column_names()`

"""

__all__ = [
    "InfluxDBRepository",
    "get_repository_class",
]

import logging
import math
from datetime import datetime
from datetime import timezone

import pandas
import pyarrow
from influxdb_client_3 import InfluxDBClient3
from influxdb_client_3 import Point  # still used for non-dict inputs
from influxdb_client_3 import write_client_options
from influxdb_client_3.exceptions.exceptions import InfluxDB3ClientError
from influxdb_client_3.write_client.client.write_api import WriteType
from influxdb_client_3.write_client.domain.write_precision import WritePrecision

from egse.env import bool_env
from egse.env import int_env
from egse.env import str_env
from egse.metrics import PointLike
from egse.metrics import TimeSeriesRepository
from egse.system import type_name

logger = logging.getLogger("egse.plugins")


# Callback functions executed by the InfluxDB Client write API on success, error, and retry events.
# These can be used for logging or custom handling of write outcomes.
def success_callback(conf, data):
    pass


def error_callback(conf, data, exception):
    logger.error(f"[INFLUX ERROR] {exception}")


def retry_callback(conf, data, exception):
    logger.warning(f"[INFLUX RETRY] {exception}")


class InfluxDBRepository(TimeSeriesRepository):
    """TimeSeriesRepository implementation for InfluxDB3.

    Handles connection and interaction with an InfluxDB time series database, providing methods for writing points,
    querying data, retrieving table and column names, and fetching values within specific time ranges.
    Supports context management and configurable write options.
    """

    def __init__(self, host: str, database: str, token: str):
        self.host = host
        self.database = database
        self.token = token
        self.metrics_time_precision = WritePrecision.NS

        self.client: InfluxDBClient3 = None  # type: ignore

    def _load_client_options(self):
        self._batch_size = int_env("CGSE_INFLUX_BATCH_SIZE", 1_000)
        self._flush_interval = int_env("CGSE_INFLUX_FLUSH_MS", 1_000)
        self._retry_interval = int_env("CGSE_INFLUX_RETRY_MS", 3_000)
        self._max_retry_delay = int_env("CGSE_INFLUX_RETRY_MAX_DELAY_MS", 3_000)
        self._max_retry_time = int_env("CGSE_INFLUX_RETRY_MAX_TIME_MS", 6_000, minimum=0)
        self._max_retries = int_env("CGSE_INFLUX_MAX_RETRIES", 5, minimum=0)
        self._no_sync = bool_env("CGSE_INFLUX_NO_SYNC", default=True)
        self._write_type_env = str_env("CGSE_INFLUX_WRITE_TYPE", default="async")
        self._write_type = WriteType.asynchronous
        if self._write_type_env:
            match self._write_type_env.strip().lower():
                case "batch":
                    self._write_type = WriteType.batching
                case "async":
                    self._write_type = WriteType.asynchronous
                case "sync":
                    self._write_type = WriteType.synchronous

    def connect(self) -> None:
        self._load_client_options()

        wco = write_client_options(
            write_type=self._write_type,
            batch_size=self._batch_size,
            flush_interval=self._flush_interval,
            retry_interval=self._retry_interval,
            max_retries=self._max_retries,
            max_retry_delay=self._max_retry_delay,
            max_retry_time=self._max_retry_time,
            no_sync=self._no_sync,
            write_precision=self.metrics_time_precision,
            success_handler=success_callback,
            error_handler=error_callback,
            retry_handler=retry_callback,
        )
        self.client = InfluxDBClient3(host=self.host, database=self.database, token=self.token, write_options=wco)

    def ping(self) -> bool:
        """Return True if the InfluxDB server is reachable, False otherwise."""
        if self.client is None:
            return False
        try:
            self.client.query("SHOW TABLES")
            return True
        except Exception as exc:
            logger.warning(f"InfluxDB ping failed: {exc}")
            return False

    def _to_point(self, payload: PointLike | Point | dict) -> Point:
        """Return an InfluxDB `Point` from either a `Point` or DataPoint-style dict.

        Args:
            payload: Either an existing `Point` instance or a dictionary with
                `measurement`, optional `tags`, optional `fields`, and optional
                `time` (Unix seconds or ISO-8601 string).

        Returns:
            A populated `Point` object ready for writing.

        Notes:
            This method is primarily a compatibility path. For dictionary payloads,
            `write` prefers line-protocol conversion via `_to_line_protocol`
            for lower per-point overhead.
        """
        if isinstance(payload, Point):
            return payload

        if not isinstance(payload, dict):
            payload = payload.as_dict()

        measurement = payload["measurement"]
        point = Point(measurement)

        for key, value in payload.get("tags", {}).items():
            point.tag(key, value)

        for key, value in payload.get("fields", {}).items():
            point.field(key, value)

        timestamp = payload.get("time")
        if isinstance(timestamp, (int, float)):
            point.time(datetime.fromtimestamp(timestamp, tz=timezone.utc))
        elif isinstance(timestamp, str):
            point.time(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))

        return point

    def write(self, points: PointLike | dict | list[PointLike | dict]) -> None:
        """Write one or many points to InfluxDB.

        Args:
            points: A single `Point`, a DataPoint-style dictionary, or a mixed
                list of both.

        Behavior:
            - `dict` payloads are converted to line protocol using `_to_line_protocol`
                for performance.
            - `Point` payloads are passed through as-is.
            - Invalid `dict` payloads (e.g. missing measurement/fields) are skipped.
            - If no valid records remain, no write call is issued.

        Notes:
            Records are written using `self.metrics_time_precision`.
        """
        if isinstance(points, list):
            # Fast path: convert dicts directly to line protocol strings, avoiding
            # the overhead of creating Point objects for every field/tag value.
            lp: list[str] = []
            point_objects: list[Point] = []
            for p in points:
                if isinstance(p, dict):
                    line = self._to_line_protocol(p)
                    if line:
                        lp.append(line)
                elif isinstance(p, Point):
                    point_objects.append(p)
                else:
                    line = self._to_line_protocol(p.as_dict())
                    if line:
                        lp.append(line)
            records: list = lp + point_objects  # type: ignore[assignment]
        elif isinstance(points, dict):
            line = self._to_line_protocol(points)
            records = [line] if line else []
        elif isinstance(points, Point):
            records = [points]
        else:
            line = self._to_line_protocol(points.as_dict())
            records = [line] if line else []

        if records:
            self.client.write(record=records, write_precision=self.metrics_time_precision)

    @staticmethod
    def _to_line_protocol(payload: dict) -> str | None:
        """Convert a DataPoint-style dict to an InfluxDB line protocol string.

        Args:
            payload: Dictionary with `measurement`, optional `tags`, `fields`,
                and optional `time`.

        Returns:
            A line-protocol string when conversion succeeds, otherwise `None`.

        Rules:
            - Missing/empty measurement returns `None`.
            - `fields` must contain at least one supported non-`None` value,
              otherwise `None` is returned.
            - `tags` with `None` values are skipped.
            - Float `NaN`/`Inf` values are skipped.
            - `time` supports Unix seconds (int/float) or ISO-8601 string and is
              emitted as nanoseconds.
        """
        measurement = payload.get("measurement", "")
        if not measurement:
            return None

        fields = payload.get("fields") or {}
        tags = payload.get("tags") or {}
        timestamp = payload.get("time")

        def _esc(s: str) -> str:
            """Escape commas, equals signs, and spaces in tag/field keys and tag values."""
            return s.replace(",", "\\,").replace("=", "\\=").replace(" ", "\\ ")

        def _field_val(v: object) -> str | None:
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, int):
                return f"{v}i"
            if isinstance(v, float):
                if not math.isfinite(v):
                    return None
                return repr(v)
            if isinstance(v, str):
                return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
            return None

        # measurement[,tag=val ...]
        meas_escaped = measurement.replace(",", "\\,").replace(" ", "\\ ")
        parts = [meas_escaped]
        if tags:
            tag_str = ",".join(f"{_esc(str(k))}={_esc(str(v))}" for k, v in sorted(tags.items()) if v is not None)
            if tag_str:
                parts.append("," + tag_str)

        # field_key=field_val[,...]
        field_parts = []
        for k, v in fields.items():
            if v is None:
                continue
            fv = _field_val(v)
            if fv is not None:
                field_parts.append(f"{_esc(str(k))}={fv}")

        if not field_parts:
            return None

        lp = "".join(parts) + " " + ",".join(field_parts)

        # Timestamp in nanoseconds
        if timestamp is not None:
            if isinstance(timestamp, (int, float)):
                lp += f" {int(timestamp * 1_000_000_000)}"
            elif isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    lp += f" {int(dt.timestamp() * 1_000_000_000)}"
                except ValueError:
                    pass

        return lp

    def query(self, query_str: str, mode: str = "all") -> pyarrow.Table | pandas.DataFrame:
        try:
            table = self.client.query(query_str, database=self.database)
        except InfluxDB3ClientError as exc:
            logger.error(f"Caught {type_name(exc)}; {exc}")
            raise ValueError(f'Caught {type_name(exc)}: check the query "{query_str}"') from exc

        match mode:
            case "all":
                return table
            case "pandas":
                df = table.to_pandas()
                return df
            case _:
                raise ValueError(f"Invalid mode '{mode}', use 'all', or 'pandas'.")

    def get_table_names(self) -> list[str]:
        """Get all tables (measurements) in the database."""
        query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'iox'"

        try:
            result: pandas.DataFrame = self.query(query, mode="pandas")
            return [x for x in result["table_name"]]
        except Exception as exc:
            logger.error(f"Caught {type_name(exc)} while getting tables: {exc}")
            return []

    def get_column_names(self, table_name: str) -> list[str]:
        """Get column information for a specific table."""
        query = f"SHOW COLUMNS IN {table_name}"

        try:
            result: pandas.DataFrame = self.query(query, mode="pandas")
            return [x for x in result["column_name"]]
        except Exception as exc:
            logger.error(f"Caught {type_name(exc)} while getting column names: {exc}")
            return []

    def close(self) -> None:
        if self.client:
            self.client.close()

    def get_values_last_hours(
        self, table_name: str, column_name: str, hours: int = 24, mode: str = "pandas"
    ) -> pandas.DataFrame | list[list]:
        """Get column values from the last N hours."""
        query = f"""
            SELECT time, {column_name}
            FROM {table_name}
            WHERE time >= NOW() - INTERVAL '{hours} hours'
            ORDER BY time DESC
        """
        df = self.query(query, mode="pandas")

        if mode == "pandas":
            return df
        else:
            return _safe_convert_to_datetime_lists(df, "time", column_name)

    def get_values_in_range(
        self, table_name: str, column_name: str, start_time: str, end_time: str, mode: str = "pandas"
    ) -> pandas.DataFrame | list[list]:
        """Get column values within a time range."""
        query = f"""
            SELECT time, {column_name}
            FROM {table_name}
            WHERE time >= '{start_time}'
              AND time < '{end_time}'
            ORDER BY time DESC
        """
        df = self.query(query, mode="pandas")

        if mode == "pandas":
            return df
        else:
            return _safe_convert_to_datetime_lists(df, "time", column_name)


def _safe_convert_to_datetime_lists(df, time_col, value_col):
    """Safely convert DataFrame to [datetimes_list, values_list] with type checking."""

    # Check if time column exists and is convertible to datetime
    if time_col not in df.columns:
        raise ValueError(f"Time column '{time_col}' not found in data frame")

    if not pandas.api.types.is_datetime64_any_dtype(df[time_col]):
        print(f"Converting {time_col} from {df[time_col].dtype} to datetime")
        df[time_col] = pandas.to_datetime(df[time_col])

    # Check if value column exists and is numeric
    if value_col not in df.columns:
        raise ValueError(f"Value column '{value_col}' not found in data frame")

    if pandas.api.types.is_object_dtype(df[value_col]):
        print(f"No conversion needed for {value_col} from object type")
    elif pandas.api.types.is_integer_dtype(df[value_col]):
        print(f"Converting {value_col} from {df[value_col].dtype} to numeric")
        df[value_col] = pandas.to_numeric(df[value_col], errors="coerce")
    elif pandas.api.types.is_float_dtype(df[value_col]):
        print(f"Converting {value_col} from {df[value_col].dtype} to numeric")
        df[value_col] = pandas.to_numeric(df[value_col], errors="coerce")
    elif pandas.api.types.is_string_dtype(df[value_col]):
        print(f"No conversion needed  for {value_col} from string type")

    # Convert to lists
    datetimes = df[time_col].dt.to_pydatetime().tolist()
    values = df[value_col].tolist()

    return [datetimes, values]


# This method is required when loading the plugin with `get_metrics_repo()`.
def get_repository_class() -> type[TimeSeriesRepository]:
    """Returns the class that implements the TimeSeriesRepository."""
    return InfluxDBRepository
