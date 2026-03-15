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

from egse.async_control import AsyncControlServer
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
