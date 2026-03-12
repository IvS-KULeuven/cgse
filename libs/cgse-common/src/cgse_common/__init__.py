from dataclasses import dataclass


@dataclass
class AppState:
    """Global Typer app parameters."""

    verbose: bool = False
