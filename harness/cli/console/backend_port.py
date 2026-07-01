"""Backend port used by the command frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class InvocationResult:
    code: int


class ConsoleBackendPort(Protocol):
    def status(self) -> int: ...

    def runs(self) -> int: ...

    def start_request(self, request: str) -> int: ...

    def dispatch_action(self, command: str, args: tuple[str, ...], raw_tail: str = "") -> int: ...
