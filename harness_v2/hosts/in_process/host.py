"""In-process host for driving the v2 backend without a daemon."""

from __future__ import annotations

from pathlib import Path

from harness_v2.backend.application.contracts import Command, CommandResult, Query, QueryResult
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.ports.event_sink import EventSinkPort
from harness_v2.backend.ports.state_store import StateStorePort
from harness_v2.hosts.in_process.composition import build_file_backed_service, build_memory_service


class InProcessHost:
    """Thin host boundary that wires adapters and delegates to application services."""

    def __init__(
        self,
        service: RunService | None = None,
        state_store: StateStorePort | None = None,
        state_root: Path | str | None = None,
        event_sink: EventSinkPort | None = None,
        working_directory: Path | str | None = None,
        allow_repository_mutation: bool = False,
    ) -> None:
        configured = sum(value is not None for value in (service, state_store, state_root))
        if configured > 1:
            raise ValueError("provide only one of service, state_store, or state_root")
        if service is not None:
            if event_sink is not None:
                raise ValueError("event_sink cannot be combined with an injected service")
            if working_directory is not None or allow_repository_mutation:
                raise ValueError("runtime TDD options cannot be combined with an injected service")
            self._service = service
        elif state_root is not None:
            self._service = build_file_backed_service(
                state_root,
                event_sink=event_sink,
                working_directory=working_directory,
                allow_repository_mutation=allow_repository_mutation,
            )
        else:
            self._service = build_memory_service(
                state_store,
                event_sink=event_sink,
                working_directory=working_directory,
                allow_repository_mutation=allow_repository_mutation,
            )

    def execute(self, command: Command) -> CommandResult:
        return self._service.execute(command)

    def query(self, query: Query) -> QueryResult:
        return self._service.query(query)
