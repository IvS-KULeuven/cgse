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

import pandas
import pyarrow
from influxdb_client_3 import InfluxDBClient3
from influxdb_client_3 import Point
from influxdb_client_3 import SYNCHRONOUS
from influxdb_client_3 import write_client_options
from influxdb_client_3.exceptions import InfluxDB3ClientError
from influxdb_client_3.write_client.domain.write_precision import WritePrecision

from egse.metrics import TimeSeriesRepository
from egse.system import type_name

logger = logging.getLogger("egse.plugins")


class InfluxDBRepository(TimeSeriesRepository):
    def __init__(self, host: str, database: str, token: str):
        self.host = host
        self.database = database
        self.token = token
        self.metrics_time_precision = WritePrecision.NS

        self.client = None

    def __enter__(self):
        self.connect()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        wco = write_client_options(
            write_options=SYNCHRONOUS, write_precision=self.metrics_time_precision, flush_interval=200
        )
        self.client = InfluxDBClient3(host=self.host, database=self.database, token=self.token, write_options=wco)

    def write(self, points: Point | dict | list[Point | dict]):
        self.client.write(record=points, write_precision=self.metrics_time_precision)

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

    def close(self):
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
def get_repository_class() -> TimeSeriesRepository:
    """Returns the class that implements the TimeSeriesRepository."""
    return InfluxDBRepository
