# Monitoring and Telemetry in CGSE

CGSE can propagate housekeeping and metrics data from control server processes to
InfluxDB. Grafana can then be used to visualize these metrics.

This page is developer-focused: it explains how CGSE structures telemetry data
and how that data reaches InfluxDB.

For stack installation and system configuration, see
[Monitoring Stack Setup](../admin_guide/monitoring.md).

For day-to-day Grafana usage and dashboard creation, see
[Using Grafana](../user_guide/grafana.md).

---

## Database Structure

Understanding this structure helps when you add new telemetry producers or when
you troubleshoot missing fields in Grafana.

### Database Name

In the current implementation, the name of the database in which all CGSE metrics are stored is taken from the `CGSE_INFLUX_DATABASE` environment variable. If that environment variable is not set, the `PROJECT` environment variable is used with `cgse` as final fallback for the database name. This keeps the database name aligned with the active project context.

To inspect the available database names, execute this in a terminal on the server:

```bash
influxdb3 show databases
```

To create a database manually, execute:

```bash
influxdb3 create database <database name>
```

### Table Names

Each process writes to a dedicated table. The table name matches the storage
mnemonic of the process in lower case.

To list the available tables, execute this in a terminal on the server:

```bash
influxdb3 query --database <database name> "SHOW TABLES"
```

Note that a table is often also called a measurement. They are basically the same thing, just different names for the same concept, depending on context:

- When you interact with InfluxDB using line protocol (the native InfluxDB write format), it's called a measurement.
- When you query using SQL (which InfluxDB 3 supports natively), that same entity appears as a table.

### Content of the Tables

For each table, the column names are the names of the corresponding
housekeeping and metrics parameters. The timestamp column is named `TIME`.

To inspect the columns of a table, execute this in a terminal on the server:

```bash
influxdb3 query --database <database name> "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '<table name>'"
```

To inspect the stored data in ascending timestamp order, execute:

```bash
influxdb3 query --database <database name> "SELECT * FROM <table name> ORDER BY TIME"
```

Add a time range to restrict the data range:
```bash
influxdb3 query --database <database name> "SELECT * FROM <table name> WHERE time >= now() - interval '10 minutes' ORDER BY TIME"
```

---

## Propagating Metrics to InfluxDB via Python

To populate metrics in InfluxDB, CGSE uses the `influxdb3-python` package. This
dependency is defined in the `pyproject.toml` file of the `cgse-common`
module.

When implementing a new device, no additional propagation code is typically
needed. Metrics propagation is handled automatically in the `serve` method of
`ControlServer`.

When housekeeping information is written to CSV, `ControlServer.propagate_metrics(..)`
is called and writes the corresponding metrics to InfluxDB.

---

## Design Notes

Open questions are tracked in the roadmap under
[Monitoring and Telemetry](../roadmap.md#monitoring-and-telemetry).
