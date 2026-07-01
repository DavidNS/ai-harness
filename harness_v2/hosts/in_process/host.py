"""In-process host for driving the v2 backend without a daemon."""

from __future__ import annotations

from harness_v2.backend.application.contracts import Command, Query
from harness_v2.backend.application.run_service import InMemoryRunService


class InProcessHost:
    """Thin host boundary that delegates commands and queries to application services."""

    def __init__(self, service: InMemoryRunService | None = None) -> None:
        self._service = service or InMemoryRunService()

    def execute(self, command: Command) -> object:
        return self._service.execute(command)

    def query(self, query: Query) -> object:
        return self._service.query(query)

