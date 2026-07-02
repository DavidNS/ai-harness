"""Run aggregate domain objects for v2."""

from __future__ import annotations

from dataclasses import dataclass

from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.decisions import DecisionRecord, PendingDecision
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord, require_text
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName, RunStatus
from harness_v2.backend.domain.tasks import TaskSummary


@dataclass(frozen=True, slots=True, init=False)
class RunRecord:
    run_id: str
    request: str
    status: RunStatus
    root_bundle: BundleName
    current_step_id: str | None
    completed_step_ids: tuple[str, ...]
    pending_decision: PendingDecision | None
    decision_history: tuple[DecisionRecord, ...]
    tasks: tuple[TaskSummary, ...]
    errors: tuple[ErrorRecord, ...]

    def __init__(
        self,
        run_id: str,
        request: str,
        status: RunStatus,
        root_bundle: BundleName = BundleName.SDD_BUNDLE,
        current_phase: PhaseName | str | None = None,
        completed_phases: tuple[PhaseName | str, ...] = (),
        pending_decision: PendingDecision | None = None,
        decision_history: tuple[DecisionRecord, ...] = (),
        tasks: tuple[TaskSummary, ...] = (),
        errors: tuple[ErrorRecord, ...] = (),
        current_step_id: str | None = None,
        completed_step_ids: tuple[str, ...] | None = None,
    ) -> None:
        object.__setattr__(self, "run_id", require_text(run_id, "run ID"))
        object.__setattr__(self, "request", require_text(request, "request"))
        object.__setattr__(self, "status", RunStatus(status))
        object.__setattr__(self, "root_bundle", BundleName(root_bundle))
        inferred_current_step_id = self._current_step_id(current_step_id, current_phase)
        completed = self._completed_step_ids(completed_step_ids, completed_phases)
        if inferred_current_step_id is None and self.status is RunStatus.FAILED:
            inferred_current_step_id = self._infer_failed_step_id(completed)
        object.__setattr__(self, "current_step_id", inferred_current_step_id)
        object.__setattr__(self, "completed_step_ids", completed)
        object.__setattr__(self, "pending_decision", pending_decision)
        object.__setattr__(self, "decision_history", tuple(decision_history))
        object.__setattr__(self, "tasks", tuple(tasks))
        object.__setattr__(self, "errors", tuple(errors))
        self._validate_invariants()

    def replace(self, **changes: object) -> "RunRecord":
        data = {
            "run_id": self.run_id,
            "request": self.request,
            "status": self.status,
            "root_bundle": self.root_bundle,
            "pending_decision": self.pending_decision,
            "decision_history": self.decision_history,
            "tasks": self.tasks,
            "errors": self.errors,
            "current_step_id": self.current_step_id,
            "completed_step_ids": self.completed_step_ids,
        }
        changes.pop("current_bundle", None)
        if "current_phase" in changes:
            current_phase = changes.pop("current_phase")
            changes["current_step_id"] = None if current_phase is None else self._step_id_from_identifier(current_phase)
        if "completed_phases" in changes:
            changes["completed_step_ids"] = self._completed_step_ids(None, changes.pop("completed_phases"))
        data.update(changes)
        return RunRecord(**data)

    @property
    def current_phase(self) -> PhaseName | None:
        if self.current_step_id is None:
            return None
        return bundle_catalog.step_for_step_id(self.root_bundle, self.current_step_id).phase_name

    @property
    def current_bundle(self) -> BundleName | None:
        if self.current_step_id is None:
            return None
        return bundle_catalog.parent_bundle(self.root_bundle, self.current_step_id)

    @property
    def completed_phases(self) -> tuple[PhaseName, ...]:
        return tuple(bundle_catalog.step_for_step_id(self.root_bundle, step_id).phase_name for step_id in self.completed_step_ids)

    def _current_step_id(self, current_step_id: str | None, current_phase: PhaseName | str | None) -> str | None:
        if current_step_id is not None:
            return self._step_id_from_identifier(current_step_id)
        if current_phase is None:
            return None
        return self._step_id_from_identifier(current_phase)

    def _completed_step_ids(self, completed_step_ids: tuple[str, ...] | None, completed_phases: tuple[PhaseName | str, ...]) -> tuple[str, ...]:
        if completed_step_ids is not None:
            return tuple(str(step_id) for step_id in completed_step_ids)
        phases = tuple(PhaseName(phase) for phase in completed_phases)
        steps = bundle_catalog.linearize_bundle(self.root_bundle)
        if len(phases) > len(steps):
            raise DomainValidationError("completed phases must be an ordered prefix of the root bundle")
        for step, phase in zip(steps, phases, strict=False):
            if step.phase_name is not phase:
                raise DomainValidationError("completed phases must be an ordered prefix of the root bundle")
        return tuple(step.step_id for step in steps[: len(phases)])

    def _step_id_from_identifier(self, identifier: str | PhaseName) -> str:
        if isinstance(identifier, PhaseName):
            return bundle_catalog.step_for_phase(self.root_bundle, identifier).step_id
        text = str(identifier)
        if ":" in text:
            return bundle_catalog.step_for_step_id(self.root_bundle, text).step_id
        return bundle_catalog.step_for_phase(self.root_bundle, text).step_id

    def _infer_failed_step_id(self, completed_step_ids: tuple[str, ...]) -> str | None:
        all_steps = bundle_catalog.step_ids(self.root_bundle)
        if len(completed_step_ids) >= len(all_steps):
            return None
        return all_steps[len(completed_step_ids)]

    def _validate_invariants(self) -> None:
        bundle_catalog.validate_completed_prefix(self.root_bundle, self.completed_step_ids)
        all_steps = bundle_catalog.linearize_bundle(self.root_bundle)
        if self.status is RunStatus.PENDING:
            self._require_no_active_step("pending run")
            return
        if self.status is RunStatus.RUNNING:
            self._require_current_step("running run", all_steps)
            return
        if self.status is RunStatus.WAITING_FOR_USER:
            self._require_current_step("waiting run", all_steps)
            if self.pending_decision is None:
                raise DomainValidationError("waiting run requires a pending decision")
            if self.pending_decision.origin_bundle != self.current_bundle:
                raise DomainValidationError("pending decision origin must match current bundle")
            return
        if self.status is RunStatus.COMPLETED:
            self._require_no_active_step("completed run")
            if self.completed_step_ids != tuple(step.step_id for step in all_steps):
                raise DomainValidationError("completed run requires all root bundle steps to be completed")
            return
        if self.status is RunStatus.CANCELLED:
            self._require_no_active_step("cancelled run")
            return
        if self.status is RunStatus.FAILED:
            self._require_failed_step("failed run", all_steps)
            return

    def _require_current_step(self, label: str, all_steps: tuple[object, ...]) -> None:
        if self.current_step_id is None:
            raise DomainValidationError(f"{label} requires a current step")
        if len(self.completed_step_ids) >= len(all_steps):
            raise DomainValidationError(f"{label} cannot continue after all root bundle steps are completed")
        expected = all_steps[len(self.completed_step_ids)]
        if self.current_step_id != expected.step_id:
            raise DomainValidationError(
                f"{label} current step must be next after completed steps: "
                f"expected {expected.step_id}, got {self.current_step_id}"
            )
        if self.pending_decision is not None and self.status is not RunStatus.WAITING_FOR_USER:
            raise DomainValidationError("only waiting runs may have a pending decision")

    def _require_failed_step(self, label: str, all_steps: tuple[object, ...]) -> None:
        if self.current_step_id is None:
            raise DomainValidationError(f"{label} requires a failed step")
        if self.pending_decision is not None:
            raise DomainValidationError(f"{label} must not have a pending decision")
        if len(self.completed_step_ids) >= len(all_steps):
            raise DomainValidationError(f"{label} cannot continue after all root bundle steps are completed")
        expected = all_steps[len(self.completed_step_ids)]
        if self.current_step_id != expected.step_id:
            raise DomainValidationError(
                f"{label} failed step must be next after completed steps: "
                f"expected {expected.step_id}, got {self.current_step_id}"
            )

    def _require_no_active_step(self, label: str) -> None:
        if self.current_step_id is not None:
            raise DomainValidationError(f"{label} must not have a current step")
        if self.pending_decision is not None:
            raise DomainValidationError(f"{label} must not have a pending decision")
