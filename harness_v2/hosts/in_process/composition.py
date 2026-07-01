"""Composition helpers for the in-process host."""

from __future__ import annotations

from pathlib import Path

from harness_v2.adapters.clock import SystemClock
from harness_v2.adapters.id_generator import UuidIdGenerator
from harness_v2.adapters.git import FilesystemRepositoryAdapter
from harness_v2.adapters.models import ScriptedModelProvider
from harness_v2.adapters.storage import FileArtifactStore, FileStateStore, InMemoryArtifactStore, InMemoryStateStore
from harness_v2.adapters.tools import SubprocessToolRunner
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.bundle_orchestration import BundleOrchestrator
from harness_v2.backend.application.bundle_registry import default_bundle_registry
from harness_v2.backend.application.run_service import RunService
from harness_v2.backend.application.tdd_loop import TddLoopService
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.event_sink import EventSinkPort
from harness_v2.backend.ports.state_store import StateStorePort


def build_file_backed_service(
    root: Path | str,
    *,
    event_sink: EventSinkPort | None = None,
    working_directory: Path | str | None = None,
    allow_repository_mutation: bool = False,
) -> RunService:
    root_path = Path(root)
    state = FileStateStore(root_path)
    artifacts = FileArtifactStore(root_path)
    return _build_service(
        state,
        artifacts,
        event_sink=event_sink,
        working_directory=working_directory,
        allow_repository_mutation=allow_repository_mutation,
    )


def build_memory_service(
    state_store: StateStorePort | None = None,
    *,
    event_sink: EventSinkPort | None = None,
    working_directory: Path | str | None = None,
    allow_repository_mutation: bool = False,
) -> RunService:
    state = state_store or InMemoryStateStore()
    artifacts = InMemoryArtifactStore()
    return _build_service(
        state,
        artifacts,
        event_sink=event_sink,
        working_directory=working_directory,
        allow_repository_mutation=allow_repository_mutation,
    )


def _build_service(
    state: StateStorePort,
    artifacts: ArtifactStorePort,
    *,
    event_sink: EventSinkPort | None,
    working_directory: Path | str | None,
    allow_repository_mutation: bool,
) -> RunService:
    clock = SystemClock()
    worker = WorkerTaskService(state, artifacts, ScriptedModelProvider(), FileWorkerResourceStore())
    repository = FilesystemRepositoryAdapter()
    tdd_loop = TddLoopService(repository=repository, rollback=repository, tool_runner=SubprocessToolRunner())
    registry = default_bundle_registry(tdd_loop=tdd_loop)
    orchestrator = BundleOrchestrator(
        state,
        artifacts,
        worker,
        clock,
        registry,
        BundleRuntimeConfig(
            working_directory=Path.cwd() if working_directory is None else Path(working_directory),
            allow_repository_mutation=allow_repository_mutation,
        ),
    )
    return RunService(
        state,
        id_generator=UuidIdGenerator(),
        orchestrator=orchestrator,
        clock=clock,
        artifact_store=artifacts,
        invalidation_rules=registry.invalidation_rules(),
        event_sink=event_sink,
    )
