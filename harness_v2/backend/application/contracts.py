"""Command, query, event, and result DTOs for the v2 backend boundary."""

from __future__ import annotations

from dataclasses import dataclass

from harness_v2.backend.domain.lifecycle import PhaseName, RunStatus, RunStrategy


class RunNotFoundError(KeyError):
    """Raised when a command or query targets an unknown run."""


class InvalidRunStateError(RuntimeError):
    """Raised when a command is not valid for the run's current state."""


PHASE_VALUES = frozenset(phase.value for phase in PhaseName)
RUN_STATUS_VALUES = frozenset(status.value for status in RunStatus)
RUN_STRATEGY_VALUES = frozenset(strategy.value for strategy in RunStrategy)


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _text_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def _phase_text(value: str, field: str = "phase") -> str:
    normalized = _require_text(value, field)
    if normalized not in PHASE_VALUES:
        raise ValueError(f"{field} is not a known phase")
    return normalized


def _status_text(value: str, field: str = "status") -> str:
    normalized = _require_text(value, field)
    if normalized not in RUN_STATUS_VALUES:
        raise ValueError(f"{field} is not a known run status")
    return normalized


def _strategy_text(value: str, field: str = "strategy") -> str:
    normalized = _require_text(value, field)
    if normalized not in RUN_STRATEGY_VALUES:
        raise ValueError(f"{field} is not a known run strategy")
    return normalized


def _type_name(expected_type: object) -> str:
    return getattr(expected_type, "__name__", str(expected_type))


def _require_instance(value: object, expected_type: object, field: str) -> object:
    if not isinstance(value, expected_type):
        raise TypeError(f"{field} must be {_type_name(expected_type)}")
    return value


def _typed_tuple(values: tuple[object, ...] | list[object], expected_type: object, field: str) -> tuple[object, ...]:
    normalized = tuple(values)
    for value in normalized:
        _require_instance(value, expected_type, field)
    return normalized


@dataclass(frozen=True, slots=True)
class StartRun:
    request: str
    strategy: str = "SDD"

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "strategy", _strategy_text(self.strategy))


@dataclass(frozen=True, slots=True)
class ResumeRun:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class RetryPhase:
    run_id: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", _phase_text(self.phase))


@dataclass(frozen=True, slots=True)
class CancelRun:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class SubmitUserDecision:
    run_id: str
    decision_id: str
    response: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "response", _require_text(self.response, "response"))


@dataclass(frozen=True, slots=True)
class GetRun:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class ListRuns:
    pass


@dataclass(frozen=True, slots=True)
class GetRunState:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class GetAvailableActions:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class RunStarted:
    run_id: str
    request: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "request", _require_text(self.request, "request"))


@dataclass(frozen=True, slots=True)
class PhaseStarted:
    run_id: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", _phase_text(self.phase))


@dataclass(frozen=True, slots=True)
class PhaseCompleted:
    run_id: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", _phase_text(self.phase))


@dataclass(frozen=True, slots=True)
class PhaseFailed:
    run_id: str
    phase: str
    error: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", _phase_text(self.phase))
        object.__setattr__(self, "error", _require_text(self.error, "error"))


@dataclass(frozen=True, slots=True)
class PhaseEscalated:
    run_id: str
    from_phase: str
    target_phase: str
    decision_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "from_phase", _phase_text(self.from_phase, "from_phase"))
        object.__setattr__(self, "target_phase", _phase_text(self.target_phase, "target_phase"))
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))


@dataclass(frozen=True, slots=True)
class PhaseRecoveryStarted:
    run_id: str
    from_phase: str
    target_phase: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "from_phase", _phase_text(self.from_phase, "from_phase"))
        object.__setattr__(self, "target_phase", _phase_text(self.target_phase, "target_phase"))
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class PhaseRetryStarted:
    run_id: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", _phase_text(self.phase))


@dataclass(frozen=True, slots=True)
class UserDecisionRequested:
    run_id: str
    decision_id: str
    prompt: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        object.__setattr__(self, "options", _text_tuple(self.options, "options"))


@dataclass(frozen=True, slots=True)
class UserDecisionReceived:
    run_id: str
    decision_id: str
    response: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "response", _require_text(self.response, "response"))


