"""Application-owned escalation policy for lifecycle recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.application.artifact_invalidation import (
    ArtifactInvalidationRule,
    InvalidatedArtifact,
    invalidate_phase_artifacts,
    restore_invalidated_artifacts,
)
from harness_v2.backend.application.contracts import (
    CommandResult,
    EscalationRaised,
    EscalationResolved,
    InvalidRunStateError,
    PhaseFailed,
    PhaseStarted,
)
from harness_v2.backend.application.decision_service import run_to_view
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord
from harness_v2.backend.domain.escalation import EscalationCategory, EscalationIssue
from harness_v2.backend.domain.lifecycle import LifecycleGraph, PhaseName, RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.artifact_store import ArtifactStorePort
from harness_v2.backend.ports.clock import ClockPort
from harness_v2.backend.ports.state_store import StateStorePort


class EscalationAction(StrEnum):
    ASK_USER = "ASK_USER"
    REWIND = "REWIND"
    FAIL = "FAIL"
    CONTINUE = "CONTINUE"


@dataclass(frozen=True, slots=True)
class EscalationResolution:
    action: EscalationAction
    target_phase: PhaseName | None = None

    def __post_init__(self) -> None:
        action = EscalationAction(self.action)
        target = None if self.target_phase is None else PhaseName(self.target_phase)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "target_phase", target)
        if action is EscalationAction.REWIND and target is None:
            raise ValueError("REWIND escalation resolution requires a target phase")
        if action is not EscalationAction.REWIND and target is not None:
            raise ValueError("only REWIND escalation resolution may target a phase")


class EscalationPolicyService:
    """Resolve descriptive phase issues into authoritative lifecycle transitions."""

    def __init__(
        self,
        state_store: StateStorePort,
        artifact_store: ArtifactStorePort,
        clock: ClockPort,
        invalidation_rules: dict[PhaseName, ArtifactInvalidationRule] | None = None,
    ) -> None:
        self._state_store = state_store
        self._artifact_store = artifact_store
        self._clock = clock
        self._invalidation_rules = invalidation_rules or {}

    def execute(self, run_id: str, issue: EscalationIssue, base_run: RunRecord | None = None) -> CommandResult:
        run = base_run if base_run is not None else self._state_store.get(run_id)
        if run.run_id != run_id:
            raise InvalidRunStateError("base run does not match escalation run ID")
        if run.status is not RunStatus.RUNNING or run.current_phase is None:
            raise InvalidRunStateError(f"run {run.run_id} cannot escalate from {run.status.value}")
        if run.current_phase != issue.origin_phase:
            raise InvalidRunStateError(f"run {run.run_id} is in phase {run.current_phase.value}, not {issue.origin_phase.value}")

        raised = EscalationRaised(
            run.run_id,
            issue.issue_id,
            issue.origin_phase.value,
            issue.category.value,
            issue.reason,
        )
        resolution = self.resolve(run, issue)
        resolved = EscalationResolved(
            run.run_id,
            issue.issue_id,
            resolution.action.value,
            resolution.target_phase.value if resolution.target_phase else None,
        )
        if resolution.action is EscalationAction.CONTINUE:
            return CommandResult(run=run_to_view(run), events=(raised, resolved))
        if resolution.action is EscalationAction.REWIND:
            updated, invalidated = self._rewind(run, issue, resolution.target_phase)
            try:
                self._state_store.save(updated)
            except Exception:
                restore_invalidated_artifacts(self._artifact_store, run.run_id, invalidated)
                raise
            return CommandResult(run=run_to_view(updated), events=(raised, resolved, PhaseStarted(run.run_id, resolution.target_phase.value)))
        if resolution.action is EscalationAction.FAIL:
            updated = self._failed(run, issue)
            self._state_store.save(updated)
            return CommandResult(run=run_to_view(updated), events=(raised, resolved, PhaseFailed(run.run_id, run.current_phase.value, issue.reason)))
        raise InvalidRunStateError("ASK_USER escalation resolution must be represented by a decision request")

    def resolve(self, run: RunRecord, issue: EscalationIssue) -> EscalationResolution:
        target = self._target_for(issue.category)
        if target is None:
            return EscalationResolution(EscalationAction.FAIL)
        graph = LifecycleGraph.for_strategy(run.strategy)
        try:
            graph.validate_rewind_target(run.current_phase, target)
        except DomainValidationError:
            return EscalationResolution(EscalationAction.FAIL)
        return EscalationResolution(EscalationAction.REWIND, target)

    @staticmethod
    def _target_for(category: EscalationCategory) -> PhaseName | None:
        return {
            EscalationCategory.EXPLORATION_GAP: PhaseName.EXPLORER_DISCOVERY,
            EscalationCategory.REQUIREMENTS_GAP: PhaseName.SPEC_BUNDLE,
            EscalationCategory.DESIGN_GAP: PhaseName.DESIGN_BUNDLE,
            EscalationCategory.TASK_PLAN_GAP: PhaseName.TASKS_BUNDLE,
        }.get(category)

    def _rewind(
        self,
        run: RunRecord,
        issue: EscalationIssue,
        target_phase: PhaseName | None,
    ) -> tuple[RunRecord, tuple[InvalidatedArtifact, ...]]:
        if target_phase is None:
            raise InvalidRunStateError("rewind escalation requires a target phase")
        graph = LifecycleGraph.for_strategy(run.strategy)
        invalidated_phases = graph.phases_from(target_phase)
        invalidated = invalidate_phase_artifacts(self._artifact_store, run.run_id, invalidated_phases, self._invalidation_rules)
        tasks = () if PhaseName.TASKS_BUNDLE in invalidated_phases else run.tasks
        return (
            run.replace(
                status=RunStatus.RUNNING,
                current_phase=target_phase,
                completed_phases=graph.completed_prefix_before(target_phase),
                pending_decision=None,
                tasks=tasks,
            ),
            invalidated,
        )

    def _failed(self, run: RunRecord, issue: EscalationIssue) -> RunRecord:
        error = ErrorRecord(
            f"{issue.origin_phase.value}_ESCALATION_FAILED",
            issue.reason,
            phase=issue.origin_phase.value,
            timestamp=self._clock.now_iso(),
        )
        return run.replace(status=RunStatus.FAILED, current_phase=None, pending_decision=None, errors=(*run.errors, error))
