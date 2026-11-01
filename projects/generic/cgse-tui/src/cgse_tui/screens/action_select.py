"""The dialog to start, stop or restart a service."""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Checkbox
from textual.widgets import Static

from cgse_tui.data.actions import SIMULATOR_OPTION
from cgse_tui.data.actions import SIMULATOR_PROCESS
from cgse_tui.data.actions import display
from cgse_tui.data.actions import lifecycle_command
from cgse_tui.data.model import ServiceInfo

ACTIONS = ("start", "stop", "restart")


def available_actions(service: ServiceInfo, running: bool) -> set[str]:
    """Start when the service is not running, stop and restart when it is; nothing without a `cgse` command."""
    if lifecycle_command(service, "start") is None:
        return set()
    return {"stop", "restart"} if running else {"start"}


def simulator_label(service: ServiceInfo, support: str | None) -> str:
    if support == SIMULATOR_PROCESS:
        return f"Use the simulator, started first with: cgse {service.cgse_object} start-sim"
    if support == SIMULATOR_OPTION:
        return "Use the simulator: start with --sim"
    return "Use the simulator (no simulator for this service)"


class ActionSelectScreen(ModalScreen[tuple[str, bool] | None]):
    """Shows the commands for a service and returns the selected action and simulator choice, None when cancelled.

    Selecting an action is the confirmation, the dialog shows the commands that will run. The simulator checkbox is
    enabled when the service has a simulator, it is checked when the service runs with its simulator now.

    Args:
        service: the selected service.
        running: True when the service is running, see `Collector.is_running()`.
        simulator_support: coroutine function that tells how the service is started with a simulator, see
            `ServiceActions.simulator_support()`. The checkbox stays disabled when None.
    """

    DEFAULT_CSS = """
    ActionSelectScreen {
        align: center middle;
    }
    ActionSelectScreen #dialog {
        width: 76;
        max-width: 100%;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    ActionSelectScreen #simulator {
        margin-top: 1;
    }
    ActionSelectScreen #buttons {
        height: auto;
        margin-top: 1;
    }
    ActionSelectScreen Button {
        margin-right: 1;
    }
    ActionSelectScreen Button.-style-default:focus {
        text-style: bold;  /* the same as without focus, the lighter background shows the focus */
        background-tint: $foreground 25%;
    }
    """

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(
        self,
        service: ServiceInfo,
        running: bool,
        simulator_support: Callable[[ServiceInfo], Awaitable[str | None]] | None = None,
    ):
        super().__init__()
        self.service = service
        self.running = running
        self.actions = available_actions(service, running)
        self._simulator_support = simulator_support

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(Text.assemble((self.service.name, "bold"), f" ({self.service.service_type})"), id="title")
            yield Static(self._description(), id="description")
            yield Checkbox(
                "Use the simulator (checking ...)", value=self.service.sim_mode is True, disabled=True, id="simulator"
            )
            with Horizontal(id="buttons"):
                for action in ACTIONS:
                    variant = "error" if action == "stop" else "primary"
                    yield Button(action.capitalize(), id=action, variant=variant, disabled=action not in self.actions)
                yield Button("Cancel", id="cancel")

    def _description(self) -> Text:
        if not self.actions:
            return Text("No cgse command is known for this service, it can't be started or stopped from the TUI.")
        commands = [display(lifecycle_command(self.service, action)) for action in ("start", "stop")]
        state = "running" if self.running else "not running"
        return Text.assemble(
            f"The service is {state}. Commands:\n",
            *((f"  {command}\n", "bold") for command in commands),
            "Restart runs both.",
        )

    def on_mount(self) -> None:
        # Enter starts a service that is not running; stopping a running service needs a deliberate choice
        self.query_one("#start" if "start" in self.actions else "#cancel", Button).focus()
        if self.actions - {"stop"} and self._simulator_support is not None:
            self.run_worker(self._check_simulator(), group="simulator")
        else:
            self.query_one("#simulator", Checkbox).display = False

    async def _check_simulator(self) -> None:
        support = await self._simulator_support(self.service)
        checkbox = self.query_one("#simulator", Checkbox)
        checkbox.label = simulator_label(self.service, support)
        checkbox.disabled = support is None
        if support is None:
            checkbox.value = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        else:
            self.dismiss((event.button.id, self.query_one("#simulator", Checkbox).value))
