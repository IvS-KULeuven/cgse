# The Service Registry

## Overview

The Service Registry is the *central discovery mechanism* for CGSE services.
Services register at startup, renew with heartbeats, and deregister on shutdown.
Other components discover active services by `service_type` instead of hardcoded
endpoints.

A primary reason for the Service Registry is dynamic port allocation for device services.
Services can bind to runtime-assigned ports and publish their resolved endpoints, while
clients discover them without hardcoded host-port pairs.

Core responsibilities:

- registration and deregistration
- service discovery
- heartbeat-based liveness
- cleanup of expired registrations
- publication of registry state-change events

## Socket Endpoints

The Registry server exposes three ZeroMQ sockets:

| Purpose            |    Pattern     | Your Socket | Default Endpoint      |
|--------------------|:--------------:|:-----------:|-----------------------|
| Service requests   | ROUTER-DEALER  |   DEALER    | tcp://localhost:6100  |
| Registry events    |    PUB-SUB     |     SUB     | tcp://localhost:6101  |
| Heartbeats         | ROUTER-DEALER  |   DEALER    | tcp://localhost:6102  |

!!! note
    These default port values are defined in `cgse_core/settings.yaml` and can be overridden in the local settings.
    Ports can be static or dynamically allocated by the OS when configured as `0`. Clients discover
    the active endpoints through the Registry, especially when ports are configured as `0`.

## Client Access

Use `AsyncRegistryClient` in async applications and `RegistryClient` in synchronous ones.
Both clients support the same core operations.

### Register A Service

=== "Asynchronous"

    ```python
    from egse.registry.client import AsyncRegistryClient

    async with AsyncRegistryClient() as client:
        service_id = await client.register(
            name="cm_cs",
            host="127.0.0.1",
            port=6110,
            service_type="CM_CS",
            metadata={"service_port": 6112, "monitoring_port": 6111},
            ttl=30,
        )

        if service_id:
            await client.start_heartbeat()
    ```

=== "Synchronous"

    ```python
    from egse.registry.client import RegistryClient

    with RegistryClient() as client:
        service_id = client.register(
            name="cm_cs",
            host="127.0.0.1",
            port=6110,
            service_type="CM_CS",
            metadata={"service_port": 6112, "monitoring_port": 6111},
            ttl=30,
        )

        if service_id:
            client.start_heartbeat()
    ```

### Discover A Service

=== "Asynchronous"

    ```python
    from egse.registry.client import AsyncRegistryClient

    async with AsyncRegistryClient() as client:
        service = await client.discover_service("CM_CS")
        if service:
            endpoint = f"tcp://{service['host']}:{service['port']}"
    ```

=== "Synchronous"

    ```python
    from egse.registry.client import RegistryClient

    with RegistryClient() as client:
        service = client.discover_service("CM_CS")
        if service:
            endpoint = f"tcp://{service['host']}:{service['port']}"
    ```

### Services On The Same Machine

A service registers the address of its network interface, and its machine identity (`machine_id` in the metadata: the
host name and, on Linux, the machine id from `/etc/machine-id`). When a client gets a service that runs on its own
machine (`discover_service()`, `get_service()`, `list_services()`, `get_endpoint()`), the `host` is `127.0.0.1` and
the registered address is in `registered_host`. Local clients keep reaching the services when the network is gone,
e.g. on a laptop without WiFi, or when it changes address. Clients on other machines get the registered address.

The machine is recognised by its identity, never by its addresses: these change with the network or a VPN (e.g.
Tailscale). A registration of an older version has no `machine_id`, its `host` is returned unchanged.

Two machines with the same host name and the same `/etc/machine-id` (e.g. cloned from one disk image without a new
machine id, see `systemd-machine-id-setup`) can't be told apart: give each machine its own machine id.

### The Metadata Of A Registration

The registry clients add to the metadata of every registration:

| Key          | Value                                                                        |
|--------------|------------------------------------------------------------------------------|
| `pid`        | the PID of the service process                                               |
| `start_time` | the start time of the service process [s since the epoch]                    |
| `machine_id` | the machine identity, see above (`egse.system.get_machine_id()`)             |

The control servers (sync and async) also register:

| Key               | Value                                                                                   |
|-------------------|-----------------------------------------------------------------------------------------|
| `service_port`    | the port of the service commands                                                        |
| `monitoring_port` | the port where the status is published                                                  |
| `server_kind`     | how to ask the service for its status, see below                                        |
| `cgse_object`     | the `cgse <object>` command of the service, e.g. `puna` for `cgse puna start`           |
| `device_id`       | the instance of the device, the argument of `cgse <object> start <device_id>`, or None  |

