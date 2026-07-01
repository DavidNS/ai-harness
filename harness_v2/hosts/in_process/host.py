"""In-process host for driving the v2 backend without a daemon."""

from __future__ import annotations

from pathlib import Path

from harness_v2.adapters.id_generator import UuidIdGenerator
from harness_v2.adapters.storage import FileStateStore, InMemoryStateStore
from harness_v2.backend.application.contracts import Command, CommandResult, Query, QueryResult
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.ports.state_store import StateStorePort


class InProcessHost:
    """Thin host boundary that wires adapters and delegates to application services."""

    def __init__(
        self,
        service: RunService | None = None,
        state_store: StateStorePort | None = None,
        state_root: Path | str | None = None,
    ) -> None:
        configured = sum(value is not None for value in (service, state_store, state_root))
        if configured > 1:
            raise ValueError("provide only one of service, state_store, or state_root")
        if service is not None:
            self._service = service
        elif state_root is not None:
            self._service = RunService(FileStateStore(state_root), id_generator=UuidIdGenerator())
        else:
            self._service = RunService(state_store or InMemoryStateStore(), id_generator=UuidIdGenerator())

    def execute(self, command: Command) -> CommandResult:
        return self._service.execute(command)

    def query(self, query: Query) -> QueryResult:
        return self._service.query(query)
