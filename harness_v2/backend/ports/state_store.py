"""State persistence ports for v2 backend runs."""

from __future__ import annotations

from typing import Protocol

from harness_v2.backend.domain.runs import RunRecord


class StateStoreError(RuntimeError):
    """Base error for state store failures."""


class StateNotFoundError(StateStoreError):
    """Raised when persisted run state does not exist."""


class StateStoreCorruptionError(StateStoreError):
    """Raised when persisted run state is malformed or invalid."""


class StateStorePort(Protocol):
    """Authoritative run state persistence boundary."""

    def save(self, run: RunRecord) -> None: ...

    def get(self, run_id: str) -> RunRecord: ...

    def list_all(self) -> tuple[RunRecord, ...]: ...

    def list_active(self) -> tuple[RunRecord, ...]: ...

    def list_completed(self) -> tuple[RunRecord, ...]: ...
