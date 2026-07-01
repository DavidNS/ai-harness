"""In-process host for driving the v2 backend without a daemon."""

from __future__ import annotations

from pathlib import Path

from harness_v2.adapters.clock import SystemClock
from harness_v2.adapters.id_generator import UuidIdGenerator
from harness_v2.adapters.models import ScriptedModelProvider
from harness_v2.adapters.storage import FileArtifactStore, FileStateStore, InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.contracts import Command, CommandResult, Query, QueryResult
from harness_v2.backend.application.bundle_orchestration import BundleOrchestrator
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.application.worker_service import WorkerTaskService
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
            root = Path(state_root)
            state = FileStateStore(root)
            artifacts = FileArtifactStore(root)
            clock = SystemClock()
            worker = WorkerTaskService(state, artifacts, ScriptedModelProvider(), FileWorkerResourceStore())
            orchestrator = BundleOrchestrator(
                state,
                artifacts,
                worker,
                clock,
                default_bundle_registry(),
                BundleRuntimeConfig(working_directory=Path.cwd()),
            )
            self._service = RunService(
                state,
                id_generator=UuidIdGenerator(),
                orchestrator=orchestrator,
                clock=clock,
            )
        else:
            state = state_store or InMemoryStateStore()
            artifacts = InMemoryArtifactStore()
            clock = SystemClock()
            worker = WorkerTaskService(state, artifacts, ScriptedModelProvider(), FileWorkerResourceStore())
            orchestrator = BundleOrchestrator(
                state,
                artifacts,
                worker,
                clock,
                default_bundle_registry(),
                BundleRuntimeConfig(working_directory=Path.cwd()),
            )
            self._service = RunService(
                state,
                id_generator=UuidIdGenerator(),
                orchestrator=orchestrator,
                clock=clock,
            )

    def execute(self, command: Command) -> CommandResult:
        return self._service.execute(command)

    def query(self, query: Query) -> QueryResult:
        return self._service.query(query)
