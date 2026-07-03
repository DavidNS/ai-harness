"""Application service for backend-owned user decision requests."""

from __future__ import annotations

from dataclasses import dataclass

from harness_v2.backend.application.contracts import (
    CommandResult,
    InvalidRunStateError,
    PendingDecisionView,
    RunNotFoundError,
    RunView,
    StepView,
    TaskSummaryView,
    ErrorView,
    UserDecisionRequested,
)
from harness_v2.backend.domain.decisions import DecisionAction, DecisionEffect, PendingDecision
from harness_v2.backend.domain.escalation import EscalationCategory
from harness_v2.backend.domain import bundle_catalog
from harness_v2.backend.domain.lifecycle import RunStatus
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.clock import ClockPort
from harness_v2.backend.ports.state_store import StateNotFoundError, StateStorePort


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _text_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    run_id: str
    decision_id: str
    prompt: str
    options: tuple[str, ...] = ()
    effects: tuple[DecisionEffect, ...] = ()
    default_action: DecisionAction = DecisionAction.CONTINUE
    default_category: EscalationCategory | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        object.__setattr__(self, "options", _text_tuple(self.options, "options"))
        default_action = DecisionAction(self.default_action)
        object.__setattr__(
            self,
            "effects",
            tuple(DecisionEffect(effect.option, effect.action, effect.category) for effect in self.effects),
        )
        default_category = None if self.default_category is None else EscalationCategory(self.default_category)
        object.__setattr__(self, "default_action", default_action)
        object.__setattr__(self, "default_category", default_category)


class RequestUserDecisionService:
    def __init__(self, state_store: StateStorePort, clock: ClockPort) -> None:
        self._state_store = state_store
        self._clock = clock

    def execute(self, command: DecisionRequest) -> CommandResult:
        try:
            run = self._state_store.get(command.run_id)
        except StateNotFoundError as exc:
            raise RunNotFoundError(command.run_id) from exc
        if run.status != RunStatus.RUNNING or run.current_phase is None:
            raise InvalidRunStateError(f"run {run.run_id} cannot request a decision from {run.status.value}")
        decision = PendingDecision(
            decision_id=command.decision_id,
            origin_bundle=run.current_bundle,
            prompt=command.prompt,
            created_at=self._clock.now_iso(),
            options=command.options,
            effects=command.effects,
            default_action=command.default_action,
            default_category=command.default_category,
        )
        event = UserDecisionRequested(
            run_id=run.run_id,
            decision_id=decision.decision_id,
            origin_bundle=decision.origin_bundle.value,
            prompt=decision.prompt,
            options=decision.options,
        )
        updated = run.replace(status=RunStatus.WAITING_FOR_USER, pending_decision=decision)
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(event,))


def pending_decision_view(run: RunRecord) -> PendingDecisionView | None:
    decision = run.pending_decision
    if decision is None:
        return None
    return PendingDecisionView(
        decision_id=decision.decision_id,
        origin_bundle=decision.origin_bundle.value,
        prompt=decision.prompt,
        created_at=decision.created_at,
        options=decision.options,
    )


def task_view(task: object) -> TaskSummaryView:
    return TaskSummaryView(task_id=task.task_id, title=task.title, status=task.status.value, attempts=task.attempts, last_failure=task.last_failure)


def step_view(run: RunRecord, step_id: str | None) -> StepView | None:
    if step_id is None:
        return None
    step = bundle_catalog.step_for_step_id(run.root_bundle, step_id)
    return StepView(
        step_id=step.step_id,
        bundle=step.bundle_name.value,
        phase=step.phase_name.value,
        step_index=step.step_index,
    )


def error_view(error: object) -> ErrorView:
    return ErrorView(code=error.code, message=error.message, step_id=error.step_id, bundle=error.bundle, phase=error.phase, timestamp=error.timestamp)


def run_to_view(run: RunRecord) -> RunView:
    return RunView(
        run_id=run.run_id,
        request=run.request,
        status=run.status.value,
        root_bundle=run.root_bundle.value,
        current_step=step_view(run, run.current_step_id),
        completed_steps=tuple(view for step_id in run.completed_step_ids if (view := step_view(run, step_id)) is not None),
        completed_bundles=tuple(bundle.value for bundle in bundle_catalog.completed_bundles(run.root_bundle, run.completed_step_ids)),
        pending_decision=pending_decision_view(run),
        tasks=tuple(task_view(task) for task in run.tasks),
        errors=tuple(error_view(error) for error in run.errors),
    )
