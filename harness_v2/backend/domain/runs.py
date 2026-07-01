"""Run aggregate domain objects for v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.errors import DomainValidationError, ErrorRecord, require_text
from harness_v2.backend.domain.lifecycle import LifecycleGraph, PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.tasks import TaskSummary


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    request: str
    status: RunStatus
    strategy: RunStrategy = RunStrategy.SDD
    current_phase: PhaseName | None = None
    completed_phases: tuple[PhaseName, ...] = ()
    pending_decision: PendingDecision | None = None
    tasks: tuple[TaskSummary, ...] = ()
    errors: tuple[ErrorRecord, ...] = ()
    events: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", require_text(self.run_id, "run ID"))
        object.__setattr__(self, "request", require_text(self.request, "request"))
        object.__setattr__(self, "status", RunStatus(self.status))
        object.__setattr__(self, "strategy", RunStrategy(self.strategy))
        object.__setattr__(self, "current_phase", self._phase_or_none(self.current_phase, "current phase"))
        object.__setattr__(
            self,
            "completed_phases",
            tuple(PhaseName(phase) for phase in self.completed_phases),
        )
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "events", tuple(self.events))
        self._validate_invariants()

    def with_events(self, events: tuple[Any, ...]) -> "RunRecord":
        return self.replace(events=events)

    def replace(self, **changes: object) -> "RunRecord":
        data = {
            "run_id": self.run_id,
            "request": self.request,
            "status": self.status,
            "strategy": self.strategy,
            "current_phase": self.current_phase,
            "completed_phases": self.completed_phases,
            "pending_decision": self.pending_decision,
            "tasks": self.tasks,
            "errors": self.errors,
            "events": self.events,
        }
        data.update(changes)
        return RunRecord(**data)

    @staticmethod
    def _phase_or_none(phase: PhaseName | str | None, field: str) -> PhaseName | None:
        if phase is None:
            return None
        try:
            return PhaseName(phase)
        except ValueError as exc:
            raise DomainValidationError(f"unknown {field}: {phase}") from exc

    def _validate_invariants(self) -> None:
        graph = LifecycleGraph.for_strategy(self.strategy)
        graph.validate_completed_prefix(self.completed_phases)
        if self.status is RunStatus.PENDING:
            self._require_no_active_phase("pending run")
            return
        if self.status is RunStatus.RUNNING:
            self._require_current_phase("running run", graph)
            return
        if self.status is RunStatus.WAITING_FOR_USER:
            self._require_current_phase("waiting run", graph)
            if self.pending_decision is None:
                raise DomainValidationError("waiting run requires a pending decision")
            if self.pending_decision.origin_phase != self.current_phase:
                raise DomainValidationError("pending decision origin must match current phase")
            return
        self._require_no_active_phase(f"{self.status.value.lower()} run")
        if self.status is RunStatus.COMPLETED and self.completed_phases != graph.phases:
            raise DomainValidationError("completed run requires all strategy phases to be completed")

    def _require_current_phase(self, label: str, graph: LifecycleGraph) -> None:
        if self.current_phase is None:
            raise DomainValidationError(f"{label} requires a current phase")
        if len(self.completed_phases) >= len(graph.phases):
            raise DomainValidationError(f"{label} cannot continue after all strategy phases are completed")
        expected = graph.phases[len(self.completed_phases)]
        if self.current_phase != expected:
            raise DomainValidationError(
                f"{label} current phase must be next after completed phases: "
                f"expected {expected.value}, got {self.current_phase.value}"
            )
        if self.pending_decision is not None and self.status is not RunStatus.WAITING_FOR_USER:
            raise DomainValidationError("only waiting runs may have a pending decision")

    def _require_no_active_phase(self, label: str) -> None:
        if self.current_phase is not None:
            raise DomainValidationError(f"{label} must not have a current phase")
        if self.pending_decision is not None:
            raise DomainValidationError(f"{label} must not have a pending decision")
