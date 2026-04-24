# Monitoring Stack Setup

This page describes how to install and configure the telemetry visualization
stack used with CGSE: InfluxDB3 Core for storage and Grafana for visualization.

Grafana itself is not part of CGSE, but most users rely on it to inspect the
telemetry data written by CGSE into InfluxDB.

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

---

## Operational Notes

- Keep the InfluxDB token secure and avoid committing it in files.
- If Grafana is remote, ensure network access and firewall rules allow the
  required ports.
- If multiple projects share the same server, use clear naming for databases
  and Grafana data sources.
- Keep package versions aligned with your operating environment and update
  through normal change control.
