"""Execution of one concrete v2 phase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from harness_v2.backend.application.artifact_invalidation import ArtifactInvalidationRule
from harness_v2.backend.application.bundle_artifacts import BundleArtifactGateway, BundleRuntimeConfig
from harness_v2.backend.application.decision_service import DecisionRequest
from harness_v2.backend.application.release_context import ReleaseContextPort
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.escalation import EscalationIssue
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.domain.tasks import TaskSummary
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.clock import ClockPort
from harness_v2.backend.ports.knowledge_patch_store import KnowledgePatchStorePort


@dataclass(frozen=True, slots=True)
class PhaseExecutionContext:
    run: RunRecord
    worker_service: WorkerTaskService
    artifacts: BundleArtifactGateway
    runtime: BundleRuntimeConfig
    clock: ClockPort
    knowledge_patches: KnowledgePatchStorePort | None = None
    bundle: BundleName | None = None
    phase: PhaseName | None = None


@dataclass(frozen=True, slots=True)
class PhaseResult:
    decision_request: DecisionRequest | None = None
    escalation_issue: EscalationIssue | None = None
    tasks: tuple[TaskSummary, ...] | None = None
    events: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if self.tasks is not None:
            object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "events", tuple(self.events))


PhaseFunction = Callable[[PhaseExecutionContext], PhaseResult]


class PhaseFunctionRegistry:
    def __init__(self, handlers: dict[PhaseName, PhaseFunction]) -> None:
        self._handlers = dict(handlers)

    def get(self, phase: PhaseName) -> PhaseFunction:
        try:
            return self._handlers[phase]
        except KeyError as exc:
            from harness_v2.backend.application.contracts import InvalidRunStateError
            raise InvalidRunStateError(f"no phase handler registered for {phase.value}") from exc

    def invalidation_rules(self) -> dict[PhaseName, ArtifactInvalidationRule]:
        return PHASE_INVALIDATION_RULES


class PhaseExecutor:
    def __init__(
        self,
        artifact_store: ArtifactStorePort,
        worker_service: WorkerTaskService,
        clock: ClockPort,
        registry: PhaseFunctionRegistry,
        runtime: BundleRuntimeConfig,
        knowledge_patches: KnowledgePatchStorePort | None = None,
        release_context: ReleaseContextPort | None = None,
    ) -> None:
        self._worker_service = worker_service
        self._clock = clock
        self._registry = registry
        self._runtime = runtime
        self._knowledge_patches = knowledge_patches
        self._release_context = release_context
        self._artifact_gateway = BundleArtifactGateway(artifact_store, worker_service, self._runtime)

    def execute(self, run: RunRecord, bundle: BundleName, phase: PhaseName) -> PhaseResult:
        if run.status is not RunStatus.RUNNING or run.current_phase != phase:
            from harness_v2.backend.application.contracts import InvalidRunStateError
            raise InvalidRunStateError(f"run {run.run_id} is not running {bundle.value}/{phase.value}")
        if bundle is BundleName.EXPLORE_BUNDLE and phase is PhaseName.EXPLORE_CONTEXT_PACK and self._release_context is not None:
            self._release_context.ensure_initial_context(run)
        handler = self._registry.get(phase)
        return handler(
            PhaseExecutionContext(
                run=run,
                worker_service=self._worker_service,
                artifacts=self._artifact_gateway,
                runtime=self._runtime,
                clock=self._clock,
                knowledge_patches=self._knowledge_patches,
                bundle=bundle,
                phase=phase,
            )
        )


PHASE_INVALIDATION_RULES: dict[PhaseName, ArtifactInvalidationRule] = {
    PhaseName.EXPLORE_REQUEST_UNDERSTANDING: ArtifactInvalidationRule(artifacts=("explore/request_profile.json",), prefixes=("workers/EXPLORE_BUNDLE/EXPLORE_REQUEST_UNDERSTANDING/",)),
    PhaseName.EXPLORE_CONTEXT_PACK: ArtifactInvalidationRule(artifacts=("explore/context_pack.json",), prefixes=()),
    PhaseName.EXPLORE_EVIDENCE_DIGEST: ArtifactInvalidationRule(artifacts=("explore/evidence_digest.json",), prefixes=("workers/EXPLORE_BUNDLE/EXPLORE_EVIDENCE_DIGEST/",)),
    PhaseName.EXPLORE_EXPLORATION_MAP: ArtifactInvalidationRule(artifacts=("explore/exploration_map.json",), prefixes=()),
    PhaseName.EXPLORE_OUTCOME_SYNTHESIS: ArtifactInvalidationRule(artifacts=("explore/outcome_synthesis.json",), prefixes=("workers/EXPLORE_BUNDLE/EXPLORE_OUTCOME_SYNTHESIS/",)),
    PhaseName.EXPLORE_HANDOFF: ArtifactInvalidationRule(artifacts=("explore/outcome_bundle.json", "explore/manifest.json", "published/explore-handoff.json"), prefixes=()),
    PhaseName.PROPOSAL_DRAFT: ArtifactInvalidationRule(artifacts=("purpose/bundle.json",), prefixes=("workers/PROPOSAL_BUNDLE/PROPOSAL_DRAFT/",)),
    PhaseName.VALIDATE_JSON: ArtifactInvalidationRule(artifacts=("validation/{step_id}-purpose_bundle.json-repair.json", "validation/{step_id}-spec.json-repair.json", "validation/{step_id}-design.json-repair.json", "validation/{step_id}-tasks.json-repair.json"), prefixes=()),
    PhaseName.PROPOSAL_HANDOFF: ArtifactInvalidationRule(artifacts=("published/proposal-handoff.json",), prefixes=()),
    PhaseName.SPEC_DRAFT: ArtifactInvalidationRule(artifacts=("spec.json",), prefixes=("workers/SPEC_BUNDLE/SPEC_DRAFT/",)),
    PhaseName.SPEC_HANDOFF: ArtifactInvalidationRule(artifacts=("published/spec-handoff.json",), prefixes=()),
    PhaseName.DESIGN_DRAFT: ArtifactInvalidationRule(artifacts=("design.json",), prefixes=("workers/DESIGN_BUNDLE/DESIGN_DRAFT/",)),
    PhaseName.DESIGN_HANDOFF: ArtifactInvalidationRule(artifacts=("published/design-handoff.json",), prefixes=()),
    PhaseName.TASKS_DRAFT: ArtifactInvalidationRule(artifacts=("tasks.json",), prefixes=("workers/TASKS_BUNDLE/TASKS_DRAFT/",)),
    PhaseName.TASKS_HANDOFF: ArtifactInvalidationRule(artifacts=("published/tasks-handoff.json",), prefixes=()),
    PhaseName.KNOWLEDGE_EXTRACT_SYNTHESIS: ArtifactInvalidationRule(artifacts=("knowledge/{bundle}/synthesis.json",), prefixes=("workers/knowledge_synthesis/",)),
    PhaseName.KNOWLEDGE_EXTRACT_PATCH: ArtifactInvalidationRule(artifacts=(), prefixes=()),
    PhaseName.TDD_EXECUTE: ArtifactInvalidationRule(artifacts=("published/tdd-results.json",), prefixes=()),
    PhaseName.TDD_HANDOFF: ArtifactInvalidationRule(artifacts=("published/tdd-handoff.json",), prefixes=()),
}




def default_phase_function_registry() -> PhaseFunctionRegistry:
    from harness_v2.backend.application.phases.registry import default_phase_function_registry as create_registry

    return create_registry()
