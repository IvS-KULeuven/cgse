# The Metrics Hub

## Overview

The Metrics Hub is a centralized ingestion and persistence service for telemetry and housekeeping metrics.
Services and control servers send metric points to the hub, and the hub batches these points before writing them
to the configured time-series backend.

This provides a single ingestion path and removes direct backend coupling from producers.

Core responsibilities:

- centralized ingestion for producers
- payload normalization and validation
- batch persistence to backend repositories
- runtime status and write-path observability

## Socket Endpoints

The Metrics Hub currently exposes two ZeroMQ sockets:

| Purpose              |    Pattern     | Your Socket | Endpoint             |
|----------------------|:--------------:|:-----------:|----------------------|
| Metric Ingestion     |   PUSH-PULL    |    PUSH     | tcp://localhost:6130 |
| Health/Control       | ROUTER-DEALER  |   DEALER    | tcp://localhost:6132 |

!!! note
    These default port values are defined in `cgse_core/settings.yaml` and can be overridden in the local settings.
    Ports can be static or dynamically allocated by the OS when configured as `0`. Clients discover
    the active endpoints through the Registry, especially when ports are configured as `0`.

## Metrics Payload

The canonical payload shape matches `DataPoint.as_dict()`:

```python
{
	"measurement": "camera_tm",
	"tags": {"device_id": "cam_01"},
	"fields": {"temperature": 23.4},
	"time": 1774354482.517,  # optional, unix timestamp
}
```

### Normalization Rules

- `measurement` must be a non-empty string
- `fields` must be a dictionary with at least one non-`None` value
- `None` field values are removed, not fatal
- `None` tag values are removed, not fatal
- payloads with only `None` fields are dropped

This behavior allows optional telemetry fields without dropping an otherwise valid point.

## Client Access

Any core service, control server, or script can send points to the hub.

=== "Synchronous"

	```python
	from egse.metrics import DataPoint
	from egse.metricshub.client import MetricsHubSender

	point = (
		DataPoint.measurement("camera_tm")
		.tag("device_id", "cam_01")
		.field("temperature", 23.4)
	)

	with MetricsHubSender() as sender:
		sender.send(point)
	```

=== "Asynchronous"

	```python
	from egse.metrics import DataPoint
	from egse.metricshub.client import AsyncMetricsHubSender

	point = (
		DataPoint.measurement("camera_tm")
		.tag("device_id", "cam_01")
		.field("temperature", 23.4)
	)

	with AsyncMetricsHubSender() as sender:
		await sender.send(point)
	```

## Control Actions

The control endpoint supports three actions:

- `health`: liveness check
- `info`: runtime info and statistics
- `terminate`: graceful shutdown request

## Status And Health

=== "Synchronous"

	```python
	from egse.metricshub.client import MetricsHubClient

	with MetricsHubClient() as client:
		ok = client.health_check()
		info = client.server_status()
	```

=== "Asynchronous"

	```python
	from egse.metricshub.client import AsyncMetricsHubClient

	with AsyncMetricsHubClient() as client:
		ok = await client.health_check()
		info = await client.server_status()
	```

The `info` response contains:

- collector and request ports
- backend details (`name`, repository class, reachability)
- batching config
- runtime statistics (`received`, `written`, `dropped`, `errors`, queue size)

## Running The Service

Start, stop, and inspect status from CLI:

=== "Using `uv` (preferred)"

    ```bash
    uv run cgse mh start
    uv run cgse mh stop
    uv run cgse mh status
    ```

=== "Direct (for debugging)"

    ```bash
    python -m egse.metricshub.server start
    python -m egse.metricshub.server status
    python -m egse.metricshub.server stop
    ```

## Configuration

Metrics Hub settings are defined under `Metrics Hub` in `cgse_core/settings.yaml` or local settings.

Important settings:

- `COLLECTOR_PORT`
- `REQUESTS_PORT`
- `BACKEND` (`influxdb` or `duckdb`)
- `BATCH_SIZE`
- `FLUSH_INTERVAL`

Environment variables can override these settings. Typical examples:

- `CGSE_METRICS_BACKEND`
- `CGSE_METRICS_BATCH_SIZE`
- `CGSE_METRICS_FLUSH_INTERVAL`
- backend-specific variables (`CGSE_INFLUX_*`, `CGSE_DUCKDB_PATH`)

## Control Server Integration

Control servers use `MetricsHubSender` and no longer need direct backend credentials.
When metrics hub ports are dynamic (port value `0`), the collector endpoint is resolved through the Registry service.

## Monitoring And Troubleshooting

The hub periodically logs statistics (`STATS_INTERVAL`) and reports operational state through the `status` command.
For debugging of optional-field traffic, the status output includes counters for filtered `None` fields/tags and
all-`None` payload drops.
