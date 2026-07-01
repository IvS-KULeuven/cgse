"""Administrative operations for CGSE."""

import datetime as dt
import json
import os
from typing import Annotated, Any, Optional

import typer

from egse.metrics import get_metrics_repo
from egse.plugins.metrics.migrate import migrate

app = typer.Typer(help="Administrative operations", no_args_is_help=True)


def _parse_json_keys(values: list[object]) -> list[str]:
    keys: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            keys.update(str(k) for k in value.keys())
            continue
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                keys.update(str(k) for k in parsed.keys())
    return sorted(keys)


def _parse_json_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {str(k): v for k, v in parsed.items()}
    return {}


def _format_value(value: object) -> str:
    if value is None:
        return "null"
    return str(value)


def _collect_tag_values_from_json(values: list[object], max_tag_values: int) -> dict[str, list[str]]:
    collected: dict[str, set[str]] = {}
    for value in values:
        parsed = _parse_json_dict(value)
        for key, raw in parsed.items():
            bucket = collected.setdefault(key, set())
            if len(bucket) >= max_tag_values:
                continue
            bucket.add(_format_value(raw))
    return {k: sorted(v) for k, v in sorted(collected.items())}


def _merge_tag_values(
    left: dict[str, list[str]],
    right: dict[str, list[str]],
    max_tag_values: int,
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {key: list(values) for key, values in left.items()}
    for key, values in right.items():
        bucket = merged.setdefault(key, [])
        for value in values:
            if value in bucket:
                continue
            if len(bucket) >= max_tag_values:
                break
            bucket.append(value)
        bucket.sort()
    return merged


def _to_datetime(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _normalize_backend_name(backend: str) -> str:
    normalized = backend.strip().lower()
    if normalized in ("quest", "questdb", "questdbrepository"):
        return "questdb"
    if normalized in ("duck", "duckdb", "duckdbrepository"):
        return "duckdb"
    if normalized in ("influx", "influxdb", "influxdbrepository"):
        return "influxdb"
    return normalized


def _is_influx_file_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "query would scan" in msg and "exceeding the file limit" in msg


def _is_read_only_statement(sql: str) -> bool:
    stripped = sql.strip().lower()
    if not stripped:
        return True

    read_only_prefixes = (
        "select",
        "show",
        "describe",
        "explain",
        "with",
        "pragma",
    )
    return stripped.startswith(read_only_prefixes)


def _print_query_result(rows: list[dict[str, object]], max_rows: int) -> None:
    if not rows:
        print("Result: statement executed (no rows returned)")
        return

    print(f"Result rows: {len(rows)}")
    shown = rows[:max_rows]
    print(f"Showing: {len(shown)} row(s)")
    for idx, row in enumerate(shown, start=1):
        print(f"  {idx}: {json.dumps(row, default=str, sort_keys=True)}")
    if len(rows) > max_rows:
        print(f"  ... {len(rows) - max_rows} additional row(s) omitted")


def _execute_sql_questdb(
    statement: str,
    max_rows: int,
    questdb_host: str,
    questdb_port: int,
    questdb_database: str,
    questdb_user: str,
    questdb_password: str,
    questdb_table: str,
    questdb_schema: str,
) -> int:
    repo = get_metrics_repo(
        "questdb",
        {
            "host": questdb_host,
            "port": questdb_port,
            "database": questdb_database,
            "user": questdb_user,
            "password": questdb_password,
            "table_name": questdb_table,
            "schema": questdb_schema,
        },
    )

    try:
        repo.connect()
        if not repo.ping():
            print("ERROR: QuestDB is unreachable")
            return 4

        rows = repo.query(statement, mode="all")
        _print_query_result(rows, max_rows=max_rows)
        return 0
    finally:
        repo.close()


def _execute_sql_duckdb(
    statement: str,
    max_rows: int,
    duckdb_path: str,
    duckdb_table: str,
) -> int:
    repo = get_metrics_repo(
        "duckdb",
        {
            "db_path": duckdb_path,
            "table_name": duckdb_table,
        },
    )

    try:
        repo.connect()
        if not repo.ping():
            print("ERROR: DuckDB is unreachable")
            return 5

        rows = repo.query(statement, mode="all")
        _print_query_result(rows, max_rows=max_rows)
        return 0
    finally:
        repo.close()


def _execute_sql_influx(
    statement: str,
    max_rows: int,
    influx_host: str,
    influx_database: str,
    influx_token: str,
) -> int:
    repo = get_metrics_repo(
        "influxdb",
        {
            "host": influx_host,
            "database": influx_database,
            "token": influx_token,
        },
    )

    try:
        repo.connect()
        if not repo.ping():
            print("ERROR: InfluxDB is unreachable")
            return 3

        result = repo.query(statement, mode="all")
        rows = result.to_pylist() if hasattr(result, "to_pylist") else result
        _print_query_result(rows, max_rows=max_rows)
        return 0
    finally:
        repo.close()


def _collect_questdb_tag_values_sampled(
    repo,
    table: str,
    sample_rows: int,
    max_tag_values: int,
    min_time: object,
    max_time: object,
) -> dict[str, list[str]]:
    slices: list[str] = [f'SELECT tags FROM "{table}" ORDER BY time DESC LIMIT {int(sample_rows)}']

    min_dt = _to_datetime(min_time)
    max_dt = _to_datetime(max_time)
    if min_dt is not None and max_dt is not None and max_dt > min_dt:
        total_seconds = max((max_dt - min_dt).total_seconds(), 1.0)
        bucket_seconds = max(int(total_seconds / max(sample_rows, 1)), 1)
        slices = [
            (f'SELECT first(tags) AS first_tags, last(tags) AS last_tags FROM "{table}" SAMPLE BY {bucket_seconds}s')
        ]

    merged: dict[str, list[str]] = {}
    for query in slices:
        rows = repo.query(query, mode="all")
        tag_payloads: list[object] = []
        for row in rows:
            if "tags" in row:
                tag_payloads.append(row.get("tags"))
            else:
                tag_payloads.append(row.get("first_tags"))
                tag_payloads.append(row.get("last_tags"))
        merged = _merge_tag_values(
            merged,
            _collect_tag_values_from_json(tag_payloads, max_tag_values),
            max_tag_values,
        )
    return merged


def _inspect_influx(
    influx_host: str,
    influx_database: str,
    influx_token: str,
    tables_filter: set[str],
    max_tables: int,
    sample_rows: int,
    max_tag_values: int,
) -> int:
    repo = get_metrics_repo(
        "influxdb",
        {
            "host": influx_host,
            "database": influx_database,
            "token": influx_token,
        },
    )

    try:
        repo.connect()
        if not repo.ping():
            print("ERROR: InfluxDB is unreachable")
            return 3

        tables = repo.get_table_names()
        if tables_filter:
            tables = [t for t in tables if t in tables_filter]
        tables = sorted(tables)[:max_tables]

        print("Database inspection")
        print("  Backend: influxdb")
        print(f"  Host: {influx_host}")
        print(f"  Database: {influx_database}")
        print(f"  Measurements: {len(tables)}")

        if not tables:
            print("  No measurements found.")
            return 0

        for table in tables:
            print(f"\nMeasurement: {table}")
            columns_df = repo.query(f'SHOW COLUMNS IN "{table}"', mode="pandas")
            field_names: list[str] = []
            tag_names: list[str] = []
            if not columns_df.empty and "column_name" in columns_df.columns:
                for _, row in columns_df.iterrows():
                    name = str(row.get("column_name", ""))
                    if not name or name == "time" or name.startswith("iox::"):
                        continue
                    marker = ""
                    for candidate in ("column_type", "influxdb_type", "kind", "type"):
                        if candidate in columns_df.columns and isinstance(row.get(candidate), str):
                            marker += str(row.get(candidate)).lower() + " "
                    if "tag" in marker:
                        tag_names.append(name)
                    else:
                        field_names.append(name)

            print(f"  Tags: {', '.join(sorted(set(tag_names))) if tag_names else '(none)'}")
            print(f"  Fields: {', '.join(sorted(set(field_names))) if field_names else '(none)'}")

            if tag_names:
                try:
                    quoted_tags = ", ".join([f'"{name}"' for name in sorted(set(tag_names))])
                    tags_df = repo.query(
                        f'SELECT {quoted_tags} FROM "{table}" ORDER BY time DESC LIMIT {int(sample_rows)}',
                        mode="pandas",
                    )
                    tag_values: dict[str, list[str]] = {}
                    for key in sorted(set(tag_names)):
                        if key not in tags_df.columns:
                            continue
                        values = []
                        for raw in tags_df[key].tolist():
                            if raw is None:
                                continue
                            text = _format_value(raw)
                            if text not in values:
                                values.append(text)
                            if len(values) >= max_tag_values:
                                break
                        if values:
                            tag_values[key] = sorted(values)
                    if tag_values:
                        print("  Tag values (sampled):")
                        for key, values in tag_values.items():
                            print(f"    - {key}: {', '.join(values)}")
                except Exception as exc:
                    print(f"  Tag values (sampled): n/a ({exc})")

            try:
                stats_df = repo.query(
                    f'SELECT COUNT(*) AS row_count, MIN(time) AS min_time, MAX(time) AS max_time FROM "{table}"',
                    mode="pandas",
                )
                if stats_df.empty:
                    print("  Rows: 0")
                    print("  Time window: n/a")
                else:
                    record = stats_df.to_dict(orient="records")[0]
                    print(f"  Rows: {int(record.get('row_count', 0) or 0)}")
                    print(f"  Time window: {record.get('min_time')} -> {record.get('max_time')}")
            except Exception as exc:
                if _is_influx_file_limit_error(exc):
                    # Full-range aggregation hits the Parquet file-scan limit.
                    # Fall back to LIMIT 1 queries; InfluxDB can resolve these
                    # from file-level min/max statistics without a full scan.
                    try:
                        min_df = repo.query(f'SELECT time FROM "{table}" ORDER BY time ASC LIMIT 1', mode="pandas")
                        max_df = repo.query(f'SELECT time FROM "{table}" ORDER BY time DESC LIMIT 1', mode="pandas")
                        min_time = min_df["time"].iloc[0] if not min_df.empty else "n/a"
                        max_time = max_df["time"].iloc[0] if not max_df.empty else "n/a"
                        print("  Rows: n/a (file-scan limit; use --query-file-limit to increase)")
                        print(f"  Time window: {min_time} -> {max_time}")
                    except Exception as exc2:
                        print("  Rows: n/a")
                        print("  Time window: n/a")
                        print(f"  Warning: could not compute stats ({exc2})")
                else:
                    print("  Rows: n/a")
                    print("  Time window: n/a")
                    print(f"  Warning: could not compute stats ({exc})")

        return 0
    finally:
        repo.close()


def _inspect_questdb(
    questdb_host: str,
    questdb_port: int,
    questdb_database: str,
    questdb_user: str,
    questdb_password: str,
    questdb_table: str,
    questdb_schema: str,
    tables_filter: set[str],
    max_tables: int,
    sample_rows: int,
    max_tag_values: int,
    tag_values_mode: str,
) -> int:
    repo = get_metrics_repo(
        "questdb",
        {
            "host": questdb_host,
            "port": questdb_port,
            "database": questdb_database,
            "user": questdb_user,
            "password": questdb_password,
            "table_name": questdb_table,
            "schema": questdb_schema,
        },
    )

    try:
        repo.connect()
        if not repo.ping():
            print("ERROR: QuestDB is unreachable")
            return 4

        table_names = repo.get_table_names()
        if questdb_schema == "unified":
            candidate_tables = [questdb_table] if questdb_table in table_names else []
        else:
            candidate_tables = table_names

        if tables_filter:
            candidate_tables = [t for t in candidate_tables if t in tables_filter]
        candidate_tables = sorted(candidate_tables)[:max_tables]

        print("Database inspection")
        print("  Backend: questdb")
        print(f"  Host: {questdb_host}:{questdb_port}")
        print(f"  Database: {questdb_database}")
        print(f"  Schema: {questdb_schema}")
        print(f"  Tables: {len(candidate_tables)}")

        if not candidate_tables:
            print("  No tables found.")
            return 0

        for table in candidate_tables:
            print(f"\nTable: {table}")
            stats: dict[str, Any] | None = None
            columns: list[str] | None = None
            time_column: str | None = None
            try:
                columns = repo.get_column_names(table)
                print(f"  Columns: {', '.join(columns) if columns else '(none)'}")
                if columns:
                    if "time" in columns:
                        time_column = "time"
                    elif "timestamp" in columns:
                        time_column = "timestamp"
            except Exception as exc:
                print(f"  Columns: n/a ({exc})")

            try:
                if not time_column:
                    raise ValueError("No time column found (expected 'time' or 'timestamp')")
                time_expr = f'"{time_column}"'
                stats_query = (
                    "SELECT COUNT(*) AS row_count, "
                    f"MIN({time_expr}) AS min_time, "
                    f"MAX({time_expr}) AS max_time "
                    f'FROM "{table}"'
                )
                stats_rows = repo.query(
                    stats_query,
                    mode="all",
                )
                if stats_rows:
                    stats = stats_rows[0]
                    assert stats is not None
                    stats_row = stats
                    row_count = int(stats_row.get("row_count") or 0)
                    min_time = stats_row.get("min_time")
                    max_time = stats_row.get("max_time")
                    print(f"  Rows: {row_count}")
                    print(f"  Time window: {min_time} -> {max_time}")
                else:
                    print("  Rows: 0")
                    print("  Time window: n/a")
            except Exception as exc:
                print("  Rows: n/a")
                print("  Time window: n/a")
                print(f"  Warning: could not compute stats ({exc})")

            # Check if this is unified schema (with tags/fields columns) or typed schema.
            has_tags_fields = "tags" in columns and "fields" in columns if columns else False

            if has_tags_fields:
                # Unified schema with JSON-stored tags and fields
                try:
                    if not time_column:
                        raise ValueError("No time column found (expected 'time' or 'timestamp')")
                    time_expr = f'"{time_column}"'
                    sample = repo.query(
                        f'SELECT tags, fields FROM "{table}" ORDER BY {time_expr} DESC LIMIT {int(sample_rows)}',
                        mode="all",
                    )
                    tag_keys = _parse_json_keys([row.get("tags") for row in sample])
                    field_keys = _parse_json_keys([row.get("fields") for row in sample])
                    print(f"  Tag keys (sampled): {', '.join(tag_keys) if tag_keys else '(none)'}")
                    print(f"  Field keys (sampled): {', '.join(field_keys) if field_keys else '(none)'}")

                    tag_values: dict[str, list[str]] = {}
                    effective_mode = tag_values_mode
                    if effective_mode == "auto":
                        row_count = int(stats.get("row_count") or 0) if stats else 0
                        effective_mode = "distinct" if row_count and row_count <= 1_000_000 else "sampled"

                    if effective_mode == "distinct":
                        distinct_query_failed = False
                        for key in tag_keys:
                            try:
                                rows = repo.query(
                                    (
                                        f"SELECT DISTINCT json_extract(tags, '$.{key}') AS tag_value "
                                        f'FROM "{table}" '
                                        f"WHERE json_extract(tags, '$.{key}') IS NOT NULL "
                                        f"ORDER BY tag_value "
                                        f"LIMIT {int(max_tag_values)}"
                                    ),
                                    mode="all",
                                )
                                values = []
                                for row in rows:
                                    raw = row.get("tag_value")
                                    if raw is None:
                                        continue
                                    text = _format_value(raw)
                                    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
                                        text = text[1:-1]
                                    if text not in values:
                                        values.append(text)
                                if values:
                                    tag_values[key] = values
                            except Exception:
                                distinct_query_failed = True
                                break
                        if distinct_query_failed:
                            effective_mode = "sampled"

                    if effective_mode == "sampled":
                        tag_values = _collect_questdb_tag_values_sampled(
                            repo=repo,
                            table=table,
                            sample_rows=sample_rows,
                            max_tag_values=max_tag_values,
                            min_time=stats.get("min_time") if stats else None,
                            max_time=stats.get("max_time") if stats else None,
                        )
                        if tag_values:
                            print("  Tag values (sampled):")
                            for key, values in tag_values.items():
                                print(f"    - {key}: {', '.join(values)}")
                    elif tag_values:
                        print("  Tag values (distinct):")
                        for key, values in tag_values.items():
                            print(f"    - {key}: {', '.join(values)}")
                except Exception as exc:
                    print(f"  Tag/field keys (sampled): n/a ({exc})")
            else:
                # Typed schema with native columns (per_measurement or line_protocol).
                # Display the typed columns (excluding temporal column) and their actual values
                typed_columns = [col for col in columns if col not in {"time", "timestamp"}] if columns else []
                if typed_columns:
                    print(f"  Tag/field keys (typed): {', '.join(typed_columns)}")

                    # Try to show some sample values for the typed columns
                    try:
                        if not time_column:
                            raise ValueError("No time column found (expected 'time' or 'timestamp')")
                        time_expr = f'"{time_column}"'
                        quoted_cols = ", ".join([f'"{col}"' for col in typed_columns[:5]])
                        sample_query = f'SELECT {quoted_cols} FROM "{table}" ORDER BY {time_expr} DESC LIMIT 1'
                        sample_rows_data = repo.query(sample_query, mode="all")
                        if sample_rows_data:
                            sample_row = sample_rows_data[0]
                            sample_values = {}
                            for col in typed_columns:
                                if col in sample_row:
                                    val = sample_row[col]
                                    if val is not None:
                                        sample_values[col] = _format_value(val)
                            if sample_values:
                                print("  Sample values:")
                                for key, value in sample_values.items():
                                    print(f"    - {key}: {value}")
                    except Exception as exc:
                        print(f"  Sample values: n/a ({exc})")
                else:
                    print("  Tag/field keys (typed): (none)")

        return 0
    finally:
        repo.close()


def _inspect_duckdb(
    duckdb_path: str,
    duckdb_table: str,
    tables_filter: set[str],
    max_tables: int,
    max_tag_values: int,
) -> int:
    repo = get_metrics_repo(
        "duckdb",
        {
            "db_path": duckdb_path,
            "table_name": duckdb_table,
        },
    )
    duck_repo: Any = repo

    try:
        duck_repo.connect()
        if not duck_repo.ping():
            print("ERROR: DuckDB is unreachable")
            return 5

        all_tables = duck_repo.query(f"SELECT DISTINCT measurement FROM {duckdb_table} ORDER BY measurement")
        measurements = [row.get("measurement") for row in all_tables if row.get("measurement")]
        if tables_filter:
            measurements = [m for m in measurements if m in tables_filter]
        measurements = sorted(measurements)[:max_tables]

        print("Database inspection")
        print("  Backend: duckdb")
        print(f"  Path: {duckdb_path}")
        print(f"  Main table: {duckdb_table}")
        print(f"  Measurements: {len(measurements)}")

        total_rows = duck_repo.query(f"SELECT COUNT(*) AS row_count FROM {duckdb_table}")
        print(f"  Total rows: {int(total_rows[0].get('row_count', 0) or 0) if total_rows else 0}")

        for measurement in measurements:
            print(f"\nMeasurement: {measurement}")
            stats = duck_repo.query(
                f"""
                SELECT
                    COUNT(*) AS row_count,
                    MIN(time) AS min_time,
                    MAX(time) AS max_time
                FROM {duckdb_table}
                WHERE measurement = '{measurement}'
                """
            )
            if stats:
                row = stats[0]
                print(f"  Rows: {int(row.get('row_count', 0) or 0)}")
                print(f"  Time window: {row.get('min_time')} -> {row.get('max_time')}")

            sample = duck_repo.query(
                f"""
                SELECT tags, fields
                FROM {duckdb_table}
                WHERE measurement = '{measurement}'
                ORDER BY time DESC
                LIMIT 200
                """
            )
            tag_keys = _parse_json_keys([row.get("tags") for row in sample])
            field_keys = _parse_json_keys([row.get("fields") for row in sample])
            print(f"  Tag keys (sampled): {', '.join(tag_keys) if tag_keys else '(none)'}")
            print(f"  Field keys (sampled): {', '.join(field_keys) if field_keys else '(none)'}")
            tag_values = _collect_tag_values_from_json([row.get("tags") for row in sample], max_tag_values)
            if tag_values:
                print("  Tag values (sampled):")
                for key, values in tag_values.items():
                    print(f"    - {key}: {', '.join(values)}")

        return 0
    finally:
        duck_repo.close()


@app.command(no_args_is_help=True)
def migrate_influx_to_questdb(
    influx_host: Annotated[str, typer.Option(help="InfluxDB host URL")] = "http://localhost:8181",
    influx_database: Annotated[str, typer.Option(help="InfluxDB database name")] = "",
    influx_token: Annotated[
        Optional[str], typer.Option(help="InfluxDB authentication token. Set INFLUXDB3_AUTH_TOKEN if not provided.")
    ] = None,
    questdb_host: Annotated[str, typer.Option(help="QuestDB host")] = "localhost",
    questdb_port: Annotated[int, typer.Option(help="QuestDB port")] = 8812,
    questdb_database: Annotated[str, typer.Option(help="QuestDB database name")] = "qdb",
    questdb_user: Annotated[str, typer.Option(help="QuestDB username")] = "admin",
    questdb_password: Annotated[str, typer.Option(help="QuestDB password")] = "quest",
    questdb_table: Annotated[str, typer.Option(help="QuestDB table name (unified schema mode)")] = "timeseries",
    questdb_schema: Annotated[
        str, typer.Option(help="QuestDB schema mode: 'unified', 'per_measurement', or 'line_protocol'")
    ] = "unified",
    tables: Annotated[
        str, typer.Option(help="Comma-separated list of measurements to migrate (auto-discover if empty)")
    ] = "",
    since: Annotated[str, typer.Option(help="RFC3339 start time (inclusive)")] = "",
    until: Annotated[str, typer.Option(help="RFC3339 end time (exclusive)")] = "",
    query_batch_size: Annotated[int, typer.Option(help="Rows fetched per InfluxDB query batch")] = 10_000,
    write_batch_size: Annotated[int, typer.Option(help="Rows written per QuestDB write call")] = 5_000,
    time_chunk_hours: Annotated[float, typer.Option(help="Time-chunk size in hours (0 = disabled)")] = 0.0,
    adaptive_chunking: Annotated[bool, typer.Option(help="Automatically reduce chunk size on query failures")] = True,
    min_time_chunk_hours: Annotated[
        float, typer.Option(help="Minimum chunk size in hours for adaptive retries")
    ] = 0.25,
    chunk_backoff_factor: Annotated[float, typer.Option(help="Factor to shrink chunks on retry (must be > 1)")] = 2.0,
    drop_destination_table: Annotated[
        bool, typer.Option(help="Drop and recreate destination table before migrating")
    ] = False,
    preflight_only: Annotated[bool, typer.Option(help="Run preflight checks and exit without writing")] = False,
    skip_preflight: Annotated[
        bool, typer.Option(help="Skip preflight checks and proceed directly to migration")
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Inspect and count rows without writing to QuestDB")] = False,
    state_file: Annotated[
        str, typer.Option(help="Path to persistent migration state for resuming")
    ] = ".migrate_influx_to_questdb.state.json",
    resume: Annotated[bool, typer.Option(help="Resume from previously saved checkpoints")] = True,
    reset_state: Annotated[bool, typer.Option(help="Delete existing state file before starting")] = False,
    replace_destination_range: Annotated[
        bool, typer.Option(help="Delete destination rows before writing (makes reruns idempotent)")
    ] = True,
) -> None:
    """Migrate time-series data from InfluxDB 3 Core to QuestDB.

    This command transfers historical metrics from InfluxDB to QuestDB, preserving
    measurement names in the 'measurement' column. Each source row is converted to
    the QuestDB payload format with measurement, tags (JSON), fields (JSON), and time.

    Use --preflight-only to inspect data without writing, or --dry-run to count rows.
    The migration supports resumable checkpoints via --state-file for handling large
    datasets or interrupted transfers.
    """
    import argparse
    import os

    # Read environment variables for defaults if parameters are not provided
    if not influx_token:
        influx_token = os.environ.get("INFLUXDB3_AUTH_TOKEN", "")
    if not influx_database:
        influx_database = os.environ.get("CGSE_INFLUX_DATABASE", os.environ.get("PROJECT", "cgse"))

    # Build arguments for the migration function
    args = argparse.Namespace(
        influx_host=influx_host,
        influx_database=influx_database,
        influx_token=influx_token,
        questdb_host=questdb_host,
        questdb_port=questdb_port,
        questdb_database=questdb_database,
        questdb_user=questdb_user,
        questdb_password=questdb_password,
        questdb_table=questdb_table,
        questdb_schema=questdb_schema,
        tables=tables,
        since=since,
        until=until,
        query_batch_size=query_batch_size,
        write_batch_size=write_batch_size,
        time_chunk_hours=time_chunk_hours,
        adaptive_chunking=adaptive_chunking,
        min_time_chunk_hours=min_time_chunk_hours,
        chunk_backoff_factor=chunk_backoff_factor,
        drop_destination_table=drop_destination_table,
        preflight_only=preflight_only,
        skip_preflight=skip_preflight,
        dry_run=dry_run,
        state_file=state_file,
        resume=resume,
        reset_state=reset_state,
        replace_destination_range=replace_destination_range,
    )

    exit_code = migrate(args)
    raise typer.Exit(code=exit_code)


@app.command(no_args_is_help=True)
def inspect_db(
    backend: Annotated[
        str,
        typer.Option(help="Database backend to inspect: influxdb, questdb, or duckdb"),
    ] = "influxdb",
    tables: Annotated[
        str,
        typer.Option(help="Optional comma-separated table/measurement filter"),
    ] = "",
    max_tables: Annotated[int, typer.Option(help="Maximum number of tables/measurements to inspect")] = 100,
    sample_rows: Annotated[int, typer.Option(help="Rows sampled for tag/field key discovery")] = 200,
    max_tag_values: Annotated[int, typer.Option(help="Maximum distinct values shown per tag key")] = 10,
    tag_values_mode: Annotated[
        str,
        typer.Option(help="Tag value discovery mode: auto, sampled, or distinct"),
    ] = "auto",
    influx_host: Annotated[str, typer.Option(help="InfluxDB host URL")] = "http://localhost:8181",
    influx_database: Annotated[str, typer.Option(help="InfluxDB database name")] = "",
    influx_token: Annotated[
        Optional[str], typer.Option(help="InfluxDB authentication token. Set INFLUXDB3_AUTH_TOKEN if not provided.")
    ] = None,
    questdb_host: Annotated[str, typer.Option(help="QuestDB host")] = "localhost",
    questdb_port: Annotated[int, typer.Option(help="QuestDB port")] = 8812,
    questdb_database: Annotated[str, typer.Option(help="QuestDB database name")] = "qdb",
    questdb_user: Annotated[str, typer.Option(help="QuestDB username")] = "admin",
    questdb_password: Annotated[str, typer.Option(help="QuestDB password")] = "quest",
    questdb_table: Annotated[str, typer.Option(help="QuestDB unified table name")] = "timeseries",
    questdb_schema: Annotated[
        str,
        typer.Option(help="QuestDB schema mode: unified, per_measurement, or line_protocol"),
    ] = "per_measurement",
    duckdb_path: Annotated[str, typer.Option(help="DuckDB file path")] = "",
    duckdb_table: Annotated[str, typer.Option(help="DuckDB main table name")] = "timeseries",
) -> None:
    """Inspect a metrics backend and print schema and data coverage information.

    The command reports tables/measurements, discovered fields/tags, row counts,
    and min/max time windows. Some values are sampled where full scans are too
    expensive.
    """
    backend_normalized = backend.strip().lower()
    if backend_normalized in ("quest", "questdb", "questdbrepository"):
        backend_normalized = "questdb"
    elif backend_normalized in ("duck", "duckdb", "duckdbrepository"):
        backend_normalized = "duckdb"
    elif backend_normalized in ("influx", "influxdb", "influxdbrepository"):
        backend_normalized = "influxdb"

    if max_tables <= 0:
        raise typer.BadParameter("--max-tables must be > 0")
    if sample_rows <= 0:
        raise typer.BadParameter("--sample-rows must be > 0")
    if max_tag_values <= 0:
        raise typer.BadParameter("--max-tag-values must be > 0")
    if tag_values_mode not in {"auto", "sampled", "distinct"}:
        raise typer.BadParameter("--tag-values-mode must be one of: auto, sampled, distinct")

    table_filter = {x.strip() for x in tables.split(",") if x.strip()}

    if backend_normalized == "influxdb":
        if not influx_token:
            influx_token = os.environ.get("INFLUXDB3_AUTH_TOKEN", "")
        if not influx_database:
            influx_database = os.environ.get("CGSE_INFLUX_DATABASE", os.environ.get("PROJECT", "cgse"))
        if not influx_token:
            print("ERROR: missing InfluxDB auth token. Set INFLUXDB3_AUTH_TOKEN or pass --influx-token.")
            raise typer.Exit(code=2)

        exit_code = _inspect_influx(
            influx_host=influx_host,
            influx_database=influx_database,
            influx_token=influx_token,
            tables_filter=table_filter,
            max_tables=max_tables,
            sample_rows=sample_rows,
            max_tag_values=max_tag_values,
        )
        raise typer.Exit(code=exit_code)

    if backend_normalized == "questdb":
        exit_code = _inspect_questdb(
            questdb_host=questdb_host,
            questdb_port=questdb_port,
            questdb_database=questdb_database,
            questdb_user=questdb_user,
            questdb_password=questdb_password,
            questdb_table=questdb_table,
            questdb_schema=questdb_schema,
            tables_filter=table_filter,
            max_tables=max_tables,
            sample_rows=sample_rows,
            max_tag_values=max_tag_values,
            tag_values_mode=tag_values_mode,
        )
        raise typer.Exit(code=exit_code)

    if backend_normalized == "duckdb":
        if not duckdb_path:
            duckdb_path = os.environ.get("CGSE_DUCKDB_PATH", "metrics.duckdb")

        exit_code = _inspect_duckdb(
            duckdb_path=duckdb_path,
            duckdb_table=duckdb_table,
            tables_filter=table_filter,
            max_tables=max_tables,
            max_tag_values=max_tag_values,
        )
        raise typer.Exit(code=exit_code)

    print(f"ERROR: unsupported backend '{backend}'. Use influxdb, questdb, or duckdb.")
    raise typer.Exit(code=2)


@app.command("sql", no_args_is_help=True)
def execute_sql(
    statement: Annotated[
        str,
        typer.Argument(help="SQL statement to execute (quote it in your shell)."),
    ],
    backend: Annotated[
        str,
        typer.Option(help="Database backend: influxdb, questdb, or duckdb"),
    ] = "questdb",
    allow_write: Annotated[
        bool,
        typer.Option(help="Allow non-read-only statements (INSERT/UPDATE/DELETE/DDL)."),
    ] = False,
    max_rows: Annotated[int, typer.Option(help="Maximum result rows to print")] = 50,
    influx_host: Annotated[str, typer.Option(help="InfluxDB host URL")] = "http://localhost:8181",
    influx_database: Annotated[str, typer.Option(help="InfluxDB database name")] = "",
    influx_token: Annotated[
        Optional[str], typer.Option(help="InfluxDB authentication token. Set INFLUXDB3_AUTH_TOKEN if not provided.")
    ] = None,
    questdb_host: Annotated[str, typer.Option(help="QuestDB host")] = "localhost",
    questdb_port: Annotated[int, typer.Option(help="QuestDB port")] = 8812,
    questdb_database: Annotated[str, typer.Option(help="QuestDB database name")] = "qdb",
    questdb_user: Annotated[str, typer.Option(help="QuestDB username")] = "admin",
    questdb_password: Annotated[str, typer.Option(help="QuestDB password")] = "quest",
    questdb_table: Annotated[str, typer.Option(help="QuestDB unified table name")] = "timeseries",
    questdb_schema: Annotated[
        str,
        typer.Option(help="QuestDB schema mode: unified, per_measurement, or line_protocol"),
    ] = "per_measurement",
    duckdb_path: Annotated[str, typer.Option(help="DuckDB file path")] = "",
    duckdb_table: Annotated[str, typer.Option(help="DuckDB main table name")] = "timeseries",
) -> None:
    """Execute a SQL statement on a selected metrics backend.

    By default, only read-only statements are allowed. Pass --allow-write for
    schema or data mutations such as DROP/ALTER/DELETE/INSERT.
    """
    backend_normalized = _normalize_backend_name(backend)

    if max_rows <= 0:
        raise typer.BadParameter("--max-rows must be > 0")

    if not statement.strip():
        raise typer.BadParameter("statement must not be empty")

    if not allow_write and not _is_read_only_statement(statement):
        raise typer.BadParameter(
            "refusing non-read-only SQL without --allow-write; "
            "use --allow-write for statements like DROP/ALTER/DELETE/INSERT"
        )

    try:
        if backend_normalized == "influxdb":
            if not influx_token:
                influx_token = os.environ.get("INFLUXDB3_AUTH_TOKEN", "")
            if not influx_database:
                influx_database = os.environ.get("CGSE_INFLUX_DATABASE", os.environ.get("PROJECT", "cgse"))
            if not influx_token:
                print("ERROR: missing InfluxDB auth token. Set INFLUXDB3_AUTH_TOKEN or pass --influx-token.")
                raise typer.Exit(code=2)

            exit_code = _execute_sql_influx(
                statement=statement,
                max_rows=max_rows,
                influx_host=influx_host,
                influx_database=influx_database,
                influx_token=influx_token,
            )
            raise typer.Exit(code=exit_code)

        if backend_normalized == "questdb":
            exit_code = _execute_sql_questdb(
                statement=statement,
                max_rows=max_rows,
                questdb_host=questdb_host,
                questdb_port=questdb_port,
                questdb_database=questdb_database,
                questdb_user=questdb_user,
                questdb_password=questdb_password,
                questdb_table=questdb_table,
                questdb_schema=questdb_schema,
            )
            raise typer.Exit(code=exit_code)

        if backend_normalized == "duckdb":
            if not duckdb_path:
                duckdb_path = os.environ.get("CGSE_DUCKDB_PATH", "metrics.duckdb")

            exit_code = _execute_sql_duckdb(
                statement=statement,
                max_rows=max_rows,
                duckdb_path=duckdb_path,
                duckdb_table=duckdb_table,
            )
            raise typer.Exit(code=exit_code)

        print(f"ERROR: unsupported backend '{backend}'. Use influxdb, questdb, or duckdb.")
        raise typer.Exit(code=2)
    except typer.Exit:
        raise
    except Exception as exc:
        print(f"ERROR: SQL execution failed: {exc}")
        raise typer.Exit(code=1)
