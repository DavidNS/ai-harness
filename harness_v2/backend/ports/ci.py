"""CI release lifecycle port definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

CI_TARGETS = frozenset(("github", "gitlab", "both"))
CI_MODES = frozenset(("off", "baseline", "branch"))


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _text_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def _target(value: str) -> str:
    normalized = _require_text(value, "target")
    if normalized not in CI_TARGETS:
        raise ValueError("target must be github, gitlab, or both")
    return normalized


def _mode(value: str) -> str:
    normalized = _require_text(value, "ci_mode")
    if normalized not in CI_MODES:
        raise ValueError("ci_mode must be off, baseline, or branch")
    return normalized


@dataclass(frozen=True, slots=True)
class CiInstallRequest:
    repository: Path
    target: str = "github"
    force: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository", Path(self.repository))
        object.__setattr__(self, "target", _target(self.target))
        if not isinstance(self.force, bool):
            raise TypeError("force must be bool")


@dataclass(frozen=True, slots=True)
class CiInstallResult:
    installed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "installed", _text_tuple(self.installed, "installed"))
        object.__setattr__(self, "skipped", _text_tuple(self.skipped, "skipped"))
        object.__setattr__(self, "warnings", _text_tuple(self.warnings, "warnings"))


@dataclass(frozen=True, slots=True)
class CiSignalRequest:
    repository: Path
    ci_mode: str = "baseline"

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository", Path(self.repository))
        object.__setattr__(self, "ci_mode", _mode(self.ci_mode))


class CIPort(Protocol):
    def install_templates(self, request: CiInstallRequest) -> CiInstallResult: ...

    def status(self, repository: Path) -> dict[str, object]: ...

    def collect_signals(self, request: CiSignalRequest) -> dict[str, object]: ...
