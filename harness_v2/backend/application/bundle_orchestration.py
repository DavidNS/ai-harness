"""Registry-driven SDD bundle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from harness_v2.backend.application.bundle_artifacts import (
    BundleArtifactGateway,
    BundleRuntimeConfig,
    BundleValidationError,
)
from harness_v2.backend.application.contracts import (
    CommandResult,
    InvalidRunStateError,
    PhaseCompleted,
    PhaseFailed,
    PhaseStarted,
    RunCompleted,
)
from harness_v2.backend.application.decision_service import RequestUserDecisionService, run_to_view
from harness_v2.backend.application.worker_service import WorkerTaskService
from harness_v2.backend.domain.errors import ErrorRecord
from harness_v2.backend.domain.lifecycle import LifecycleGraph, PhaseName, RunStatus, SDD_PHASES, TerminalState
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.clock import ClockPort
from harness_v2.backend.ports.state_store import StateStorePort


@dataclass(frozen=True, slots=True)
class BundleContext:
    run: RunRecord
    state_store: StateStorePort
    artifact_store: ArtifactStorePort
    worker_service: WorkerTaskService
    decision_service: RequestUserDecisionService
    artifacts: BundleArtifactGateway
    runtime: BundleRuntimeConfig


@dataclass(frozen=True, slots=True)
class BundleExecutionResult:
    waiting: CommandResult | None = None


class BundleDefinition(Protocol):
    phase: PhaseName
    failure_code: str

    def execute(self, context: BundleContext) -> BundleExecutionResult: ...


class BundleRegistry:
    def __init__(self, bundles: tuple[BundleDefinition, ...] | list[BundleDefinition]) -> None:
        by_phase: dict[PhaseName, BundleDefinition] = {}
        for bundle in bundles:
            if bundle.phase in by_phase:
                raise ValueError(f"duplicate bundle phase: {bundle.phase.value}")
            by_phase[bundle.phase] = bundle
        self._bundles = by_phase

    def get(self, phase: PhaseName) -> BundleDefinition:
        try:
            return self._bundles[phase]
        except KeyError as exc:
            raise InvalidRunStateError(f"no bundle registered for {phase.value}") from exc

    def phases(self) -> tuple[PhaseName, ...]:
        return tuple(self._bundles)

    def validate_sdd_coverage(self) -> None:
        missing = [phase.value for phase in SDD_PHASES if phase not in self._bundles]
        if missing:
            raise ValueError("bundle registry missing SDD phases: " + ", ".join(missing))


class BundleOrchestrator:
    """Execute exactly one current bundle and advance authoritative run state."""

    def __init__(
        self,
        state_store: StateStorePort,
        artifact_store: ArtifactStorePort,
        worker_service: WorkerTaskService,
        clock: ClockPort,
        registry: BundleRegistry,
        runtime: BundleRuntimeConfig,
    ) -> None:
        self._state_store = state_store
        self._artifact_store = artifact_store
        self._worker_service = worker_service
        self._clock = clock
        self._registry = registry
        self._runtime = runtime
        self._decision_service = RequestUserDecisionService(state_store, clock)
        self._artifact_gateway = BundleArtifactGateway(artifact_store, worker_service, self._runtime)

    def execute_current_phase(self, run_id: str) -> CommandResult | None:
        run = self._state_store.get(run_id)
        if run.status is not RunStatus.RUNNING or run.current_phase is None:
            return None
        try:
            bundle = self._registry.get(run.current_phase)
            result = bundle.execute(
                BundleContext(
                    run=run,
                    state_store=self._state_store,
                    artifact_store=self._artifact_store,
                    worker_service=self._worker_service,
                    decision_service=self._decision_service,
                    artifacts=self._artifact_gateway,
                    runtime=self._runtime,
                )
            )
            if result.waiting is not None:
                return result.waiting
            return self._complete_phase(run.run_id, bundle.phase)
        except Exception as exc:
            return self._fail(run_id, run.current_phase, exc)

    def _complete_phase(self, run_id: str, phase: PhaseName) -> CommandResult:
        run = self._state_store.get(run_id)
        if run.status is not RunStatus.RUNNING or run.current_phase != phase:
            raise InvalidRunStateError(f"run {run.run_id} is not running {phase.value}")
        graph = LifecycleGraph.for_strategy(run.strategy)
        next_node = graph.next_after(phase)
        completed = (*run.completed_phases, phase)
        events: list[object] = [PhaseCompleted(run.run_id, phase.value)]
        if next_node is TerminalState.COMPLETED:
            updated = run.replace(status=RunStatus.COMPLETED, current_phase=None, completed_phases=completed)
            events.append(RunCompleted(run.run_id))
        else:
            updated = run.replace(current_phase=next_node, completed_phases=completed)
            events.append(PhaseStarted(run.run_id, next_node.value))
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=tuple(events))

    def _fail(self, run_id: str, phase: PhaseName, exc: Exception) -> CommandResult:
        run = self._state_store.get(run_id)
        message = str(exc) or type(exc).__name__
        failure_code = f"{phase.value}_FAILED"
        try:
            failure_code = self._registry.get(phase).failure_code
        except Exception:
            pass
        payload = {
            "schema_version": 1,
            "phase": phase.value,
            "error": message,
            "error_type": type(exc).__name__,
        }
        content = self._artifact_gateway
        content.write_json(run_id, f"validation/{phase.value}-failure.json", payload)
        error = ErrorRecord(failure_code, message, phase=phase.value, timestamp=self._clock.now_iso())
        updated = run.replace(status=RunStatus.FAILED, current_phase=None, pending_decision=None, errors=(*run.errors, error))
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(PhaseFailed(run_id, phase.value, message),))
