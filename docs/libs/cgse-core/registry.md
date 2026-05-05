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

    with AsyncRegistryClient() as client:
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

    with AsyncRegistryClient() as client:
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
## Server Behavior

The server implementation is `AsyncRegistryServer`.
It uses a pluggable backend (`AsyncSQLiteBackend` by default) and handles:

- request processing on the request socket
- heartbeat renewals on the heartbeat socket
- cleanup of expired services
- publication of registry events (`register`, `deregister`, `expire`)

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

Optional CLI parameters include `req_port`, `pub_port`, `hb_port`, `db_path`, and `cleanup_interval`.

In core-service orchestration this service is referred to as `rm_cs`.

## Status And Health

- `health` returns simple liveness (`success`, `status`, `timestamp`)
- `info` returns runtime details including request/publication/heartbeat ports and current registrations

You can query these through:

- `RegistryClient.health_check()` / `AsyncRegistryClient.health_check()`
- `RegistryClient.server_status()` / `AsyncRegistryClient.server_status()`

## Configuration

The Registry server can be configured via CLI parameters and defaults from the `egse.registry` module constants.
For deployments that need custom ports or storage path, pass explicit CLI options when starting the server.

## Monitoring And Troubleshooting

### Registry is not reachable

- Verify the process is running
- Verify request port matches your client endpoint
- Check local firewall/network namespace constraints

### Services disappear unexpectedly

- Confirm heartbeats are started (`start_heartbeat`)
- Check TTL value vs heartbeat interval
- Check cleanup interval and long event-loop blocking in your service

### Discovery returns no service

- Verify `service_type` matches what services registered
- Confirm service health (heartbeat renewals)
- Inspect `status` output to verify active registrations