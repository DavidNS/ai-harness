"""Application-owned escalation policy for bundle lifecycle recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from harness_v2.backend.application.artifact_invalidation import ArtifactInvalidationRule, InvalidatedArtifact, invalidate_step_artifacts, restore_invalidated_artifacts
from harness_v2.backend.application.contracts import BundleStarted, CommandResult, EscalationRaised, EscalationResolved, InvalidRunStateError, StepFailed, StepStarted
from harness_v2.backend.application.decision_service import run_to_view
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord
from harness_v2.backend.domain.escalation import EscalationCategory, EscalationIssue
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
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
    target_bundle: BundleName | None = None

    def __post_init__(self) -> None:
        action = EscalationAction(self.action)
        target = None if self.target_bundle is None else BundleName(self.target_bundle)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "target_bundle", target)
        if action is EscalationAction.REWIND and target is None:
            raise ValueError("REWIND escalation resolution requires a target bundle")
        if action is not EscalationAction.REWIND and target is not None:
            raise ValueError("only REWIND escalation resolution may target a bundle")


class EscalationPolicyService:
    def __init__(self, state_store: StateStorePort, artifact_store: ArtifactStorePort, clock: ClockPort, invalidation_rules: dict[PhaseName, ArtifactInvalidationRule] | None = None) -> None:
        self._state_store = state_store
        self._artifact_store = artifact_store
        self._clock = clock
        self._invalidation_rules = invalidation_rules or {}

    def execute(self, run_id: str, issue: EscalationIssue, base_run: RunRecord | None = None) -> CommandResult:
        run = base_run if base_run is not None else self._state_store.get(run_id)
        if run.run_id != run_id:
            raise InvalidRunStateError("base run does not match escalation run ID")
        if run.status is not RunStatus.RUNNING or run.current_bundle is None or run.current_step_id is None:
            raise InvalidRunStateError(f"run {run.run_id} cannot escalate from {run.status.value}")
        if run.current_bundle != issue.origin_bundle:
            raise InvalidRunStateError(f"run {run.run_id} is in bundle {run.current_bundle.value}, not {issue.origin_bundle.value}")

        raised = EscalationRaised(run.run_id, issue.issue_id, issue.origin_bundle.value, issue.category.value, issue.reason)
        resolution = self.resolve(run, issue)
        resolved = EscalationResolved(run.run_id, issue.issue_id, resolution.action.value, resolution.target_bundle.value if resolution.target_bundle else None)
        if resolution.action is EscalationAction.CONTINUE:
            return CommandResult(run=run_to_view(run), events=(raised, resolved))
        if resolution.action is EscalationAction.REWIND:
            updated, invalidated = self._rewind(run, resolution.target_bundle)
            try:
                self._state_store.save(updated)
            except Exception:
                restore_invalidated_artifacts(self._artifact_store, run.run_id, invalidated)
                raise
            assert updated.current_bundle is not None and updated.current_step_id is not None
            return CommandResult(run=run_to_view(updated), events=(raised, resolved, BundleStarted(run.run_id, updated.current_bundle.value), StepStarted(run.run_id, updated.current_step_id, updated.current_bundle.value, updated.current_phase.value)))
        if resolution.action is EscalationAction.FAIL:
            updated = self._failed(run, issue)
            self._state_store.save(updated)
            assert run.current_bundle is not None and run.current_phase is not None
            return CommandResult(run=run_to_view(updated), events=(raised, resolved, StepFailed(run.run_id, run.current_step_id, run.current_bundle.value, run.current_phase.value, issue.reason)))
        raise InvalidRunStateError("ASK_USER escalation resolution must be represented by a decision request")

    def resolve(self, run: RunRecord, issue: EscalationIssue) -> EscalationResolution:
        target = self._target_for(issue.category)
        if target is None or run.current_phase is None:
            return EscalationResolution(EscalationAction.FAIL)
        steps = bundle_catalog.linearize_bundle(run.root_bundle)
        current_index = bundle_catalog.step_for_step_id(run.root_bundle, run.current_step_id).step_index
        target_indexes = [index for index, step in enumerate(steps) if step.bundle_name is target]
        if not target_indexes or target_indexes[0] > current_index:
            return EscalationResolution(EscalationAction.FAIL)
        return EscalationResolution(EscalationAction.REWIND, target)

    @staticmethod
    def _target_for(category: EscalationCategory) -> BundleName | None:
        return {
            EscalationCategory.EXPLORATION_GAP: BundleName.EXPLORE_BUNDLE,
            EscalationCategory.REQUIREMENTS_GAP: BundleName.SPEC_BUNDLE,
            EscalationCategory.DESIGN_GAP: BundleName.DESIGN_BUNDLE,
            EscalationCategory.TASK_PLAN_GAP: BundleName.TASKS_BUNDLE,
        }.get(category)

    def _rewind(self, run: RunRecord, target_bundle: BundleName | None) -> tuple[RunRecord, tuple[InvalidatedArtifact, ...]]:
        if target_bundle is None:
            raise InvalidRunStateError("rewind escalation requires a target bundle")
        target_steps = [step for step in bundle_catalog.linearize_bundle(run.root_bundle) if step.bundle_name is target_bundle]
        if not target_steps:
            raise InvalidRunStateError(f"bundle {target_bundle.value} is not in {run.root_bundle.value}")
        target_step = target_steps[0]
        try:
            invalidated_step_ids = bundle_catalog.step_ids_from(run.root_bundle, target_step.step_id)
            completed_prefix = bundle_catalog.completed_prefix_before(run.root_bundle, target_step.step_id)
        except DomainValidationError as exc:
            raise InvalidRunStateError(str(exc)) from exc
        invalidated = invalidate_step_artifacts(self._artifact_store, run.run_id, run.root_bundle, invalidated_step_ids, self._invalidation_rules)
        invalidated_bundles = set(bundle_catalog.parent_bundle(run.root_bundle, step_id) for step_id in invalidated_step_ids)
        tasks = () if BundleName.TASKS_BUNDLE in invalidated_bundles else run.tasks
        return (run.replace(status=RunStatus.RUNNING, current_step_id=target_step.step_id, completed_step_ids=completed_prefix, pending_decision=None, tasks=tasks), invalidated)

    def _failed(self, run: RunRecord, issue: EscalationIssue) -> RunRecord:
        phase = run.current_phase.value if run.current_phase is not None else None
        error = ErrorRecord(f"{issue.origin_bundle.value}_ESCALATION_FAILED", issue.reason, step_id=run.current_step_id, bundle=issue.origin_bundle.value, phase=phase, timestamp=self._clock.now_iso())
        return run.replace(status=RunStatus.FAILED, pending_decision=None, errors=(*run.errors, error))
