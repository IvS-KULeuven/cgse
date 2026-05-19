# Monitoring Stack Setup

This page describes how to install and configure the telemetry visualization
stack used with CGSE: InfluxDB3 Core or QuestDB for storage and Grafana for visualization.

Grafana itself is not part of CGSE, but most users rely on it to inspect the
telemetry data written by CGSE into InfluxDB or QuestDB.

For dashboard usage, see [Using Grafana](../user_guide/grafana.md).

For developer details on how CGSE writes telemetry, see
[Monitoring and Telemetry in CGSE](../dev_guide/monitoring.md).

---

## Installation

The steps below assume installation on the server that hosts the telemetry
stack.

### Install InfluxDB3 Core

The easiest way to install InfluxDB 3 Core for Linux or Mac is with the following command. This will install the latest release on your system.

```bash
curl -O https://www.influxdata.com/d/install_influxdb3.sh && sh install_influxdb3.sh
```

For a more in-depth explanation, check out the InfuxDB documentation to [Install InfluxDB 3 Core](https://docs.influxdata.com/influxdb3/core/install/).

In order to manage the database, you will need to create an admin token:

```bash
influxdb3 create token --admin
```

Export the returned token (that starts with `apiv3_`) as the environment variable `INFLUXDB3_AUTH_TOKEN` and reload your terminal session.
Store this token securely, Grafana and other administration tasks depend on it.

!!!WARNING
    Don't push your admin InfluxDB token to a (remote) repository. Too many users put it in a `.env` file and forget to _git ignore_ that file. Don't make that mistake!

### Install QuestDB

QuestDB is an alternative time-series backend supported by CGSE. The easiest way to run QuestDB is with Docker:

```bash
docker run -d --name questdb \
    -p 9000:9000 -p 8812:8812 \
    questdb/questdb
```

This exposes the web console on port `9000` and the PGWire SQL port on `8812`.

#### Install QuestDB from a tar archive (Linux)

If Docker is not available, download the Linux binary from the [QuestDB releases page](https://github.com/questdb/questdb/releases/latest). The Linux package includes a bundled JVM so no prior Java installation is needed:

```bash
# Download the latest Linux release (replace the version as needed)
wget https://github.com/questdb/questdb/releases/download/9.3.5/questdb-9.3.5-rt-linux-amd64.tar.gz

# Extract
tar -xzf questdb-9.3.5-rt-linux-amd64.tar.gz
cd questdb-9.3.5-rt-linux-amd64

# Start QuestDB
./questdb.sh start
```

To stop or check status:

```bash
./questdb.sh stop
./questdb.sh status
```

The data directory defaults to `$HOME/.questdb`. Pass `-d /path/to/data` to `questdb.sh` to use a different location. For platforms without a bundled JVM (e.g. ARM Linux), download the `no-jre` variant and ensure Java 17 is available on your system.

QuestDB does not require an authentication token by default (the default credentials are `admin` / `quest`). Update `CGSE_QUESTDB_USER` and `CGSE_QUESTDB_PASSWORD` if you configure custom credentials.

### Install Grafana

Installing Grafana is a bit more complicated and it's best that you follow the official installation from the [GrafanaLabs](https://grafana.com/docs/grafana/latest/setup-grafana/installation/) installation page. After installation, start the required services if they are not already running.

---

## Basic Verification

After installation, verify core components:

1. InfluxDB is reachable and has your target database.
2. Grafana is reachable via `http://localhost:3000` (or server host and port).
3. You can create and test an InfluxDB data source in Grafana.

Use these commands to inspect InfluxDB:

```bash
influxdb3 show databases
influxdb3 query --database <database name> "SHOW TABLES"
```

If no tables are present yet, that usually means no CGSE process has written
telemetry to the selected database.

To verify QuestDB, open the web console at `http://localhost:9000` or run a query via the CGSE admin tool:

```bash
cgse admin sql --backend questdb 'SELECT table_name FROM tables()'
```

---

## Operational Notes

- Keep the InfluxDB token secure and avoid committing it in files.
- If Grafana is remote, ensure network access and firewall rules allow the
  required ports.
- If multiple projects share the same server, use clear naming for databases
  and Grafana data sources.
- Keep package versions aligned with your operating environment and update
  through normal change control.

---

## Data Migration: InfluxDB to QuestDB

When migrating historical metrics from InfluxDB to QuestDB, CGSE uses a state tracking file to manage resumable, incremental migration. This prevents duplicate data transfer and allows safe recovery from interruptions.

### Migration State File

**Location:** `.migrate_influx_to_questdb.state.json` (in the relevant project/library directory)

**Purpose:** Tracks the progress of data migration from InfluxDB to QuestDB on a per-table basis.

**File structure:**
```json
{
  "version": 1,
  "tables": {
    "<measurement_name>": {
      "completed": true,
      "last_time": "2026-03-25T12:00:05.463840Z",
      "rows_read": 180040,
      "rows_written": 180040,
      "updated_at": "2026-04-27T10:45:22.699261Z"
    }
  }
}
```

**Fields:**
- `version`: Schema version of the state file (for future compatibility)
- `tables`: Dictionary of migration progress per measurement/table
  - `completed`: Whether migration for this table is finished
  - `last_time`: Timestamp of the last row migrated (used to resume incremental migrations)
  - `rows_read`: Total rows read from InfluxDB
  - `rows_written`: Total rows successfully written to QuestDB
  - `updated_at`: When this record was last updated

### Migration Workflow

1. Migration script reads the state file
2. Skips tables marked as `completed: true`
3. For incomplete tables, uses `last_time` to only migrate newer data (avoiding duplicates)
4. Updates row counts and timestamps as data transfers
5. On completion, sets `completed: true`

This design ensures:
- **Idempotent execution**: Re-running the migration script is safe
- **Resumable**: Interrupted migrations can pick up where they left off
- **No duplicates**: Only unmigrated data is transferred in subsequent runs
- **Audit trail**: Complete row counts and timestamps are retained

### Running the Migration Tool

The migration tool is integrated into CGSE as an administrative subcommand.

**Basic usage:**

```bash
cgse admin migrate-influx-to-questdb
```

The tool reads configuration from environment variables and falls back to defaults:

- InfluxDB: `CGSE_INFLUX_HOST`, `CGSE_INFLUX_DATABASE`, `INFLUXDB3_AUTH_TOKEN`
- QuestDB: `CGSE_QUESTDB_HOST`, `CGSE_QUESTDB_PORT`, `CGSE_QUESTDB_DATABASE`, `CGSE_QUESTDB_USER`, `CGSE_QUESTDB_PASSWORD`, `CGSE_QUESTDB_TABLE`, `CGSE_QUESTDB_SCHEMA`

**Common options:**

- `--dry-run`: Preview row counts and inferred schemas without writing to QuestDB
- `--preflight-only`: Run preflight visibility checks and exit
- `--skip-preflight`: Skip preflight checks and proceed directly
- `--tables cm,storagecontrolserver`: Migrate only specific measurements (comma-separated)
- `--since 2026-01-01T00:00:00Z --until 2026-03-01T00:00:00Z`: Migrate a specific time range
- `--state-file <path>`: Path to the state file (default: `.migrate_influx_to_questdb.state.json`)
- `--resume`: Resume from saved checkpoints (default: enabled)
- `--reset-state`: Delete existing state file before starting (starts fresh)
- `--questdb-schema unified|per_measurement`: Choose target schema (default from env or `unified`)
- `--drop-destination-table`: Drop and recreate the destination table before migrating
- `--replace-destination-range`: Delete destination rows in the migrated time range before writing, making reruns idempotent (default: enabled)
- `--write-batch-size N`: Rows per QuestDB write call (default: `5000`)
- `--query-batch-size N`: Rows fetched per InfluxDB query batch (default: `10000`)
- `--time-chunk-hours N`: Split large time ranges into chunks of N hours (default: disabled)
- `--adaptive-chunking`: Automatically reduce chunk size on query failures (default: enabled)

All connection parameters (`--questdb-host`, `--questdb-port`, `--questdb-database`, `--questdb-user`, `--questdb-password`, `--questdb-table`, `--influx-host`, `--influx-database`, `--influx-token`) can also be passed directly as CLI flags to override environment variables.

**Examples:**

```bash
# Dry-run to see what would be migrated
cgse admin migrate-influx-to-questdb --dry-run

# Migrate all measurements (creates state file for resumption)
cgse admin migrate-influx-to-questdb

# Resume an interrupted migration (picks up from last checkpoint)
cgse admin migrate-influx-to-questdb

# Migrate only selected measurements into QuestDB per_measurement schema
cgse admin migrate-influx-to-questdb \
    --tables DAQ6510,hexapod \
    --questdb-schema per_measurement

# Migrate a specific time range
cgse admin migrate-influx-to-questdb \
    --since 2026-01-01T00:00:00Z \
    --until 2026-03-01T00:00:00Z

# Start fresh (reset state and re-migrate everything)
cgse admin migrate-influx-to-questdb --reset-state
```

**State file location:**

By default, the state file is created in the current working directory as `.migrate_influx_to_questdb.state.json`. You can specify a different location with `--state-file <path>` if needed for multiple concurrent migrations or to organize state files per project.

---

## Execute SQL via CGSE Admin

Use the `cgse admin sql` command to run SQL directly against supported metrics backends (`questdb`, `duckdb`, `influxdb`) without switching tools.

Read-only statements are allowed by default. Mutating statements (`DROP`, `ALTER`, `DELETE`, `INSERT`, ...) require `--allow-write`.

### Examples

```bash
# Read-only query on QuestDB (default backend)
cgse admin sql 'SELECT table_name FROM tables()'

# Drop a typed measurement table in QuestDB
cgse admin sql --allow-write 'DROP TABLE IF EXISTS "mh_load_schema";'

# Run SQL on DuckDB
cgse admin sql --backend duckdb --duckdb-path metrics.duckdb 'SELECT COUNT(*) AS n FROM timeseries;'

# Run SQL on InfluxDB
cgse admin sql --backend influxdb --influx-database cgse 'SHOW TABLES'
```

### Notes

- Backend aliases are accepted (`quest`, `duck`, `influx`).
- Result rows are printed as JSON objects (with `--max-rows` limit).
- For InfluxDB, set `INFLUXDB3_AUTH_TOKEN` or pass `--influx-token`.