@dataclass(frozen=True, slots=True)
class RunResumed:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class RunCompleted:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class RunCancelled:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


Command = StartRun | ResumeRun | RetryPhase | CancelRun | SubmitUserDecision
Query = GetRun | ListRuns | GetRunState | GetAvailableActions
Event = (
    RunStarted
    | PhaseStarted
    | PhaseCompleted
    | PhaseFailed
    | PhaseEscalated
    | PhaseRecoveryStarted
    | PhaseRetryStarted
    | UserDecisionRequested
    | UserDecisionReceived
    | RunResumed
    | RunCompleted
    | RunCancelled
)


@dataclass(frozen=True, slots=True)
class PendingDecisionView:
    decision_id: str
    origin_phase: str
    prompt: str
    created_at: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "origin_phase", _phase_text(self.origin_phase, "origin_phase"))
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        object.__setattr__(self, "created_at", _require_text(self.created_at, "created_at"))
        object.__setattr__(self, "options", _text_tuple(self.options, "options"))


@dataclass(frozen=True, slots=True)
class TaskSummaryView:
    task_id: str
    title: str
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _require_text(self.task_id, "task_id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "status", _require_text(self.status, "status"))


@dataclass(frozen=True, slots=True)
class ErrorView:
    code: str
    message: str
    phase: str | None = None
    timestamp: str = "unknown"

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_text(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        object.__setattr__(self, "phase", None if self.phase is None else _phase_text(self.phase))
        object.__setattr__(self, "timestamp", _require_text(self.timestamp, "timestamp"))


@dataclass(frozen=True, slots=True)
class RunView:
    run_id: str
    request: str
    status: str
    strategy: str
    current_phase: str | None = None
    completed_phases: tuple[str, ...] = ()
    pending_decision: PendingDecisionView | None = None
    tasks: tuple[TaskSummaryView, ...] = ()
    errors: tuple[ErrorView, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "status", _status_text(self.status))
        object.__setattr__(self, "strategy", _strategy_text(self.strategy))
        object.__setattr__(
            self,
            "current_phase",
            None if self.current_phase is None else _phase_text(self.current_phase, "current_phase"),
        )
        object.__setattr__(
            self,
            "completed_phases",
            tuple(_phase_text(phase, "completed_phases") for phase in self.completed_phases),
        )
        if self.pending_decision is not None:
            _require_instance(self.pending_decision, PendingDecisionView, "pending_decision")
        object.__setattr__(self, "tasks", _typed_tuple(self.tasks, TaskSummaryView, "tasks"))
        object.__setattr__(self, "errors", _typed_tuple(self.errors, ErrorView, "errors"))


@dataclass(frozen=True, slots=True)
class RunSummaryView:
    run_id: str
    request: str
    status: str
    current_phase: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "status", _status_text(self.status))
        object.__setattr__(
            self,
            "current_phase",
            None if self.current_phase is None else _phase_text(self.current_phase, "current_phase"),
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    run: RunView
    events: tuple[Event, ...]

    def __post_init__(self) -> None:
        _require_instance(self.run, RunView, "run")
        object.__setattr__(self, "events", _typed_tuple(self.events, Event, "events"))


@dataclass(frozen=True, slots=True)
class GetRunResult:
    run: RunView

    def __post_init__(self) -> None:
        _require_instance(self.run, RunView, "run")


@dataclass(frozen=True, slots=True)
class ListRunsResult:
    runs: tuple[RunSummaryView, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "runs", _typed_tuple(self.runs, RunSummaryView, "runs"))


@dataclass(frozen=True, slots=True)
class GetRunStateResult:
    run_id: str
    status: str
    current_phase: str | None = None
    pending_decision: PendingDecisionView | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "status", _status_text(self.status))
        object.__setattr__(
            self,
            "current_phase",
            None if self.current_phase is None else _phase_text(self.current_phase, "current_phase"),
        )
        if self.pending_decision is not None:
            _require_instance(self.pending_decision, PendingDecisionView, "pending_decision")


@dataclass(frozen=True, slots=True)
class GetAvailableActionsResult:
    run_id: str
    actions: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "actions", _text_tuple(self.actions, "actions"))


QueryResult = GetRunResult | ListRunsResult | GetRunStateResult | GetAvailableActionsResult
