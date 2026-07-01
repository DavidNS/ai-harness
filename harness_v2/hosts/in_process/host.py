"""In-process host for driving the v2 backend without a daemon."""

from __future__ import annotations

from harness_v2.adapters.storage import InMemoryStateStore
from harness_v2.backend.application.contracts import Command, Query
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.ports.state_store import StateStorePort


class InProcessHost:
    """Thin host boundary that wires adapters and delegates to application services."""

    def __init__(self, service: RunService | None = None, state_store: StateStorePort | None = None) -> None:
        if service is not None and state_store is not None:
            raise ValueError("provide either service or state_store, not both")
        self._service = service or RunService(state_store or InMemoryStateStore())

    def execute(self, command: Command) -> object:
        return self._service.execute(command)

    def query(self, query: Query) -> object:
        return self._service.query(query)
