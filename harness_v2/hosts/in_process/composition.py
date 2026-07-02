"""Composition helpers for the in-process host."""

from __future__ import annotations

from pathlib import Path

from harness_v2.adapters.clock import SystemClock
from harness_v2.adapters.id_generator import UuidIdGenerator
from harness_v2.adapters.git.release import GitCommandAdapter
from harness_v2.adapters.ci.local import LocalCIAdapter
from harness_v2.adapters.models import CliModelProvider
from harness_v2.adapters.storage import (
    FileArtifactStore,
    FileKnowledgePatchStore,
    FileStateStore,
    InMemoryArtifactStore,
    InMemoryKnowledgePatchStore,
    InMemoryStateStore,
)
from harness_v2.adapters.worker_resources import FileWorkerResourceStore
from harness_v2.backend.application.bundle_artifacts import BundleRuntimeConfig
from harness_v2.backend.application.phase_executor import PhaseExecutor, default_phase_function_registry
from harness_v2.backend.application.run_orchestrator import RunOrchestrator
from harness_v2.backend.application.release_context import ReleaseContextService, ReleaseRuntimeConfig
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.event_sink import EventSinkPort
from harness_v2.backend.ports.knowledge_patch_store import KnowledgePatchStorePort
from harness_v2.backend.ports.model_provider import ModelProviderPort
from harness_v2.backend.ports.state_store import StateStorePort


def build_file_backed_service(
    root: Path | str,
    *,
    event_sink: EventSinkPort | None = None,
    working_directory: Path | str | None = None,
    allow_repository_mutation: bool = False,
    branch_mode: str = "current",
    github_ci_mode: str = "baseline",
    model_provider: ModelProviderPort | None = None,
    model_provider_name: str = "codex",
) -> RunOrchestrator:
    root_path = Path(root)
    state = FileStateStore(root_path)
    artifacts = FileArtifactStore(root_path)
    knowledge_root = Path.cwd() if working_directory is None else Path(working_directory)
    knowledge = FileKnowledgePatchStore(knowledge_root)
    return _build_service(
        state,
        artifacts,
        knowledge,
        event_sink=event_sink,
        working_directory=working_directory,
        allow_repository_mutation=allow_repository_mutation,
        branch_mode=branch_mode,
        github_ci_mode=github_ci_mode,
        model_provider=model_provider,
        model_provider_name=model_provider_name,
    )


def build_memory_service(
    state_store: StateStorePort | None = None,
    *,
    event_sink: EventSinkPort | None = None,
    working_directory: Path | str | None = None,
    allow_repository_mutation: bool = False,
    branch_mode: str = "current",
    github_ci_mode: str = "baseline",
    model_provider: ModelProviderPort | None = None,
    model_provider_name: str = "codex",
) -> RunOrchestrator:
    state = state_store or InMemoryStateStore()
    artifacts = InMemoryArtifactStore()
    knowledge = InMemoryKnowledgePatchStore()
    return _build_service(
        state,
        artifacts,
        knowledge,
        event_sink=event_sink,
        working_directory=working_directory,
        allow_repository_mutation=allow_repository_mutation,
        branch_mode=branch_mode,
        github_ci_mode=github_ci_mode,
        model_provider=model_provider,
        model_provider_name=model_provider_name,
    )


def _build_service(
    state: StateStorePort,
    artifacts: ArtifactStorePort,
    knowledge_patches: KnowledgePatchStorePort,
    *,
    event_sink: EventSinkPort | None,
    working_directory: Path | str | None,
    allow_repository_mutation: bool,
    branch_mode: str,
    github_ci_mode: str,
    model_provider: ModelProviderPort | None,
    model_provider_name: str,
) -> RunOrchestrator:
    clock = SystemClock()
    provider = model_provider or CliModelProvider.for_name(model_provider_name)
    worker = WorkerTaskService(state, artifacts, provider, FileWorkerResourceStore())
    registry = default_phase_function_registry()
    working_path = Path.cwd() if working_directory is None else Path(working_directory)
    release_context = ReleaseContextService(
        artifacts,
        GitCommandAdapter(),
        LocalCIAdapter(),
        ReleaseRuntimeConfig(working_directory=working_path, branch_mode=branch_mode, ci_mode=github_ci_mode),
    )
    phase_executor = PhaseExecutor(
        artifacts,
        worker,
        clock,
        registry,
        BundleRuntimeConfig(
            working_directory=working_path,
            allow_repository_mutation=allow_repository_mutation,
        ),
        knowledge_patches=knowledge_patches,
        release_context=release_context,
    )
    return RunOrchestrator(
        state,
        id_generator=UuidIdGenerator(),
        phase_executor=phase_executor,
        clock=clock,
        artifact_store=artifacts,
        invalidation_rules=registry.invalidation_rules(),
        event_sink=event_sink,
        release_context=release_context,
        knowledge_patches=knowledge_patches,
    )
