"""Provider contracts used by the controller."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Captured outcome of one bounded provider process."""

    stdout: str
    stderr: str
    exit_code: int | None
    duration_seconds: float
    timed_out: bool = False
    truncated: bool = False

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and self.exit_code == 0


ProviderProgress = Callable[[str, str], None]


@runtime_checkable
class Provider(Protocol):
    """Minimal provider interface; implementations must not use a shell."""

    def run_prompt(
        self,
        prompt: str,
        *,
        cwd: Path,
        permissions: Mapping[str, object] | None = None,
        progress: ProviderProgress | None = None,
        temp_dir: Path | None = None,
    ) -> ProviderResult: ...


Command = Sequence[str]
