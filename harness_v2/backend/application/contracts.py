"""Command, query, and event DTOs for the v2 backend boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
class StartRun:
    request: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", _require_text(self.request, "request"))


@dataclass(frozen=True, slots=True)
class ResumeRun:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


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
        object.__setattr__(self, "phase", _require_text(self.phase, "phase"))


@dataclass(frozen=True, slots=True)
class PhaseCompleted:
    run_id: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", _require_text(self.phase, "phase"))


@dataclass(frozen=True, slots=True)
class PhaseFailed:
    run_id: str
    phase: str
    error: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "phase", _require_text(self.phase, "phase"))
        object.__setattr__(self, "error", _require_text(self.error, "error"))


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
class RunCompleted:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class RunCancelled:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


Command = StartRun | ResumeRun | CancelRun | SubmitUserDecision
Query = GetRun | ListRuns | GetRunState | GetAvailableActions
Event = (
    RunStarted
    | PhaseStarted
    | PhaseCompleted
    | PhaseFailed
    | UserDecisionRequested
    | UserDecisionReceived
    | RunCompleted
    | RunCancelled
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    run: Any
    events: tuple[Event, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))

