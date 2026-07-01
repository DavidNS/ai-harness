"""Repository snapshot and rollback ports for bounded TDD mutation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


def _path_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if isinstance(value, str) and value.strip())
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    files: dict[str, bytes]
    directories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "files", dict(self.files))
        object.__setattr__(self, "directories", _path_tuple(self.directories, "directories"))


@dataclass(frozen=True, slots=True)
class RepositoryDiff:
    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "added", _path_tuple(self.added, "added paths"))
        object.__setattr__(self, "modified", _path_tuple(self.modified, "modified paths"))
        object.__setattr__(self, "deleted", _path_tuple(self.deleted, "deleted paths"))

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(sorted({*self.added, *self.modified, *self.deleted}))


class RepositorySnapshotPort(Protocol):
    def capture(self, root: object) -> RepositorySnapshot: ...

    def diff(self, before: RepositorySnapshot, after: RepositorySnapshot) -> RepositoryDiff: ...


class RepositoryRollbackPort(Protocol):
    def restore(self, root: object, snapshot: RepositorySnapshot) -> None: ...
