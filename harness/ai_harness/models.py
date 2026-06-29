"""Typed data contracts with explicit runtime validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Sequence

from .errors import ValidationError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Mode(StrEnum):
    CODE = "code"
    NON_CODE = "non_code"


class Strategy(StrEnum):
    SDD = "SDD"
    EXPLORER = "EXPLORER"
    NON_CODE_STUB = "NON_CODE_STUB"


class Complexity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewVerdict(StrEnum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class RunStatus(StrEnum):
    ACTIVE = "active"
    WAITING_FOR_USER = "waiting_for_user"
    FAILED = "failed"
    COMPLETED = "completed"
    IMPOSSIBLE = "impossible"


@dataclass(frozen=True, slots=True)
class Route:
    mode: Mode
    intent: str
    confidence: float

    def __post_init__(self) -> None:
        allowed = {Mode.CODE: {"build_software", "modify_code", "debug_issue", "explorer_request"}, Mode.NON_CODE: {"ideation", "market_analysis", "research", "unknown"}}
        if self.intent not in allowed[self.mode]:
            raise ValidationError("intent is inconsistent with mode")
        if isinstance(self.confidence, bool) or not 0 <= self.confidence <= 1:
            raise ValidationError("confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    strategy: Strategy
    complexity: Complexity
    score: int
    reason: str
    matched_signals: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.score < 0 or not self.reason.strip():
            raise ValidationError("strategy score and reason are required")
        if self.strategy in {Strategy.NON_CODE_STUB, Strategy.EXPLORER}:
            return
        if self.strategy is not Strategy.SDD:
            raise ValidationError("strategy is inconsistent with complexity")


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    title: str
    depends_on: tuple[str, ...] = ()
    status: TaskStatus = TaskStatus.PENDING
    acceptance_criteria: tuple[str, ...] = ()
    test_commands: tuple[str, ...] = ()
    attempts: int = 0

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip():
            raise ValidationError("task ID and title are required")
        if len(set(self.depends_on)) != len(self.depends_on) or self.id in self.depends_on:
            raise ValidationError("task dependencies must be unique and cannot be self-referential")
        if self.attempts < 0:
            raise ValidationError("task attempts cannot be negative")


@dataclass(frozen=True, slots=True)
class Review:
    verdict: ReviewVerdict
    findings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    code: str
    message: str
    phase: str | None = None
    timestamp: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ToolEvidence:
    tool: str
    arguments: Mapping[str, Any]
    result: Mapping[str, Any]
    postcondition_met: bool

    def __post_init__(self) -> None:
        if not self.tool.strip():
            raise ValidationError("tool name is required")


@dataclass(frozen=True, slots=True)
class ActionRequest:
    tool: str
    arguments: Mapping[str, Any]
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.tool.strip() or not self.idempotency_key.strip():
            raise ValidationError("action tool and idempotency key are required")


@dataclass(frozen=True, slots=True)
class PendingDecision:
    id: str
    origin_phase: str
    target_phase: str
    request_artifact: str
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.origin_phase.strip() or not self.target_phase.strip():
            raise ValidationError("pending decision ID, origin phase, and target phase are required")
        expected = f"decisions/{self.id}/request.json"
        if self.request_artifact != expected:
            raise ValidationError("pending decision request artifact path is inconsistent")


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    id: str
    run_id: str
    summary: str
    decisions: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    solutions: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.run_id.strip() or not self.summary.strip():
            raise ValidationError("knowledge ID, run ID, and summary are required")


@dataclass(slots=True)
class RunState:
    run_id: str
    user_input: str
    current_phase: str
    strategy: Strategy
    mode: Mode
    intent: str
    complexity: Complexity
    selected_provider: str
    selected_provider_command: tuple[str, ...] = ()
    selected_model: str = ""
    completed_phases: list[str] = field(default_factory=list)
    failed_phases: list[str] = field(default_factory=list)
    artifacts: dict[str, dict[str, str]] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)
    errors: list[ErrorRecord] = field(default_factory=list)
    status: RunStatus = RunStatus.ACTIVE
    pending_decision: PendingDecision | None = None
    started_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    schema_version: int = 1
    harness_version: str = "0.1.0"

    def validate(self) -> None:
        if not self.run_id.strip() or not self.user_input.strip():
            raise ValidationError("run ID and user input are required")
        if any(not isinstance(part, str) or not part.strip() for part in self.selected_provider_command):
            raise ValidationError("selected provider command must contain nonempty strings")
        if not isinstance(self.selected_model, str):
            raise ValidationError("selected model must be a string")
        if len(self.completed_phases) != len(set(self.completed_phases)):
            raise ValidationError("completed phases must be unique")
        if set(self.completed_phases) & set(self.failed_phases):
            raise ValidationError("a phase cannot be both completed and failed")
        if self.status is RunStatus.WAITING_FOR_USER:
            if self.pending_decision is None:
                raise ValidationError("waiting runs require one pending decision")
            if self.current_phase != self.pending_decision.target_phase:
                raise ValidationError("waiting current phase must match the pending decision target")
        elif self.pending_decision is not None:
            raise ValidationError("only waiting runs may carry a pending decision")
        if self.status is RunStatus.COMPLETED and self.current_phase != "COMPLETED":
            raise ValidationError("completed runs must be at COMPLETED")
        if self.status is RunStatus.FAILED and self.current_phase != "FAILED":
            raise ValidationError("failed runs must be at FAILED")
        if self.status is RunStatus.IMPOSSIBLE and self.current_phase != "IMPOSSIBLE":
            raise ValidationError("impossible runs must be at IMPOSSIBLE")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "harness_version": self.harness_version,
            "run_id": self.run_id, "user_input": self.user_input, "mode": self.mode.value,
            "intent": self.intent, "strategy": self.strategy.value, "complexity": self.complexity.value,
            "current_phase": self.current_phase, "completed_phases": self.completed_phases,
            "failed_phases": self.failed_phases, "artifacts": self.artifacts,
            "tasks": [task_to_dict(t) for t in self.tasks], "selected_provider": self.selected_provider,
            "selected_provider_command": list(self.selected_provider_command), "selected_model": self.selected_model,
            "status": self.status.value, "errors": [vars_like(e) for e in self.errors],
            "pending_decision": None if self.pending_decision is None else vars_like(self.pending_decision),
            "timestamps": {"started_at": self.started_at, "updated_at": self.updated_at, "finished_at": self.finished_at},
        }


def vars_like(value: Any) -> dict[str, Any]:
    return {name: getattr(value, name) for name in value.__dataclass_fields__}


def task_to_dict(task: Task) -> dict[str, Any]:
    return {"id": task.id, "title": task.title, "depends_on": list(task.depends_on), "status": task.status.value,
            "acceptance_criteria": list(task.acceptance_criteria), "test_commands": list(task.test_commands), "attempts": task.attempts}


def task_from_dict(value: Mapping[str, Any]) -> Task:
    required = {"id", "title"}
    if not required <= value.keys():
        raise ValidationError("task is missing required fields")
    return Task(str(value["id"]), str(value["title"]), tuple(value.get("depends_on", ())),
                TaskStatus(value.get("status", "pending")), tuple(value.get("acceptance_criteria", ())),
                tuple(value.get("test_commands", ())), int(value.get("attempts", 0)))


def run_state_from_dict(value: Mapping[str, Any]) -> RunState:
    timestamps = value["timestamps"]
    if not isinstance(timestamps, Mapping):
        raise ValidationError("timestamps must be an object")
    pending_value = value.get("pending_decision")
    if pending_value is not None and not isinstance(pending_value, Mapping):
        raise ValidationError("pending decision must be an object")
    state = RunState(
        run_id=value["run_id"],
        user_input=value["user_input"],
        current_phase=value["current_phase"],
        strategy=Strategy(value["strategy"]),
        mode=Mode(value["mode"]),
        intent=value["intent"],
        complexity=Complexity(value["complexity"]),
        selected_provider=value["selected_provider"],
        selected_provider_command=tuple(value.get("selected_provider_command", ())),
        selected_model=value.get("selected_model", ""),
        completed_phases=list(value.get("completed_phases", [])),
        failed_phases=list(value.get("failed_phases", [])),
        artifacts=dict(value.get("artifacts", {})),
        tasks=[task_from_dict(item) for item in value.get("tasks", [])],
        errors=[ErrorRecord(**item) for item in value.get("errors", [])],
        status=RunStatus(value.get("status", "active")),
        pending_decision=None if pending_value is None else PendingDecision(**pending_value),
        started_at=timestamps["started_at"],
        updated_at=timestamps["updated_at"],
        finished_at=timestamps.get("finished_at"),
        schema_version=value.get("schema_version", 1),
        harness_version=value.get("harness_version", "0.1.0"),
    )
    state.validate()
    validate_tasks(state.tasks)
    return state


def validate_tasks(tasks: Sequence[Task]) -> None:
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValidationError("task IDs must be unique")
    known = set(ids)
    for task in tasks:
        missing = set(task.depends_on) - known
        if missing:
            raise ValidationError(f"unknown dependencies for {task.id}: {sorted(missing)}")
    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {task.id: task for task in tasks}

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValidationError("task dependency cycle detected")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in ids:
        visit(task_id)


def select_ready_task(tasks: Sequence[Task]) -> Task | None:
    validate_tasks(tasks)
    if sum(task.status is TaskStatus.IN_PROGRESS for task in tasks) > 1:
        raise ValidationError("only one task may be in progress")
    completed = {task.id for task in tasks if task.status is TaskStatus.COMPLETED}
    for task in tasks:
        if task.status is TaskStatus.PENDING and set(task.depends_on) <= completed:
            return task
    return None
