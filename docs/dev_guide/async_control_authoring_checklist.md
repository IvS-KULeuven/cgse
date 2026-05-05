# Async Control Authoring Checklist

Use this checklist when adding a new async control server/client pair in `cgse-core` or downstream projects.

## 1. Define the server subclass

- Subclass `AsyncControlServer`.
- Set a unique `service_type` string.
- Implement `register_custom_handlers()`.
  - Register device commands with `add_device_command_handler(...)`.
  - Register service commands with `add_service_command_handler(...)`.
- Optionally override `get_service_info()` to expose server-specific metadata.

## 2. Define the client subclass

- Subclass `TypedAsyncControlClient`.
- Set the same `service_type` as the server.
- Add one method per command (for example `health()`, `move()`, `configure()`).
- Use:
  - `_success_message_as_str(...)` for string responses.
  - `_success_message_as_dict(...)` for JSON/object responses.
- Keep transport details out of business methods; call `send_device_command(...)` or `send_service_command(...)`.

## 3. Keep command contracts aligned

- Command names in client wrappers match server handler registration.
- Request payload fields are documented and validated.
- Response shape is stable and documented (`success` + `message`).
- Error responses are predictable and actionable.

## 4. Prefer explicit command channels

- Device actions: `send_device_command(...)`.
- Service/lifecycle actions: `send_service_command(...)`.
- Avoid using private client methods from application code.

## 5. Add tests for the pair

- Start the server subclass in an async test.
- Connect with the client subclass (using default class `service_type`).
- Test at least:
  - one happy-path device command,
  - one happy-path service command,
  - one failure path (unknown command or bad payload).

## 6. Validate quality gates

- Run focused tests for changed files.
- Run lint/type checks for touched files.
- Ensure no line-length/import-order regressions.

## 7. Migration notes (legacy -> async)

- Server-side "handler registration" belongs in server subclasses.
- Client-side extension is done with typed wrapper methods, not handler maps.
- If an old client called private methods directly, migrate to public wrappers.

## Minimal skeleton

```python
from typing import Any

from egse.async_control import AcquisitionAsyncControlServer
from egse.zmq_ser import zmq_json_response
from egse.async_control import TypedAsyncControlClient
from egse.zmq_ser import zmq_json_response


class MyAsyncControlServer(AsyncControlServer):
    service_type = "my-async-control-server"

    def register_custom_handlers(self):
        self.add_device_command_handler("set-mode", self._set_mode)
        self.add_service_command_handler("health", self._health)

    async def _set_mode(self, cmd: dict[str, Any]) -> list:
        mode = cmd.get("mode", "default")
        return zmq_json_response({"success": True, "message": {"mode": mode}})

    async def _health(self, cmd: dict[str, Any]) -> list:
        return zmq_json_response({"success": True, "message": {"status": "ok"}})


class MyAsyncControlClient(TypedAsyncControlClient):
    service_type = MyAsyncControlServer.service_type

    async def set_mode(self, mode: str) -> dict[str, Any] | None:
        response = await self.send_device_command({"command": "set-mode", "mode": mode})
        return self._success_message_as_dict(response, "set-mode")

    async def health(self) -> dict[str, Any] | None:
        response = await self.send_service_command("health")
        return self._success_message_as_dict(response, "health")
```

## Handle-based acquisition callback pattern

If your device driver invokes a callback with a single argument such as `callback(handle)`, do not try to force the
driver to call `on_acquisition_data(...)` directly. Instead, add a small adapter method in your server subclass that
matches the driver callback signature exactly.

The intended execution path is:

1. `start_acquisition()` registers a driver-facing callback such as `self._driver_callback`.
2. The driver calls `self._driver_callback(handle)` on its own thread.
3. `_driver_callback(handle)` extracts the data you need from `handle` and calls `self.on_acquisition_data(...)`.
4. `AsyncControlServer.on_acquisition_data(...)` performs the thread-safe handoff into the asyncio queue.
5. `AsyncControlServer.process_acquisition_data()` drains the queue.
6. Your subclass hook `handle_acquisition_record(...)` receives the normalized record and stores, logs, or forwards it.

In other words: the device callback belongs to the subclass, the queueing belongs to `AsyncControlServer`, and the
storage/logging belongs to `handle_acquisition_record(...)`.

```python
from typing import Any

from egse.async_control import AsyncControlServer


class MyHandleBasedServer(AcquisitionAsyncControlServer):
    service_type = "my-handle-based-server"

    def __init__(self, driver):
        self._driver = driver
        self._acquisition_running = False
        super().__init__()

    def register_custom_handlers(self):
        self.add_device_command_handler("start-acquisition", self._do_start_acquisition)
        self.add_device_command_handler("stop-acquisition", self._do_stop_acquisition)

    async def _do_start_acquisition(self, cmd: dict[str, Any]) -> list:
        self._driver.start_acquisition(callback=self._driver_callback)
        self._acquisition_running = True
        return zmq_json_response({"success": True, "message": {"running": True}})

    async def _do_stop_acquisition(self, cmd: dict[str, Any]) -> list:
        self._driver.stop_acquisition()
        self._acquisition_running = False
        return zmq_json_response({"success": True, "message": {"running": False}})

    def _driver_callback(self, handle):
        """Adapter that matches the driver callback signature exactly."""
        payload = self._extract_payload_from_handle(handle)
        self.on_acquisition_data(
            payload,
            source="my-device",
            metadata={"handle_type": type(handle).__name__},
        )

    def _extract_payload_from_handle(self, handle) -> dict[str, Any]:
        """Read the data immediately if the handle is only valid during the callback."""
        return {
            "timestamp": handle.timestamp,
            "value": handle.value,
            "status": handle.status,
        }

    async def handle_acquisition_record(self, record: dict[str, Any]):
        self.logger.info("Received acquisition record: %s", record["data"])
```

Notes:

- Prefer extracting plain Python data from the driver handle inside `_driver_callback(...)`. Many drivers only keep the
  handle or buffer valid during the callback.
- You usually do not need to override `get_acquisition_callback()` for this pattern.
- Keep `_driver_callback(...)` short. Do not do DB writes, network calls, or other slow work there.
- If you need batch storage, override `handle_acquisition_batch(...)`; otherwise only override
  `handle_acquisition_record(...)`.

## Sequential execution across clients and timers

If both external clients and internal tasks (timers/background jobs) touch the same device,
route those operations through `AsyncControlServer._execute_sequential(...)`.

This creates one serialized hardware lane across all call sites.

```python
import asyncio
from typing import Any

from egse.async_control import AsyncControlServer
from egse.zmq_ser import zmq_json_response


class MySequentialServer(AsyncControlServer):
    service_type = "my-sequential-server"

    def __init__(self, driver):
        self._driver = driver
        super().__init__()

    def register_custom_handlers(self):
        self.add_device_command_handler("fetch", self._do_fetch)

    async def _do_fetch(self, cmd: dict[str, Any]) -> list:
        # External client request goes through the same serialized lane.
        value = await self._execute_sequential(
            asyncio.to_thread(self._driver.fetch_reading)
        )
        return zmq_json_response({"success": True, "message": {"value": value}})

    async def poll_timer_tick(self):
        # Internal timer work uses the same lane, preventing command/timer races.
        value = await self._execute_sequential(
            asyncio.to_thread(self._driver.fetch_reading)
        )
        self.logger.info("Polled device reading: %s", value)
```

Notes:

- Device command handlers are already processed one-by-one, but `_execute_sequential(...)`
  is still useful to serialize device access across *multiple sources*.
- Use `asyncio.to_thread(...)` inside `_execute_sequential(...)` for blocking driver APIs.
