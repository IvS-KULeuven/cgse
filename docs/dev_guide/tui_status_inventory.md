# Status API Inventory (for the CGSE TUI)

This inventory records what status and lifecycle information each core service and device control server exposes
**through its client API** as of 2026-10-29. It is input for the design of a Textual TUI that shows the status of the
CGSE services and performs simple maintenance (start/stop/restart). The TUI shall use the client APIs, not parse the
text output of `cgse <service> status`. Where the APIs are insufficient, they will be enhanced (see
[Proposed API enhancements](#proposed-api-enhancements)).

File and line references are relative to `libs/cgse-core/src/` unless the path is given in full. They are a snapshot and
will drift as the code changes.

## Status access by server kind

| Server kind                     | Liveness                              | Status available by request                                                                                                               | Full status (incl. service/device extras)                                                                                                     |
|---------------------------------|---------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| Sync `ControlServer`            | `"Ping"` → `"Pong"`, `is_*_active()`  | `ServiceProxy.get_process_status()`: `timestamp, delay, PID, Up, UUID, RSS, USS, CPU User, CPU System, CPU count, CPU%` (base `CommandProtocol.get_status()` only) | The device protocol `get_status()` is published on the monitoring PUB socket only (`egse/control.py:596-600`)                                |
| `AsyncControlServer`            | `ping()`                              | `info()`: name, hostname, ports, service type, uptime as a humanized string — no PID, no process metrics                                 | `get_status()` (`schema_version, timestamp, delay, control_server, components, process`) is published on the monitoring PUB socket only (`egse/async_control.py:785`) |
| Custom asyncio ZMQ (registry, notification hub, metrics hub) | `health_check()` → `{"action": "health"}` | `server_status()` → `{"action": "info"}`, returns a dict                                                                      | n/a                                                                                                                                           |
| Logger                          | none (use `send_request("status")`)   | `send_request("status")` returns a dict                                                                                                   | n/a                                                                                                                                           |

No server currently returns its full status on request. The async `get_status()` is the shape closest to the
uniform schema we want.

`cgse core status` and every `cgse <service> status` spawn `python -m <module> status` as a subprocess and print its
text output (`cgse_core/_status.py`). `cgse <service> stop` likewise spawns `python -m <module> stop`
(`cgse_core/_stop.py`).

## Core services

| Service                         | Server kind                           | Client                                                     | Status by request                                                                                                                         | Process metrics            | Registry entry (`service_type`, metadata)                         | Remote stop                     |
|---------------------------------|---------------------------------------|------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|----------------------------|-------------------------------------------------------------------|---------------------------------|
| Service Registry (`reg_cs`)     | custom asyncio (ROUTER/PUB/ROUTER, SQLite backend) | `RegistryClient`, `AsyncRegistryClient`        | `server_status()`: ports, `enforce_unique_service_types`, `services[]` (`id, name, host, port, metadata, ttl, last_heartbeat, health`) | none                       | does not register itself                                          | `terminate_registry_server()`   |
| Logger (`log_cs`)               | custom sync REP loop, pickled strings | **no client class**, only `egse.logger.send_request(str)`  | `"status"` → `{status, logging_port, commanding_port, file_logger_level, stream_logger_level, file_logger_location}`                     | none                       | `LOG_CS`, name `log_cs`, `{receiver_port}`                       | `send_request("quit")`          |
| Configuration Manager, sync (`confman_cs`) — **production** | sync `ControlServer` | `ConfigurationManagerProxy`, `ServiceProxy`          | separate calls only: `get_obsid()`, `get_setup()` (full Setup object); obsid/setup are in the PUB status only                            | `get_process_status()`     | `CM_CS`, `{service_port, monitoring_port}`                       | `quit_server()`                 |
| Configuration Manager, async (`cm_acs`) — **not yet production** | `AsyncControlServer` | `AsyncConfigurationManagerClient`                | `info()` and `confman_status()` → `{obsid_active, obsid, setup_id, sut_id, storage_connected}`                                           | PUB only                   | `CM_ACS`, `{service_port, monitoring_port}`                      | `stop_server()`                 |
| Storage Manager (`storage_cs`)  | sync `ControlServer`                  | `StorageProxy`, `ServiceProxy`                             | separate calls: `get_storage_location`, `get_loaded_setup_id`, `get_registry_names`, `get_disk_usage`, `get_obsid`                       | `get_process_status()`     | `SM_CS`, `{service_port, monitoring_port}`                       | `quit_server()`                 |
| Process Manager (`procman_cs`)  | sync `ControlServer`                  | `ProcessManagerProxy`, `ServiceProxy`                      | `get_core_processes`, `get_device_ids`; `get_core_service_status` / `get_device_process_status` run `cgse … status` and text-match the output | `get_process_status()` | `PM_CS`, `{service_port, monitoring_port}`                       | `quit_server()`                 |
| Notification Hub (`nh_cs`)      | custom asyncio                        | `NotificationHubClient`, `AsyncNotificationHubClient` (default `localhost`, no registry lookup) | `server_status()`: ports and `statistics{events_received, events_published, last_message_time, start_time}` | none (uptime derivable from `start_time`) | `NH_CS`, `{pub_port, collector_port}` taken from settings, not the bound ports | `terminate_notification_hub()` |
| Metrics Hub (`mh_cs`)           | custom asyncio                        | `MetricsHubClient`, `AsyncMetricsHubClient` (default `localhost`, no registry lookup) | `server_status()`: batching config, `backend{name, reachable, …}`, `statistics{received, written, dropped, errors, …}` | none | `MH_CS`, `{collector_port}` (bound port)                         | `terminate_metrics_hub()` (sync client sends no-reply, cannot confirm) |

### Configuration Manager: sync vs async

`cgse cm start` and `cgse core start` launch the **sync** Configuration Manager `egse.confman.confman_cs`
(`cgse_core/_start.py:57-68`). The async version `egse.cm_acs` exists for some time but is not yet fully tested to
replace the sync version in a production environment. It is not wired into the `cgse` command; it is started with
`python -m egse.cm_acs`.

Consequences for the TUI:

- The sync CM is *the* Configuration Manager. Its status comes from `ConfigurationManagerProxy` and `ServiceProxy`.
- `cm_acs` is shown only when `CM_ACS` is registered, behind the same data-layer interface, so that switching over
  later only replaces a collector.
- `cm_acs` `confman_status()` is the model for the status section to add to the sync CM.

## Device control servers

All sync drivers expose `is_connected` and `is_simulator` as proxy commands (YAML). Registry metadata is always
`{service_port, monitoring_port}` unless noted otherwise.

| Device (package)               | Kind                     | Client                                                   | Extra `get_status()` keys (PUB only) | Connected via client                         | Simulator mode via client          | `service_type` from      | Instances                                  | `cgse <device> status`                     | Remote stop          |
|--------------------------------|--------------------------|----------------------------------------------------------|--------------------------------------|----------------------------------------------|------------------------------------|--------------------------|--------------------------------------------|--------------------------------------------|----------------------|
| TGF4000 (aim-tti-awg)          | sync                     | `Tgf4000Proxy(device_id)`                                | none                                 | `is_connected`                               | `is_simulator`                     | settings, per device_id  | multiple                                   | subprocess, text                           | `quit_server()`      |
| DT8874 (digilent)              | sync                     | `Dt8874Proxy()`                                          | none                                 | `is_connected`                               | `is_simulator`                     | settings `DT8874`        | single                                     | in-process, text                           | `quit_server()`      |
| PMX-A (kikusui-power-supply)   | sync                     | `PmxAProxy(device_id)`                                   | none                                 | `is_connected`                               | `is_simulator`                     | settings, per device_id  | multiple                                   | subprocess, text                           | `quit_server()`      |
| RSD3305P (rs-pro-power-supply) | sync                     | `Rsd3305pProxy(device_id)`                               | none                                 | `is_connected`                               | `is_simulator`                     | settings, per device_id  | multiple                                   | subprocess, text                           | `quit_server()`      |
| TCU (ariel-tcu)                | sync                     | `TcuProxy()`                                             | none                                 | `is_connected`                               | `is_simulator`                     | `TCU_CS`                 | single                                     | in-process, text                           | `quit_server()`      |
| LakeShore336 (lakeshore-tempcontrol, prototype) | sync    | `LakeShore336Proxy(device_id)`                           | none                                 | `is_connected`                               | `is_simulator`                     | = device_id              | multiple                                   | in-process, text (prints "inactive")       | `quit_server()`      |
| PUNA (symetrie-hexapod)        | sync                     | `ProxyFactory` → `PunaProxy` / `PunaPlusProxy`           | `mach, user, alength`                | `is_connected`                               | `is_simulator`                     | = device_id              | multiple, all named `puna_cs`              | in-process, text                           | `quit_server()`      |
| ZONDA (symetrie-hexapod)       | sync                     | `ZondaProxy`                                             | `mach, user, alength` (no guard for a disconnected device) | `is_connected`         | `is_simulator`                     | = device_id              | multiple, name defaults to `zonda_control_server` | in-process, text                    | `quit_server()`      |
| JORAN (symetrie-hexapod)       | sync                     | `JoranProxy(device_id)`                                  | `mach, user, alength`                | `is_connected`                               | `is_simulator`                     | = device_id              | multiple, all named `joran_cs`             | in-process, text                           | `quit_server()`      |
| DAQ6510 (keithley-tempcontrol) | async (`daq6510_acs`)    | `DAQ6510Client`                                          | `scan`, `acquisition`, `sinks`       | yes, via `health` service command and `scan_status()` | no — simulator is a separate process (`daq6510_sim`) | settings `DAQ6510` | single                                 | subprocess, prints a dict; has `start-sim`/`stop-sim`/`status-sim` | `stop_server()` |
| ThermalVac (ivs tvac)          | async (`tvac_acs`)       | `ThermalVacControlClient`                                | `scan`, `acquisition`, `sinks`       | **no** — `tvac_devif.is_connected()` exists but is not exposed | no — separate OPC UA simulator | `TVAC`                   | single                                     | in-process, prints a dict                  | `stop_server()`      |
| facility_hk (ariel-facility)   | not a ControlServer (`FacilityHousekeepingExporter`) | none, raw `send_request()`   | n/a                                  | no                                           | no                                 | lower-cased, **no metadata** | single                                 | text plus a registry listing               | `"quit"`             |
| Dummy (`egse/dummy.py`)        | sync                     | `DummyProxy`                                             | none                                 | no                                           | no                                 | **does not register**    | single                                     | not a `cgse` entry point                   | `quit_server()`      |

The Process Manager (`egse/procman/__init__.py:382-404`) derives device state by text-matching `cgse <obj> status`
output: active unless "inactive"/"not active", connected unless "not connected", simulator if "simulator". For DAQ6510
and TVAC, whose status prints a dict, this always yields connected=True and sim=False while the server is active.

## Proposed API enhancements

1. **Status on request in both base servers.** Add a `get_status` service command to the sync `ServiceProtocol`
   (`services.yaml`) that returns the *device protocol's* `get_status()`, and a `status` service command to
   `AsyncControlServer` that returns `get_status()`. This covers CM, SM, PM and all device drivers in one change.
   Normalize the process keys (`pid`, `uptime_s`, `rss`, `uss`, `cpu_percent`, …) and make `UUID` a string so the dict
   is JSON-safe.
2. **One base schema with service-specific sections**, based on the async `get_status()`: `schema_version`,
   `control_server{name, service_type, device_id, host, ports}`, `process{…}`, plus a service section. For device
   drivers add `device{connected, sim_mode}`; protocols already track `state` (`DeviceConnectionState`) but do not
   report it.
3. **Service sections for the core services**: CM sync `{obsid, setup_id, site_id}` (as `cm_acs` `confman_status`),
   SM `{storage_location, loaded_setup_id, registrations, disk_usage}`, PM `{managed processes}`.
4. **Bring the custom servers in line**: add `pid`, `uptime` and `host` to the registry, notification hub, metrics hub
   and logger status replies; give the logger a client class; let the notification hub and metrics hub clients
   discover their endpoint from the registry.
5. **Richer registry metadata**: `device_id`, `cgse_object` (the `cgse <obj>` name) and `sim_mode`. One
   `list_services()` call can then build the TUI overview and map a service to its lifecycle command, replacing the
   `SequenceMatcher` heuristic in `procman_ui.get_cgse_cmd()`.
6. **Simulator mode for async drivers** (DAQ6510, TVAC) must come from a setting or start flag, since the server
   cannot detect it is talking to a separate simulator process.
7. **Process Manager lifecycle**: `start_process` should return a result (it returns `None` now), add
   `restart_process`, and resolve the command from the service type instead of accepting shell strings. Its
   `get_*_status` methods should use the client APIs from 1–2 instead of text-matching.

## Defects found during the inventory

- TVAC: `cgse tvac` uses `start-cs`/`stop-cs` instead of `start`/`stop`, breaking the `cgse <obj> start|stop|status`
  contract the Process Manager relies on.
- JORAN: no `after_serve()`, so it never deregisters; `self.device_id` is never set.
- ZONDA: `service_name` is never set (defaults to `zonda_control_server`); `get_status()` has no guard for a
  disconnected device.
- Notification Hub: registers the ports from settings, not the bound ports, so dynamic ports (`0`) are registered as
  0; `_generate_health_response()` is never called.
- Metrics Hub: `start_time` is set with `time.time()` but compared with `time.monotonic()` in the stats reporter, so the
  logged rates are wrong.
- `ControlServer`: `__init__` sets `self.service_id` but `register_service()` assigns `self._service_id`
  (`egse/control.py:141` vs `:699`).
- Process Manager: `StatusCommand.cmd` interpolates the `device_args` list directly into the command string (runtime
  effect not verified).
- facility_hk: an unknown command gets no reply, leaving the client's REQ socket stuck.
- CLAUDE.md mentions registry ports 4242/4243; the settings use 6100–6102 (4242 is only the code fallback).
