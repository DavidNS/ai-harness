"""Git release lifecycle port definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

BRANCH_MODES = frozenset(("off", "current", "create", "create-from-main"))


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field)


def _text_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def _branch_mode(value: str) -> str:
    normalized = _require_text(value, "branch_mode")
    if normalized not in BRANCH_MODES:
        raise ValueError("branch_mode must be off, current, create, or create-from-main")
    return normalized


@dataclass(frozen=True, slots=True)
class GitRunRequest:
    repository: Path
    run_id: str
    request: str
    branch_mode: str = "current"

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository", Path(self.repository))
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "branch_mode", _branch_mode(self.branch_mode))


@dataclass(frozen=True, slots=True)
class GitRunResult:
    is_git_repository: bool
    current_branch: str = ""
    head: str | None = None
    origin_url: str | None = None
    origin_main: str | None = None
    dirty: bool = False
    branch_mode: str = "current"
    created_branch: str | None = None
    branch_base_ref: str | None = None
    warnings: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.is_git_repository, bool):
            raise TypeError("is_git_repository must be bool")
        if not isinstance(self.dirty, bool):
            raise TypeError("dirty must be bool")
        object.__setattr__(self, "current_branch", self.current_branch.strip() if isinstance(self.current_branch, str) else "")
        object.__setattr__(self, "head", _optional_text(self.head, "head"))
        object.__setattr__(self, "origin_url", _optional_text(self.origin_url, "origin_url"))
        object.__setattr__(self, "origin_main", _optional_text(self.origin_main, "origin_main"))
        object.__setattr__(self, "branch_mode", _branch_mode(self.branch_mode))
        object.__setattr__(self, "created_branch", _optional_text(self.created_branch, "created_branch"))
        object.__setattr__(self, "branch_base_ref", _optional_text(self.branch_base_ref, "branch_base_ref"))
        object.__setattr__(self, "warnings", _text_tuple(self.warnings, "warnings"))
        if self.schema_version != 1:
            raise ValueError("schema_version must be 1")

    def to_artifact(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "is_git_repository": self.is_git_repository,
            "current_branch": self.current_branch,
            "head": self.head,
            "origin_url": self.origin_url,
            "origin_main": self.origin_main,
            "dirty": self.dirty,
            "branch_mode": self.branch_mode,
            "created_branch": self.created_branch,
            "branch_base_ref": self.branch_base_ref,
            "warnings": list(self.warnings),
        }


class GitPort(Protocol):
    def prepare_run(self, request: GitRunRequest) -> GitRunResult: ...
