# Status API Inventory (for the CGSE TUI)

This inventory records what status and lifecycle information each core service and device control server exposes
**through its client API** as of 2026-10-29. It is input for the design of a Textual TUI that shows the status of the
CGSE services and performs simple maintenance (start/stop/restart). The TUI shall use the client APIs, not parse the
text output of `cgse <service> status`. Where the APIs are insufficient, they will be enhanced (see
[Proposed API enhancements](#proposed-api-enhancements)).

File and line references are relative to `libs/cgse-core/src/` unless the path is given in full. They are a snapshot and
will drift as the code changes.

The tables below are the **baseline** before the status report was added. What has been implemented since is described
in [The status report](#the-status-report) and marked in [Proposed API enhancements](#proposed-api-enhancements).

## The status report

Merged in PR #449 (core) and one PR per device package, #450–#458 (aim-tti, kikusui, rs-pro, digilent, ariel-tcu,
symetrie, lakeshore, daq6510, tvac). The registry metadata `server_kind` was added in PR #460.

Every control server returns a status report on request, with the same layout for sync and async servers:

| Server kind          | Request                                                                     |
|----------------------|-----------------------------------------------------------------------------|
| Sync `ControlServer` | `ServiceProxy.get_status_report()`, service command `get_status_report`     |
| `AsyncControlServer` | `get_status_report()` on the async client, service command `status_report`  |

```text
schema_version   1
timestamp        ISO 8601, UTC
control_server   name, service_type, device_id, hostname, device_commanding_port, service_commanding_port,
                 monitoring_port
process          pid, uptime_s, uuid, rss, uss, cpu_user_s, cpu_system_s, cpu_count, cpu_percent
device           None for services without a device, otherwise {connected, sim_mode}
details          service or device specific status
```

- `process` comes from `ProcessStatus.as_status_dict()`: normalized keys, the UUID as a string. The status published on
  the monitoring port and `get_process_status()` keep the old keys.
- `device` comes from `get_device_status()`. `connected` tells whether the connection to the device is open; the device
  itself is not queried, so a status request never blocks a control server or disconnects a device. `sim_mode` is the
  protocol's `simulator` flag for the sync drivers, and `None` (unknown) for DAQ6510 and TVAC.
- `details` comes from `get_status_details()` (sync, by default the entries the device protocol adds to its
  `get_status()`) or `get_component_status()` (async). CM: `obsid_active, obsid, setup_id, site_id`. SM:
  `storage_location, disk_usage, loaded_setup_id, obsid, registrations`. PM: `core_processes`.
- When `device` or `details` cannot be retrieved, that section contains only an `error` entry.
- Only `control_server`, `process` and `device` are guaranteed JSON-safe. Sync `details` travel over pickle and may hold
  any value a device protocol puts there, e.g. `NaN` in the `alength` of the hexapods, which is not valid strict JSON.
- A server only offers the new request after a restart with the new code. Clients such as the TUI need a fallback (e.g.
  `get_process_status()`) for servers that don't have it.
- Every driver was checked in simulator mode with a live request, except LakeShore336 (see the defects below).

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

1. **Done — status on request in both base servers.** Implemented as `get_status_report` (sync) and `status_report`
   (async), see [The status report](#the-status-report). The monitoring status is unchanged; the normalized process
   keys are only in the new report.
2. **Done — one base schema with service-specific sections**, including `device{connected, sim_mode}` for all device
   drivers.
   *Correction:* this item first stated that the protocols already track `state` (`DeviceConnectionState`) and only
   need to report it. That is not the case: only PUNA and ZONDA update `state`, in all other drivers it stays
   `DEVICE_NOT_CONNECTED`. `connected` is therefore taken from the open connection of each driver (a new
   `is_connection_open()`, or an existing `is_connected()` that doesn't query the device).
3. **Done — service sections for the core services**: CM sync `{obsid_active, obsid, setup_id, site_id}`, SM
   `{storage_location, disk_usage, loaded_setup_id, obsid, registrations}`, PM `{core_processes}`. The device ids are
   not in the PM section, because `get_device_ids()` loads the Setup on every call and the PM serves requests on a
   single thread.
4. **Partly done — bring the custom servers in line.** Done on `feat/registry-process-status`: the process information
   of every service is in the registry instead of in the status replies. The registry client adds `pid` and
   `start_time` to every registration, every heartbeat carries the process status (`egse.process.process_status()`),
   and the registry keeps it with the registration (`status` in `list_services()`); the registry's own `info` reply
   has its `pid`, `start_time` and process status. Still open: a client class for the logger, and endpoint discovery
   from the registry in the notification hub and metrics hub clients.
5. **Partly done — richer registry metadata.** Every registration has `server_kind` (`sync`, `async`, `notifyhub`,
   `metricshub`, or `command` for the logger and facility_hk), which tells a client how to ask for the status. Still
   open: `device_id`, `cgse_object` (the `cgse <obj>` name) and `sim_mode`. One `list_services()` call can then map a
   service to its lifecycle command, replacing the `SequenceMatcher` heuristic in `procman_ui.get_cgse_cmd()`.
6. **Open — simulator mode for async drivers** (DAQ6510, TVAC) must come from a setting or start flag, since the
   server cannot detect it is talking to a separate simulator process. Until then they report `sim_mode: None`.
7. **Open — Process Manager lifecycle**: `start_process` should return a result (it returns `None` now), add
   `restart_process`, and resolve the command from the service type instead of accepting shell strings. Its
   `get_*_status` methods should use the status report instead of text-matching. This is part of a broader refactor of
   the Process Manager, which is too complex and uses blocking calls.

## Defects

### Fixed

- TVAC: `cgse tvac` used `start-cs`/`stop-cs` instead of `start`/`stop`, breaking the `cgse <obj> start|stop|status`
  contract the Process Manager relies on. Fixed in PR #441 (`feat/tvac-cgse-subcommands`).
- JORAN: no `after_serve()`, so it never deregistered and the process didn't exit after `joran_cs stop` (the registry
  heartbeat thread kept running). Fixed in PR #455.
- JORAN: the control server didn't start: it required a telemetry dictionary in the Setup, loaded `joran.yaml` from the
  wrong location, and `JoranInterface` lacked the `DeviceInterface` methods. Fixed in PR #455.
- TGF4000: the simulator and the proxy required `HOSTNAME`/`PORT` in the device settings (an unused
  `ethernet_interface` was created in `Tgf4000Interface`), and the control server settings used `HOST` while the code
  reads `HOSTNAME`. Fixed in PR #450.
- PMX-A: `pmx_a_cs start --sim` crashed with `NotImplementedError` when the Storage Manager was running, the simulator
  didn't implement `get_current()`/`get_voltage()`. Fixed in PR #451.
- Lost requests: the registry server, notification hub, metrics hub and async control server waited for a request with
  `asyncio.wait_for(socket.recv_multipart(), timeout=…)` and cancelled the receive when the timeout expired. A request
  that arrived just when the receive was cancelled was lost, and the client timed out. A client that polls in a fixed
  rhythm (like the TUI, every 2 s) drifted through this window every few polls, which made services flap between ok
  and stale in the TUI. Found on 2026-10-31: the registry logged no `Received request` for the requests that timed
  out. Confirmed on a test registry by sending each request a fixed delay after the previous reply: at 996 ms 9 of 10
  requests were lost, at all other delays none. Fixed in PR #461: the receive loops wait with
  `egse.zmq_ser.wait_for_message()` (a `poll()` that doesn't take the message) and receive only when a message is
  there; with the fix, no request was lost at any delay, and the TUI had no timeouts. The TUI still tolerates one lost
  request per polled server (stale after three polls plus one request timeout), e.g. for a server that is busy.
- Notification Hub: registered the ports from its settings, not the bound ports, so dynamic ports (`0`) were
  registered as 0. Fixed on `feat/registry-process-status`.
- facility_hk: registered without metadata. Fixed on `feat/registry-process-status`: it registers
  `server_kind: "command"`.
- Dummy control server: didn't register. Fixed on `feat/registry-process-status`: it registers as `DUMMY_CS` when a
  registry is available, and keeps working without one (its ports are fixed in the settings).
- Registry clients (`RegistryClient` and `AsyncRegistryClient`) use a DEALER socket and don't match replies to
  requests. A request that timed out stayed queued, and the next request read the reply to an earlier one. Found with
  the TUI on 2026-10-30: after a registry restart, `list_services()` read a `health` reply and returned no services
  (the TUI now uses a new client for every poll). On 2026-11-01 the notification hub and the metrics hub dropped out of
  the registry for good: their health checks timed out at start-up (13:09, before the registry answered), and when
  the laptop lid was closed (13:12) the re-registration after an IP address change read a late `health` reply, logged
  `Service registered with ID: None`, and the cleared service id stopped the heartbeat loop. Fixed on
  `fix/registry-client-stale-replies`: after a timeout or ZeroMQ error the client replaces the socket (new identity),
  a registration only succeeds with a `service_id` in the reply, and a failed re-registration keeps the service id so
  the heartbeat retries. Regression tests in `libs/cgse-core/tests/test_registry_client_recovery.py`.
- CLAUDE.md mentioned registry ports 4242/4243; the settings use 6100/6101/6102 (4242/4243 are only the code fallback
  in `egse/registry/__init__.py`). Fixed in the local CLAUDE.md, which is not tracked by git.

### Open

- JORAN: `self.device_id` is never set, the status report shows `device_id: null`.
- JORAN: `JoranController.__init__` would fail with real hardware: `{JORAN_SETTINGS.IP}` creates a set instead of a
  string, and `super.__init__()` is missing the parentheses. `joran.py` also loads `joran.yaml` without a location
  into the unused `DEVICE_SETTINGS`.
- ZONDA: `service_name` is never set (defaults to `zonda_control_server`); `get_status()` has no guard for a
  disconnected device.
- Hexapods: the status details contain `NaN` (`alength`), which is not valid strict JSON.
- Hexapods: `dynalpha.py` uses `telnetlib`, which is removed in Python 3.13.
- LakeShore336 (prototype): `lakeshore336_cs.py` has no `if __name__ == "__main__"`, so `python -m
  egse.tempcontrol.lakeshore.lakeshore336_cs` and therefore `cgse lakeshore336 start --background` silently do
  nothing. The protocol needs a Setup with `gse.tempcontrol.lakeshore336[<device_id>].input_channels`, also with
  `--sim`, so it could not be checked live.
- TGF4000: `tgf4000.py` defines several methods more than once (ruff F811), e.g. `set_am_frequency` three times.
- `ControlServer`: `ProcessStatus` registers its Prometheus metrics without a unique prefix, so only one sync control
  server can be created per Python process (relevant for tests).
- Process Manager: `get_device_ids()` / `get_devices()` load the Setup on every call, which blocks the single-threaded
  server.
- `get_host_ip()` returns another address when the Wi-Fi is down, e.g. on 2026-11-01 after the laptop lid was closed
  the heartbeat of the notification hub detected an IP address change from `192.168.68.75` to `100.66.244.53` (the
  `100.64.0.0/10` range, used by Tailscale) and re-registered with that address. Clients on the same machine still
  connect, clients on other machines may not.
- Registry clients: in `RegistryClient` the heartbeat thread calls `health_check()` and `reregister()`, which use the
  request socket of the main thread (ZeroMQ sockets are not thread-safe); after a timeout that socket is now also
  replaced from the heartbeat thread. In both heartbeat loops, a failed health check (`continue`) skips the sleep, so
  during an outage the loop retries after each heartbeat plus health check timeout.
- Notification Hub: `_generate_health_response()` is never called.
- Metrics Hub: `start_time` is set with `time.time()` but compared with `time.monotonic()` in the stats reporter, so the
  logged rates are wrong.
- `ControlServer`: `__init__` sets `self.service_id` but `register_service()` assigns `self._service_id`
  (`egse/control.py:141` vs `:699`).
- Process Manager: `StatusCommand.cmd` interpolates the `device_args` list directly into the command string (runtime
  effect not verified).
- facility_hk: an unknown command gets no reply, leaving the client's REQ socket stuck.
- Tests failing on `main`, independent of these changes: `ariel-tcu` `test_tcu.py::test_set_prof_gen_axis_speed`,
  `cgse-core` `test_async_control.py::test_control_server` (its log capture is empty) and
  `test_client_server_interaction.py::test_proxy_without_cs`, and 10 tests in `cgse-common`. The `cgse-common` and
  `cgse-core` tests cannot run in one pytest process, both have a `tests/fixtures` package.
- `cgse-core` test suite is timing dependent when no core services are running: the outcome differs from run to run,
  and a run sometimes doesn't finish. Seen on 2026-10-30:
  - `test_connect.py::test_circuit_break_async`, a long-running test that checks that reconnecting ends in a circuit
    break, sometimes fails quickly and sometimes takes longer than 60 s.
  - `test_registry_service.py::test_server_is_running` (only an `asyncio.sleep(10)` with a registry on the test
    ports) sometimes takes longer than 60 s, after which the following tests in that file error and the run stops
    making progress. The file passes on its own.
  - `test_registry_backend.py`: `test_sqlite_persistence[True]`, `test_sqlite_persistence[False]` and
    `test_sqlite_backend_resilience` error because they request the async fixture `sqlite_only`, which pytest-asyncio
    doesn't handle.

  To do: make the async tests independent of a running registry and of timing (explicit timeouts), fix the
  `sqlite_only` fixture, and run the suite repeatedly (e.g. twice in CI) to catch flaky tests.