`server_kind` is `sync` or `async` for the control servers, `notifyhub`, `metricshub`, or `command` for the servers
that answer the pickled string command `"status"` (the logger, the log-files service and the ARIEL facility
housekeeping exporter). The notification hub, the metrics hub, the logger, the log-files service and the ARIEL facility
housekeeping exporter add `cgse_object` (`nh`, `mh`, `log`, `lf`, `facility_hk`) to their own metadata.

The process manager and the CGSE TUI find the devices of the Setup by `cgse_object` and `device_id`, see
[The Setup](../cgse-common/setup.md).

### The Status Of The Service Process

Every heartbeat carries the status of the service process, from `egse.process.process_status()`: `pid`, `uptime_s`,
`rss`, `swap`, `cpu_user_s`, `cpu_system_s` and `cpu_percent`. The registry keeps the last status with the
registration; `list_services()` and `get_service()` return it as `status`, and `last_heartbeat` tells its age. A
heartbeat without status, from an older client, keeps the previous status.

The heartbeat interval is a third of the TTL of the registration (30 s by default), unless `start_heartbeat()` gets
another interval.

### Registry Events

The registry publishes the events `register`, `deregister` and `expire`, and a `status` event every second (see
below). `RegistryClient` doesn't subscribe to the events. `AsyncRegistryClient` subscribes only when the events are
used: `on_event(event_type, handler)` and `start_event_listener()`.

## Server Behavior

The server implementation is `AsyncRegistryServer`.
It uses a pluggable backend (`AsyncSQLiteBackend` by default) and handles:

- request processing on the request socket
- heartbeat renewals on the heartbeat socket
- cleanup of expired services
- publication of registry events (`register`, `deregister`, `expire`), and a `status` event every second with the
  PID and start time of the registry (`pid`, `start_time`), to know that it is alive or was restarted

## Control Actions

The request socket supports these actions:

- `register`
- `deregister`
- `renew`
- `get`
- `list`
- `discover`
- `health`
- `info`
- `terminate`

A request that times out leaves its reply behind on the DEALER socket. The clients therefore close the socket after a
timeout or a ZeroMQ error and open a new one, so the next request can't read that late reply.

## Running The Service

Start, inspect, and stop the Registry service:

=== "Using `uv` (preferred)"

    ```bash
    uv run cgse reg start
    uv run cgse reg stop
    uv run cgse reg status
    uv run cgse reg list-services
    ```

=== "Direct (for debugging)"

    ```bash
    python -m egse.registry.server start
    python -m egse.registry.server status
    python -m egse.registry.server stop
    ```

`cgse reg start` takes `--enforce-unique-service-types` (one service per service type, the default from the
settings) or `--allow-duplicate-service-types`, and `--log-level`. `cgse reg deregister <service_type>` removes the
registrations of a service type, e.g. of a service that was killed.

The options of `python -m egse.registry.server start` are `--req-port`, `--pub-port`, `--hb-port`, `--db-path`,
`--cleanup-interval`, `--enforce-unique-service-types` and `--log-level`. Its script is `reg_cs`.

## Status And Health

- `health` returns simple liveness (`success`, `status`, `timestamp`)
- `info` returns runtime details: the request, publication and heartbeat ports, whether service types are unique,
  `cgse_object` `reg`, the PID, start time and process status (`process`) of the registry, and the current
  registrations. The registry doesn't register itself, `info` is where its own process information is.

You can query these through:

- `RegistryClient.health_check()` / `AsyncRegistryClient.health_check()`
- `RegistryClient.server_status()` / `AsyncRegistryClient.server_status()`

## Configuration

Settings are loaded from `Service Registry` in `cgse_core/settings.yaml`:

- `REQUESTER_PORT`, `PUBLISHER_PORT`, `HEARTBEAT_PORT`: the ports, the defaults of the CLI options
- `CLEANUP_INTERVAL`: how often expired registrations are removed [s], when `--cleanup-interval` is not given
- `UNIQUE_SERVICE_TYPES`: one service per service type (`true`), or several for pooling

The SQLite database is `service_registry.db` in the working directory of the registry, unless `--db-path` is given.

## Monitoring And Troubleshooting

### Registry is not reachable

- Verify the process is running
- Verify request port matches your client endpoint
- Check local firewall/network namespace constraints

### Services disappear unexpectedly

- Confirm heartbeats are started (`start_heartbeat`), and check `last_heartbeat` with `cgse reg list-services`
- Check TTL value vs heartbeat interval
- Check cleanup interval and long event-loop blocking in your service

### Discovery returns no service

- Verify `service_type` matches what services registered
- Confirm service health (heartbeat renewals)
- Inspect `status` output to verify active registrations