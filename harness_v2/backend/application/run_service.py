"""Application services for v2 run commands and queries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from harness_v2.backend.application.contracts import (
    CancelRun,
    Command,
    CommandResult,
    ErrorView,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetRun,
    InvalidRunStateError,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    ListRuns,
    ListRunsResult,
    PendingDecisionView,
    PhaseCompleted,
    PhaseStarted,
    Query,
    QueryResult,
    ResumeRun,
    RunCancelled,
    RunNotFoundError,
    RunCompleted,
    RunResumed,
    RunStarted,
    RunSummaryView,
    RunView,
    StartRun,
    SubmitUserDecision,
    TaskSummaryView,
    UserDecisionReceived,
    UserDecisionRequested,
)
from harness_v2.backend.domain.decisions import PendingDecision
from harness_v2.backend.domain.lifecycle import LifecycleGraph, PhaseName, RunStatus, RunStrategy
from harness_v2.backend.domain.runs import RunRecord
from harness_v2.backend.ports.state_store import StateNotFoundError, StateStorePort

INITIAL_PHASE = PhaseName.EXPLORE_BUNDLE


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        object.__setattr__(self, "options", _text_tuple(self.options, "options"))


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _pending_decision_view(run: RunRecord) -> PendingDecisionView | None:
    decision = run.pending_decision
    if decision is None:
        return None
    return PendingDecisionView(
        decision_id=decision.decision_id,
        origin_phase=decision.origin_phase.value,
        prompt=decision.prompt,
        created_at=decision.created_at,
        options=decision.options,
    )


def _task_view(task: object) -> TaskSummaryView:
    return TaskSummaryView(
        task_id=task.task_id,
        title=task.title,
        status=task.status.value,
    )


def _error_view(error: object) -> ErrorView:
    return ErrorView(
        code=error.code,
        message=error.message,
        phase=error.phase,
        timestamp=error.timestamp,
    )


def run_to_view(run: RunRecord) -> RunView:
    """Project the domain aggregate into a serialization-stable boundary DTO."""

    return RunView(
        run_id=run.run_id,
        request=run.request,
        status=run.status.value,
        strategy=run.strategy.value,
        current_phase=run.current_phase.value if run.current_phase else None,
        completed_phases=tuple(phase.value for phase in run.completed_phases),
        pending_decision=_pending_decision_view(run),
        tasks=tuple(_task_view(task) for task in run.tasks),
        errors=tuple(_error_view(error) for error in run.errors),
    )


def run_to_summary(run: RunRecord) -> RunSummaryView:
    return RunSummaryView(
        run_id=run.run_id,
        request=run.request,
        status=run.status.value,
        current_phase=run.current_phase.value if run.current_phase else None,
    )


def available_actions(run: RunRecord) -> tuple[str, ...]:
    if run.status in {RunStatus.PENDING, RunStatus.RUNNING}:
        return ("resume", "cancel")
    if run.status == RunStatus.WAITING_FOR_USER:
        return ("submit-user-decision", "cancel")
    return ()


class _RunStateAccess:
    def __init__(self, state_store: StateStorePort) -> None:
        self._state_store = state_store

    def _get(self, run_id: str) -> RunRecord:
        try:
            return self._state_store.get(run_id)
        except StateNotFoundError as exc:
            raise RunNotFoundError(run_id) from exc


class StartRunService(_RunStateAccess):
    def __init__(self, state_store: StateStorePort, id_factory: Callable[[], str] | None = None) -> None:
        super().__init__(state_store)
        self._id_factory = id_factory or (lambda: uuid4().hex)

    def execute(self, command: StartRun) -> CommandResult:
        run_id = self._id_factory()
        events = (
            RunStarted(run_id=run_id, request=command.request),
            PhaseStarted(run_id=run_id, phase=INITIAL_PHASE.value),
            PhaseCompleted(run_id=run_id, phase=INITIAL_PHASE.value),
            RunCompleted(run_id=run_id),
        )
        run = RunRecord(
            run_id=run_id,
            request=command.request,
            status=RunStatus.COMPLETED,
            strategy=RunStrategy.EXPLORE_BUNDLE,
            current_phase=None,
            completed_phases=(INITIAL_PHASE,),
        )
        self._state_store.save(run)
        return CommandResult(run=run_to_view(run), events=events)


class ResumeRunService(_RunStateAccess):
    def execute(self, command: ResumeRun) -> CommandResult:
        run = self._get(command.run_id)
        if run.status == RunStatus.PENDING:
            start_phase = LifecycleGraph.for_strategy(run.strategy).start_phase
            resumed = RunResumed(run_id=run.run_id)
            started = PhaseStarted(run_id=run.run_id, phase=start_phase.value)
            updated = run.replace(
                status=RunStatus.RUNNING,
                current_phase=start_phase,
            )
            self._state_store.save(updated)
            return CommandResult(run=run_to_view(updated), events=(resumed, started))
        if run.status == RunStatus.RUNNING:
            event = RunResumed(run_id=run.run_id)
            return CommandResult(run=run_to_view(run), events=(event,))
        if run.status == RunStatus.WAITING_FOR_USER:
            raise InvalidRunStateError(f"run {run.run_id} requires a user decision before it can resume")
        raise InvalidRunStateError(f"run {run.run_id} cannot be resumed from {run.status.value}")


class RequestUserDecisionService(_RunStateAccess):
    def __init__(self, state_store: StateStorePort, timestamp_factory: Callable[[], str] | None = None) -> None:
        super().__init__(state_store)
        self._timestamp_factory = timestamp_factory or _utc_timestamp

    def execute(self, command: DecisionRequest) -> CommandResult:
        run = self._get(command.run_id)
        if run.status != RunStatus.RUNNING or run.current_phase is None:
            raise InvalidRunStateError(f"run {run.run_id} cannot request a decision from {run.status.value}")
        decision = PendingDecision(
            decision_id=command.decision_id,
            origin_phase=run.current_phase,
            prompt=command.prompt,
            created_at=self._timestamp_factory(),
            options=command.options,
        )
        event = UserDecisionRequested(
            run_id=run.run_id,
            decision_id=decision.decision_id,
            prompt=decision.prompt,
            options=decision.options,
        )
        updated = run.replace(
            status=RunStatus.WAITING_FOR_USER,
            pending_decision=decision,
        )
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(event,))


class CancelRunService(_RunStateAccess):
    def execute(self, command: CancelRun) -> CommandResult:
        run = self._get(command.run_id)
        if run.status not in {RunStatus.PENDING, RunStatus.RUNNING, RunStatus.WAITING_FOR_USER}:
            raise InvalidRunStateError(f"run {run.run_id} cannot be cancelled from {run.status.value}")
        event = RunCancelled(run_id=command.run_id)
        updated = run.replace(
            status=RunStatus.CANCELLED,
            current_phase=None,
            pending_decision=None,
        )
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(event,))


class SubmitUserDecisionService(_RunStateAccess):
    def execute(self, command: SubmitUserDecision) -> CommandResult:
        run = self._get(command.run_id)
        if run.status != RunStatus.WAITING_FOR_USER or run.pending_decision is None:
            raise InvalidRunStateError(f"run {run.run_id} has no pending decision")
        decision = run.pending_decision
        if command.decision_id != decision.decision_id:
            raise InvalidRunStateError(f"run {run.run_id} is waiting for decision {decision.decision_id}")
        if decision.options and command.response not in decision.options:
            allowed = ", ".join(decision.options)
            raise InvalidRunStateError(f"decision response must be one of: {allowed}")

        event = UserDecisionReceived(
            run_id=command.run_id,
            decision_id=command.decision_id,
            response=command.response,
        )
        updated = run.replace(
            status=RunStatus.RUNNING,
            pending_decision=None,
        )
        self._state_store.save(updated)
        return CommandResult(run=run_to_view(updated), events=(event,))


class GetRunService(_RunStateAccess):
    def query(self, query: GetRun) -> GetRunResult:
        return GetRunResult(run=run_to_view(self._get(query.run_id)))


class ListRunsService(_RunStateAccess):
    def query(self, query: ListRuns) -> ListRunsResult:
        return ListRunsResult(runs=tuple(run_to_summary(run) for run in self._state_store.list_all()))


class GetRunStateService(_RunStateAccess):
    def query(self, query: GetRunState) -> GetRunStateResult:
        run = self._get(query.run_id)
        return GetRunStateResult(
            run_id=run.run_id,
            status=run.status.value,
            current_phase=run.current_phase.value if run.current_phase else None,
            pending_decision=_pending_decision_view(run),
        )


class GetAvailableActionsService(_RunStateAccess):
    def query(self, query: GetAvailableActions) -> GetAvailableActionsResult:
        run = self._get(query.run_id)
        return GetAvailableActionsResult(run_id=run.run_id, actions=available_actions(run))


class RunService:
    """Facade over explicit application services with persistence behind ports."""

    def __init__(
        self,
        state_store: StateStorePort,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._state_store = state_store
        self._start = StartRunService(state_store, id_factory=id_factory)
        self._resume = ResumeRunService(state_store)
        self._cancel = CancelRunService(state_store)
        self._submit_decision = SubmitUserDecisionService(state_store)
        self._get = GetRunService(state_store)
        self._list = ListRunsService(state_store)
        self._get_state = GetRunStateService(state_store)
        self._get_actions = GetAvailableActionsService(state_store)

    def execute(self, command: Command) -> CommandResult:
        if isinstance(command, StartRun):
            return self._start.execute(command)
        if isinstance(command, ResumeRun):
            return self._resume.execute(command)
        if isinstance(command, CancelRun):
            return self._cancel.execute(command)
        if isinstance(command, SubmitUserDecision):
            return self._submit_decision.execute(command)
        raise TypeError(f"unsupported command: {type(command).__name__}")

    def query(self, query: Query) -> QueryResult:
        if isinstance(query, GetRun):
            return self._get.query(query)
        if isinstance(query, ListRuns):
            return self._list.query(query)
        if isinstance(query, GetRunState):
            return self._get_state.query(query)
        if isinstance(query, GetAvailableActions):
            return self._get_actions.query(query)
        raise TypeError(f"unsupported query: {type(query).__name__}")
