"""Migrate time-series data from InfluxDB 3 Core to QuestDB.

This module provides the migration functionality for transferring historical metrics
data from InfluxDB to QuestDB. It is typically invoked via the `cgse admin migrate-influx-to-questdb`
CLI command.

InfluxDB measurement names are preserved in the QuestDB ``measurement`` column.
Each source row is converted to the QuestDB payload format:

- measurement: source measurement name
- time: source ``time`` value
- tags: JSON object with Influx tag columns
- fields: JSON object with Influx field columns
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

from egse.metrics import get_metrics_repo
from egse.plugins.metrics.influxdb import InfluxDBRepository
from egse.plugins.metrics.questdb import QuestDBRepository


def _parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate InfluxDB3 metrics to QuestDB")

    parser.add_argument("--influx-host", default=os.environ.get("CGSE_INFLUX_HOST", "http://localhost:8181"))
    parser.add_argument(
        "--influx-database",
        default=os.environ.get("CGSE_INFLUX_DATABASE", os.environ.get("PROJECT", "cgse")),
    )
    parser.add_argument("--influx-token", default=os.environ.get("INFLUXDB3_AUTH_TOKEN", ""))

    parser.add_argument("--questdb-host", default=os.environ.get("CGSE_QUESTDB_HOST", "localhost"))
    parser.add_argument("--questdb-port", type=int, default=int(os.environ.get("CGSE_QUESTDB_PORT", "8812")))
    parser.add_argument("--questdb-database", default=os.environ.get("CGSE_QUESTDB_DATABASE", "qdb"))
    parser.add_argument("--questdb-user", default=os.environ.get("CGSE_QUESTDB_USER", "admin"))
    parser.add_argument("--questdb-password", default=os.environ.get("CGSE_QUESTDB_PASSWORD", "quest"))
    parser.add_argument("--questdb-table", default=os.environ.get("CGSE_QUESTDB_TABLE", "timeseries"))
    parser.add_argument(
        "--questdb-schema",
        default=os.environ.get("CGSE_QUESTDB_SCHEMA", "unified"),
        choices=["unified", "per_measurement"],
        help=(
            "QuestDB schema mode. 'unified' stores all measurements in a single table (default). "
            "'per_measurement' creates one table per measurement, mirroring InfluxDB's structure."
        ),
    )

    parser.add_argument(
        "--tables",
        default="",
        help="Comma-separated list of Influx measurements to migrate. Default: auto-discover all measurements.",
    )
    parser.add_argument("--since", default="", help="Optional RFC3339 start time (inclusive).")
    parser.add_argument("--until", default="", help="Optional RFC3339 end time (exclusive).")

    parser.add_argument("--query-batch-size", type=int, default=10_000, help="Rows fetched per Influx query batch.")
    parser.add_argument("--write-batch-size", type=int, default=5_000, help="Rows written per QuestDB write call.")
    parser.add_argument(
        "--time-chunk-hours",
        type=float,
        default=0.0,
        help=(
            "Optional time-chunk size in hours. When > 0, queries are split into smaller "
            "time windows to work around wide-range query limits."
        ),
    )
    parser.add_argument(
        "--adaptive-chunking",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Automatically reduce chunk size when a chunk query fails.",
    )
    parser.add_argument(
        "--min-time-chunk-hours",
        type=float,
        default=0.25,
        help="Smallest chunk size in hours allowed for adaptive retries.",
    )
    parser.add_argument(
        "--chunk-backoff-factor",
        type=float,
        default=2.0,
        help="Factor used to shrink chunks on retry (must be > 1).",
    )

    parser.add_argument(
        "--drop-destination-table",
        action="store_true",
        help="Drop and recreate the QuestDB destination table before migrating.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run preflight visibility checks and exit without writing to QuestDB.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight visibility checks and proceed directly to migration.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Inspect and count rows without writing to QuestDB.")
    parser.add_argument(
        "--state-file",
        default=".migrate_influx_to_questdb.state.json",
        help="Path to persistent migration state used for resume.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume from previously saved checkpoints in --state-file.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Delete existing state file before starting migration.",
    )
    parser.add_argument(
        "--replace-destination-range",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Delete destination rows for each measurement/time-range before writing. "
            "This makes reruns and resume operations idempotent."
        ),
    )

    return parser.parse_args(args)


def _parse_tables(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _assert_read_only_influx_query(query: str) -> None:
    """Fail fast if a non-read-only statement is about to be sent to InfluxDB."""
    normalized = query.strip().lower()
    if not normalized:
        raise ValueError("Empty InfluxDB query is not allowed")

    # This migration script only needs schema discovery and reads.
    allowed_prefixes = ("select", "show", "with", "explain")
    if not normalized.startswith(allowed_prefixes):
        raise ValueError(f"Blocked non-read-only InfluxDB query: {query!r}")


def _influx_query(influx: InfluxDBRepository, query: str, mode: str = "pandas") -> pd.DataFrame:
    _assert_read_only_influx_query(query)
    result = influx.query(query, mode=mode)
    if mode == "pandas" and not isinstance(result, pd.DataFrame):
        raise TypeError("Expected pandas DataFrame from Influx query")
    return result


def _quote_influx_identifier(identifier: str) -> str:
    """Quote an Influx SQL identifier to preserve case and special characters."""
    return '"' + identifier.replace('"', '""') + '"'


def _sql_time_literal(value: str) -> str:
    # Keep user-supplied format; script assumes RFC3339-style timestamps.
    return value


def _build_where_clause(since: str, until: str) -> str:
    clauses: list[str] = []
    if since:
        clauses.append(f"time >= '{_sql_time_literal(since)}'")
    if until:
        clauses.append(f"time < '{_sql_time_literal(until)}'")

    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)


def _infer_tag_and_field_columns(influx: InfluxDBRepository, table: str) -> tuple[list[str], list[str]]:
    """Infer tag/field columns using SHOW COLUMNS metadata.

    If column kind metadata is not present, falls back to treating all
    non-time/non-system columns as fields.
    """
    table_quoted = _quote_influx_identifier(table)
    df = _influx_query(influx, f"SHOW COLUMNS IN {table_quoted}", mode="pandas")

    if not isinstance(df, pd.DataFrame) or df.empty or "column_name" not in df.columns:
        return [], []

    tag_cols: list[str] = []
    field_cols: list[str] = []

    for _, row in df.iterrows():
        name = str(row["column_name"])
        if name == "time" or name.startswith("iox::"):
            continue

        type_markers = []
        for candidate in ("column_type", "influxdb_type", "kind", "type"):
            if candidate in df.columns:
                value = row.get(candidate)
                if isinstance(value, str):
                    type_markers.append(value.lower())

        marker_blob = " ".join(type_markers)
        if "tag" in marker_blob:
            tag_cols.append(name)
        elif "field" in marker_blob:
            field_cols.append(name)
        else:
            # Unknown metadata shape: keep as field by default.
            field_cols.append(name)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    tag_cols = [c for c in tag_cols if not (c in seen or seen.add(c))]
    seen.clear()
    field_cols = [c for c in field_cols if not (c in seen or seen.add(c))]

    # Prevent overlap if metadata was inconsistent.
    field_cols = [c for c in field_cols if c not in set(tag_cols)]

    return tag_cols, field_cols


def _scalar_or_none(value: Any) -> Any:
    if value is None:
        return None
    if pd.isna(value):
        return None

    if isinstance(value, (bool, int, str)):
        return value

    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return None

    if isinstance(value, (pd.Timestamp, dt.datetime)):
        return value.isoformat()

    return str(value)


def _row_to_payload(
    table: str,
    row: dict[str, Any],
    tag_cols: list[str],
    field_cols: list[str],
) -> dict[str, Any] | None:
    if "time" not in row or row["time"] is None or pd.isna(row["time"]):
        return None

    tags: dict[str, str] = {}
    for c in tag_cols:
        if c not in row:
            continue
        value = _scalar_or_none(row[c])
        if value is not None:
            tags[c] = str(value)

    fields: dict[str, Any] = {}
    for c in field_cols:
        if c not in row:
            continue
        value = _scalar_or_none(row[c])
        if value is not None:
            fields[c] = value

    # If field inference produced no columns, fallback to all non-time/non-tag columns.
    if not fields:
        for c, value_raw in row.items():
            if c == "time" or c.startswith("iox::") or c in tags:
                continue
            value = _scalar_or_none(value_raw)
            if value is not None:
                fields[c] = value

    if not fields:
        return None

    time_val = row["time"]
    if isinstance(time_val, pd.Timestamp):
        time_out: Any = time_val.to_pydatetime()
    else:
        time_out = time_val

    return {
        "measurement": table,
        "tags": tags,
        "fields": fields,
        "time": time_out,
    }


def _drop_destination_table(repo: QuestDBRepository, table_name: str) -> None:
    if repo.conn is None:
        raise ConnectionError("QuestDB repository is not connected")
    with repo.conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {table_name}")


def _to_datetime_or_none(value: Any) -> dt.datetime | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _normalize_dt(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _run_preflight(
    influx: InfluxDBRepository,
    tables: list[str],
    since: str,
    until: str,
) -> tuple[bool, dict[str, tuple[dt.datetime | None, dt.datetime | None, int]]]:
    """Return (has_warning, per_table_visible_range)."""
    since_dt = _normalize_dt(_to_datetime_or_none(since))
    until_dt = _normalize_dt(_to_datetime_or_none(until))

    print("\nInflux preflight (query-visible range)")
    print("  This reflects data that InfluxDB Core currently allows querying.")

    has_warning = False
    per_table: dict[str, tuple[dt.datetime | None, dt.datetime | None, int]] = {}
    for table in tables:
        table_quoted = _quote_influx_identifier(table)
        try:
            df = _influx_query(
                influx,
                f"SELECT MIN(time) AS min_time, MAX(time) AS max_time, COUNT(*) AS row_count FROM {table_quoted}",
                mode="pandas",
            )
        except Exception as exc:
            has_warning = True
            per_table[table] = (None, None, 0)
            print(f"  - {table}: query failed ({exc})")
            print("    WARNING: skipping this table for preflight and migration.")
            continue

        if not isinstance(df, pd.DataFrame) or df.empty:
            per_table[table] = (None, None, 0)
            print(f"  - {table}: no query-visible rows")
            if since_dt or until_dt:
                has_warning = True
                print("    WARNING: requested time filter may not be reachable in Core.")
            continue

        record = df.to_dict(orient="records")[0]
        min_dt = _normalize_dt(_to_datetime_or_none(record.get("min_time")))
        max_dt = _normalize_dt(_to_datetime_or_none(record.get("max_time")))
        row_count = int(record.get("row_count", 0) or 0)
        per_table[table] = (min_dt, max_dt, row_count)

        print(
            f"  - {table}: rows={row_count}, min={min_dt.isoformat() if min_dt else 'n/a'}, "
            f"max={max_dt.isoformat() if max_dt else 'n/a'}"
        )

        if since_dt and min_dt and since_dt < min_dt:
            has_warning = True
            print("    WARNING: --since is older than earliest query-visible row.")
            print("    WARNING: this can indicate Core historical window limits.")
        if until_dt and max_dt and until_dt > max_dt:
            has_warning = True
            print("    WARNING: --until is newer than latest query-visible row.")
            print("    WARNING: this can indicate no data in that span or Core limits.")

    return has_warning, per_table


def _iter_time_chunks(
    start: dt.datetime,
    end: dt.datetime,
    hours: float,
):
    seconds = max(int(hours * 3600), 1)
    delta = dt.timedelta(seconds=seconds)
    current = start
    while current < end:
        nxt = min(current + delta, end)
        yield current, nxt
        current = nxt


def _fmt_dt_sql(value: dt.datetime) -> str:
    value = _normalize_dt(value) or value
    return value.isoformat().replace("+00:00", "Z")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "tables": {}}

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        return {"version": 1, "tables": {}}
    if "tables" not in data or not isinstance(data["tables"], dict):
        data["tables"] = {}
    if "version" not in data:
        data["version"] = 1
    return data


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def _get_table_state(state: dict[str, Any], table: str) -> dict[str, Any]:
    tables = state.setdefault("tables", {})
    table_state = tables.get(table)
    if not isinstance(table_state, dict):
        table_state = {}
        tables[table] = table_state
    return table_state


def _update_table_checkpoint(
    state: dict[str, Any],
    state_path: Path,
    table: str,
    checkpoint_time: dt.datetime,
    table_rows_read: int,
    table_rows_written: int,
) -> None:
    table_state = _get_table_state(state, table)
    table_state["last_time"] = _fmt_dt_sql(checkpoint_time)
    table_state["rows_read"] = int(table_rows_read)
    table_state["rows_written"] = int(table_rows_written)
    table_state["completed"] = False
    table_state["updated_at"] = _fmt_dt_sql(dt.datetime.now(tz=dt.timezone.utc))
    _save_state(state_path, state)


def _mark_table_completed(
    state: dict[str, Any],
    state_path: Path,
    table: str,
    table_rows_read: int,
    table_rows_written: int,
) -> None:
    table_state = _get_table_state(state, table)
    table_state["rows_read"] = int(table_rows_read)
    table_state["rows_written"] = int(table_rows_written)
    table_state["completed"] = True
    table_state["updated_at"] = _fmt_dt_sql(dt.datetime.now(tz=dt.timezone.utc))
    _save_state(state_path, state)


def _max_payload_time(points: list[dict[str, Any]]) -> dt.datetime | None:
    max_time: dt.datetime | None = None
    for payload in points:
        item_time = _normalize_dt(_to_datetime_or_none(payload.get("time")))
        if item_time is None:
            continue
        if max_time is None or item_time > max_time:
            max_time = item_time
    return max_time


def _delete_destination_range(
    repo: QuestDBRepository,
    table_name: str,
    measurement: str,
    since_dt: dt.datetime | None,
    until_dt: dt.datetime | None,
) -> int | None:
    if repo.conn is None:
        raise ConnectionError("QuestDB repository is not connected")

    # For per_measurement schema the target table IS the measurement; no
    # measurement-column filter needed.  For unified schema we filter by both
    # the measurement column and the time range.
    if repo.schema == "per_measurement":
        target_table = f'"{measurement}"'
        where_parts: list[str] = []
        params: list[Any] = []
    else:
        target_table = f'"{table_name}"'
        where_parts = ["measurement = %s"]
        params = [measurement]

    if since_dt is not None:
        where_parts.append("time >= %s")
        params.append(since_dt)
    if until_dt is not None:
        where_parts.append("time < %s")
        params.append(until_dt)

    where_clause = " AND ".join(where_parts)
    query = f"DELETE FROM {target_table}" + (f" WHERE {where_clause}" if where_clause else "")

    try:
        with repo.conn.cursor() as cur:
            cur.execute(query, params)
            deleted = cur.rowcount
    except Exception as exc:
        # Some QuestDB versions/builds don't support DELETE FROM over PGWire.
        message = str(exc)
        if "unexpected token [FROM]" in message:
            return None
        raise

    if deleted is None or deleted < 0:
        return None
    return int(deleted)


def _iter_influx_batches_windowed(
    influx: InfluxDBRepository,
    table: str,
    where_clause: str,
    query_batch_size: int,
    chunk_start: dt.datetime,
    chunk_end: dt.datetime,
):
    table_quoted = _quote_influx_identifier(table)
    chunk_where_parts = [f"time >= '{_fmt_dt_sql(chunk_start)}'", f"time < '{_fmt_dt_sql(chunk_end)}'"]
    if where_clause:
        chunk_where_parts.insert(0, where_clause.replace("WHERE", "", 1).strip())
    chunk_where = "WHERE " + " AND ".join(chunk_where_parts)

    offset = 0
    while True:
        query = f"SELECT * FROM {table_quoted} {chunk_where} ORDER BY time ASC LIMIT {query_batch_size} OFFSET {offset}"
        df = _influx_query(influx, query, mode="pandas")

        if not isinstance(df, pd.DataFrame) or df.empty:
            break

        yield df
        offset += len(df)


def _iter_influx_batches_windowed_adaptive(
    influx: InfluxDBRepository,
    table: str,
    where_clause: str,
    query_batch_size: int,
    start: dt.datetime,
    end: dt.datetime,
    chunk_hours: float,
    adaptive_chunking: bool,
    min_chunk_hours: float,
    chunk_backoff_factor: float,
):
    current = start
    while current < end:
        current_chunk_hours = chunk_hours
        while True:
            current_delta = dt.timedelta(seconds=max(int(current_chunk_hours * 3600), 1))
            current_end = min(current + current_delta, end)

            try:
                for df in _iter_influx_batches_windowed(
                    influx,
                    table,
                    where_clause,
                    query_batch_size,
                    current,
                    current_end,
                ):
                    yield df

                if current_chunk_hours < chunk_hours:
                    print(
                        "    Chunk recovered: "
                        f"{_fmt_dt_sql(current)} .. {_fmt_dt_sql(current_end)} "
                        f"({current_chunk_hours:g}h)"
                    )

                current = current_end
                break
            except Exception as exc:
                if not adaptive_chunking:
                    raise

                next_chunk_hours = max(min_chunk_hours, current_chunk_hours / chunk_backoff_factor)
                cannot_reduce = math.isclose(next_chunk_hours, current_chunk_hours)
                if next_chunk_hours <= min_chunk_hours and cannot_reduce:
                    raise RuntimeError(
                        "Chunk query failed at minimum chunk size; "
                        f"table={table}, range={_fmt_dt_sql(current)}..{_fmt_dt_sql(current_end)}, "
                        f"min_chunk_hours={min_chunk_hours:g}"
                    ) from exc

                print(
                    "    Chunk query failed, retrying with smaller window: "
                    f"{current_chunk_hours:g}h -> {next_chunk_hours:g}h"
                )
                current_chunk_hours = next_chunk_hours


def _iter_influx_batches(
    influx: InfluxDBRepository,
    table: str,
    where_clause: str,
    query_batch_size: int,
):
    table_quoted = _quote_influx_identifier(table)
    offset = 0
    while True:
        query = (
            f"SELECT * FROM {table_quoted} {where_clause} ORDER BY time ASC LIMIT {query_batch_size} OFFSET {offset}"
        )
        df = _influx_query(influx, query, mode="pandas")

        if not isinstance(df, pd.DataFrame) or df.empty:
            break

        yield df
        offset += len(df)


def _is_influx_query_file_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "query would scan" in message and "exceeding the file limit" in message


def migrate(args: argparse.Namespace) -> int:
    if not args.influx_token:
        print("ERROR: missing InfluxDB auth token. Set INFLUXDB3_AUTH_TOKEN or pass --influx-token.")
        return 2
    if args.time_chunk_hours < 0:
        print("ERROR: --time-chunk-hours must be >= 0")
        return 2
    if args.time_chunk_hours > 0 and args.min_time_chunk_hours <= 0:
        print("ERROR: --min-time-chunk-hours must be > 0")
        return 2
    if args.time_chunk_hours > 0 and args.chunk_backoff_factor <= 1:
        print("ERROR: --chunk-backoff-factor must be > 1")
        return 2
    if args.time_chunk_hours > 0 and args.min_time_chunk_hours > args.time_chunk_hours:
        print("ERROR: --min-time-chunk-hours must be <= --time-chunk-hours")
        return 2

    state_path = Path(args.state_file).expanduser()
    if args.reset_state and state_path.exists():
        state_path.unlink()

    state: dict[str, Any] = {"version": 1, "tables": {}}
    if args.resume and not args.dry_run:
        state = _load_state(state_path)

    influx = get_metrics_repo(
        "influxdb",
        {
            "host": args.influx_host,
            "database": args.influx_database,
            "token": args.influx_token,
        },
    )
    quest = get_metrics_repo(
        "questdb",
        {
            "host": args.questdb_host,
            "port": args.questdb_port,
            "database": args.questdb_database,
            "user": args.questdb_user,
            "password": args.questdb_password,
            "table_name": args.questdb_table,
            "schema": args.questdb_schema,
        },
    )

    influx = influx  # type: ignore[assignment]
    quest = quest  # type: ignore[assignment]

    # Guardrail: this script must never write to InfluxDB.
    def _blocked_influx_write(*_args, **_kwargs):
        raise RuntimeError("Blocked attempt to write to InfluxDB from migration script")

    influx.write = _blocked_influx_write  # type: ignore[assignment]

    with influx, quest:
        if not influx.ping():
            print("ERROR: InfluxDB is unreachable")
            return 3
        if not quest.ping():
            print("ERROR: QuestDB is unreachable")
            return 4

        tables = _parse_tables(args.tables)
        if not tables:
            tables = influx.get_table_names()

        if not tables:
            print("No InfluxDB measurements found to migrate.")
            return 0

        where_clause = _build_where_clause(args.since, args.until)

        print("Migration plan")
        print(f"  Influx:  {args.influx_host} / {args.influx_database}")
        print(
            f"  QuestDB: {args.questdb_host}:{args.questdb_port} / {args.questdb_database} / "
            + (f"table={args.questdb_table}" if args.questdb_schema == "unified" else "schema=per_measurement")
        )
        print(f"  Tables:  {', '.join(tables)}")
        print(f"  Filter:  {where_clause if where_clause else '(none)'}")
        print(f"  Time chunk (hours): {args.time_chunk_hours}")
        if args.time_chunk_hours > 0:
            print(f"  Adaptive chunking: {args.adaptive_chunking}")
            print(f"  Min chunk (hours): {args.min_time_chunk_hours}")
            print(f"  Chunk backoff:     {args.chunk_backoff_factor}")
        print(f"  Preflight only: {args.preflight_only}")
        print(f"  Skip preflight: {args.skip_preflight}")
        print(f"  Dry run: {args.dry_run}")
        print(f"  Resume: {args.resume and not args.dry_run}")
        print(f"  Replace destination range: {args.replace_destination_range and not args.dry_run}")
        if not args.dry_run:
            print(f"  State file: {state_path}")

        if args.preflight_only and args.skip_preflight:
            print("ERROR: --preflight-only and --skip-preflight cannot be used together.")
            return 2
        if args.skip_preflight and args.time_chunk_hours <= 0 and not args.since and not args.until:
            print("ERROR: --skip-preflight without a time filter can trigger InfluxDB Core file-scan limits.")
            print("ERROR: provide --since/--until, or set --time-chunk-hours with at least --since.")
            return 2

        has_preflight_warning = False
        preflight_ranges: dict[str, tuple[dt.datetime | None, dt.datetime | None, int]] = {}
        if args.skip_preflight:
            print("\nSkipping preflight checks (--skip-preflight).")
        else:
            has_preflight_warning, preflight_ranges = _run_preflight(influx, tables, args.since, args.until)
            if has_preflight_warning:
                print("\nPreflight warnings detected. Review range coverage before migration.")

        if args.preflight_only and not args.skip_preflight:
            print("\nPreflight-only mode enabled. Exiting without migration.")
            return 0

        if args.drop_destination_table and not args.dry_run:
            if args.questdb_schema == "per_measurement":
                # Drop each individual measurement table so they are recreated fresh.
                for _t in tables:
                    print(f"Dropping destination table '{_t}'...")
                    _drop_destination_table(quest, _t)
                    quest._created_tables.discard(_t)
            else:
                print(f"Dropping destination table '{args.questdb_table}'...")
                _drop_destination_table(quest, args.questdb_table)
                # Recreate schema after drop.
                quest.close()
                quest.connect()

        total_rows_read = 0
        total_rows_written = 0
        total_rows_deleted = 0
        has_unknown_delete_counts = False
        destination_replace_supported = True

        for table in tables:
            if args.resume and not args.dry_run:
                table_state = _get_table_state(state, table)
                if bool(table_state.get("completed", False)):
                    print(f"\nSkipping measurement '{table}' (already completed in state file).")
                    continue

            print(f"\nMigrating measurement '{table}'...")
            tag_cols, field_cols = _infer_tag_and_field_columns(influx, table)
            print(f"  Inferred tags:   {tag_cols if tag_cols else '[]'}")
            print(f"  Inferred fields: {field_cols if field_cols else '[]'}")

            table_rows_read = 0
            table_rows_written = 0
            table_rows_deleted = 0
            write_buffer: list[dict[str, Any]] = []

            table_min_dt, table_max_dt, _ = preflight_ranges.get(table, (None, None, 0))
            if not args.skip_preflight and table_min_dt is None and table_max_dt is None:
                print("  Skipping table due to failed or empty preflight.")
                continue
            since_dt = _normalize_dt(_to_datetime_or_none(args.since)) or table_min_dt
            until_dt = _normalize_dt(_to_datetime_or_none(args.until)) or table_max_dt
            if args.skip_preflight and args.time_chunk_hours > 0 and since_dt and until_dt is None:
                until_dt = dt.datetime.now(tz=dt.timezone.utc)
                print(f"  Using current time as upper bound: {_fmt_dt_sql(until_dt)}")

            resume_since_dt: dt.datetime | None = None
            if args.resume and not args.dry_run:
                table_state = _get_table_state(state, table)
                resume_since_dt = _normalize_dt(_to_datetime_or_none(table_state.get("last_time")))
                if resume_since_dt:
                    since_dt = max(since_dt, resume_since_dt) if since_dt else resume_since_dt
                    print(f"  Resume checkpoint: {_fmt_dt_sql(resume_since_dt)}")

            per_table_where_clause = _build_where_clause(
                _fmt_dt_sql(since_dt) if since_dt else "",
                _fmt_dt_sql(until_dt) if until_dt else "",
            )

            if args.replace_destination_range and not args.dry_run:
                print(
                    "  Replacing destination range for idempotent replay: "
                    f"{_fmt_dt_sql(since_dt) if since_dt else '-inf'} .. "
                    f"{_fmt_dt_sql(until_dt) if until_dt else '+inf'}"
                )
                deleted = _delete_destination_range(quest, args.questdb_table, table, since_dt, until_dt)
                if deleted is None:
                    has_unknown_delete_counts = True
                    destination_replace_supported = False
                    print("  Destination rows deleted: unsupported by current QuestDB SQL dialect")
                    print("  WARNING: continuing without destination range replacement for this run")
                    print("  WARNING: reruns may duplicate rows; use --no-replace-destination-range to silence this")
                else:
                    table_rows_deleted = deleted
                    total_rows_deleted += deleted
                    print(f"  Destination rows deleted: {deleted}")

            if args.time_chunk_hours > 0 and since_dt and until_dt and since_dt < until_dt:
                print(
                    "  Using time-chunked queries: "
                    f"{_fmt_dt_sql(since_dt)} .. {_fmt_dt_sql(until_dt)} in "
                    f"{args.time_chunk_hours:g}h slices"
                )
                batch_iter = _iter_influx_batches_windowed_adaptive(
                    influx,
                    table,
                    per_table_where_clause,
                    args.query_batch_size,
                    since_dt,
                    until_dt,
                    args.time_chunk_hours,
                    args.adaptive_chunking,
                    args.min_time_chunk_hours,
                    args.chunk_backoff_factor,
                )
            else:
                batch_iter = _iter_influx_batches(influx, table, per_table_where_clause, args.query_batch_size)

            try:
                for batch_df in batch_iter:
                    rows = batch_df.to_dict(orient="records")
                    table_rows_read += len(rows)

                    for row in rows:
                        payload = _row_to_payload(table, row, tag_cols, field_cols)
                        if payload is None:
                            continue
                        write_buffer.append(payload)

                        if len(write_buffer) >= args.write_batch_size:
                            if not args.dry_run:
                                quest.write(write_buffer)
                                if args.resume:
                                    checkpoint_time = _max_payload_time(write_buffer)
                                    if checkpoint_time is not None:
                                        _update_table_checkpoint(
                                            state,
                                            state_path,
                                            table,
                                            checkpoint_time,
                                            table_rows_read,
                                            table_rows_written + len(write_buffer),
                                        )
                            table_rows_written += len(write_buffer)
                            write_buffer.clear()

                    print(f"  Read {table_rows_read} rows so far...")
            except ValueError as exc:
                if _is_influx_query_file_limit_error(exc):
                    print("ERROR: InfluxDB Core query-file-limit reached while reading source data.")
                    print("ERROR: retry with a narrower --since/--until window.")
                    print("ERROR: for large ranges, use --time-chunk-hours (for example 1 or 0.25).")
                    print("ERROR: alternatively increase InfluxDB Core --query-file-limit.")
                    return 5
                raise

            if write_buffer:
                if not args.dry_run:
                    quest.write(write_buffer)
                    if args.resume:
                        checkpoint_time = _max_payload_time(write_buffer)
                        if checkpoint_time is not None:
                            _update_table_checkpoint(
                                state,
                                state_path,
                                table,
                                checkpoint_time,
                                table_rows_read,
                                table_rows_written + len(write_buffer),
                            )
                table_rows_written += len(write_buffer)
                write_buffer.clear()

            print(f"  Completed '{table}': read={table_rows_read}, written={table_rows_written}")
            if args.replace_destination_range and not args.dry_run:
                if has_unknown_delete_counts:
                    print(f"  Deleted before replay: {table_rows_deleted if table_rows_deleted else 'unknown'}")
                else:
                    print(f"  Deleted before replay: {table_rows_deleted}")

            if args.resume and not args.dry_run:
                _mark_table_completed(state, state_path, table, table_rows_read, table_rows_written)

            total_rows_read += table_rows_read
            total_rows_written += table_rows_written

        print("\nMigration finished")
        print(f"  Total rows read:    {total_rows_read}")
        print(f"  Total rows written: {total_rows_written}")
        if args.replace_destination_range and not args.dry_run:
            if has_unknown_delete_counts:
                print(f"  Total rows deleted: {total_rows_deleted}+ (some counts unavailable)")
            else:
                print(f"  Total rows deleted: {total_rows_deleted}")
            if not destination_replace_supported:
                print("  WARNING: destination range replacement is not supported on this QuestDB instance")
                print("  WARNING: migration completed in append mode for affected tables")

    return 0


def main(args: list[str] | None = None) -> int:
    """Entry point for the migration tool."""
    parsed_args = _parse_args(args)
    return migrate(parsed_args)


if __name__ == "__main__":
    raise SystemExit(main())
