"""In-memory application service for the v2 walking skeleton."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from harness_v2.backend.application.contracts import (
    CancelRun,
    Command,
    CommandResult,
    GetAvailableActions,
    GetRun,
    GetRunState,
    ListRuns,
    PhaseCompleted,
    PhaseStarted,
    Query,
    ResumeRun,
    RunCancelled,
    RunCompleted,
    RunStarted,
    StartRun,
    SubmitUserDecision,
)
from harness_v2.backend.domain.runs import RunRecord, RunStatus

SIMULATED_PHASE = "SIMULATED"


class RunNotFoundError(KeyError):
    """Raised when a command or query targets an unknown run."""


class InvalidRunStateError(RuntimeError):
    """Raised when a command is not valid for the run's current state."""


class InMemoryRunService:
    """Minimal authoritative backend service with no external side effects."""

    def __init__(self, id_factory: Callable[[], str] | None = None) -> None:
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._runs: dict[str, RunRecord] = {}

    def execute(self, command: Command) -> CommandResult:
        if isinstance(command, StartRun):
            return self._start(command)
        if isinstance(command, ResumeRun):
            return CommandResult(run=self._get(command.run_id), events=())
        if isinstance(command, CancelRun):
            return self._cancel(command)
        if isinstance(command, SubmitUserDecision):
            return self._submit_decision(command)
        raise TypeError(f"unsupported command: {type(command).__name__}")

    def query(self, query: Query) -> object:
        if isinstance(query, GetRun):
            return self._get(query.run_id)
        if isinstance(query, ListRuns):
            return tuple(self._runs.values())
        if isinstance(query, GetRunState):
            return self._get(query.run_id).status
        if isinstance(query, GetAvailableActions):
            return self._available_actions(self._get(query.run_id))
        raise TypeError(f"unsupported query: {type(query).__name__}")

    def _start(self, command: StartRun) -> CommandResult:
        run_id = self._id_factory()
        events = (
            RunStarted(run_id=run_id, request=command.request),
            PhaseStarted(run_id=run_id, phase=SIMULATED_PHASE),
            PhaseCompleted(run_id=run_id, phase=SIMULATED_PHASE),
            RunCompleted(run_id=run_id),
        )
        run = RunRecord(
            run_id=run_id,
            request=command.request,
            status=RunStatus.COMPLETED,
            current_phase=None,
            completed_phases=(SIMULATED_PHASE,),
            events=events,
        )
        self._runs[run_id] = run
        return CommandResult(run=run, events=events)

    def _cancel(self, command: CancelRun) -> CommandResult:
        run = self._get(command.run_id)
        if run.status not in {RunStatus.PENDING, RunStatus.RUNNING}:
            raise InvalidRunStateError(f"run {run.run_id} cannot be cancelled from {run.status.value}")
        event = RunCancelled(run_id=command.run_id)
        updated = RunRecord(
            run_id=run.run_id,
            request=run.request,
            status=RunStatus.CANCELLED,
            current_phase=run.current_phase,
            completed_phases=run.completed_phases,
            events=(*run.events, event),
        )
        self._runs[command.run_id] = updated
        return CommandResult(run=updated, events=(event,))

    def _submit_decision(self, command: SubmitUserDecision) -> CommandResult:
        run = self._get(command.run_id)
        raise InvalidRunStateError(f"run {run.run_id} has no pending decision")

    def _get(self, run_id: str) -> RunRecord:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc

    def _available_actions(self, run: RunRecord) -> tuple[str, ...]:
        if run.status == RunStatus.COMPLETED:
            return ()
        if run.status == RunStatus.CANCELLED:
            return ()
        return ("resume", "cancel")

