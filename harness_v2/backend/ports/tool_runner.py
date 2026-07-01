"""Command execution port for controller-owned validation commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


def _command_tuple(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    command = tuple(value for value in values)
    if not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise ValueError("command must be a nonempty argv tuple")
    return command


@dataclass(frozen=True, slots=True)
class ToolRunRequest:
    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _command_tuple(self.command))
        object.__setattr__(self, "cwd", Path(self.cwd))
        if isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ToolRunResult:
    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    missing_executable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _command_tuple(self.command))
        if self.exit_code is not None and isinstance(self.exit_code, bool):
            raise TypeError("exit_code must be int or None")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise TypeError("stdout and stderr must be strings")

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and not self.missing_executable and self.exit_code == 0


class ToolRunnerPort(Protocol):
    def run(self, request: ToolRunRequest) -> ToolRunResult: ...
