"""Command, query, event, and result DTOs for the v2 backend boundary."""

from __future__ import annotations

from dataclasses import dataclass



class RunNotFoundError(KeyError):
    """Raised when a command or query targets an unknown run."""


class InvalidRunStateError(RuntimeError):
    """Raised when a command is not valid for the run's current state."""


BUNDLE_VALUES = frozenset((
    "SDD_BUNDLE",
    "EXPLORE_BUNDLE",
    "KNOWLEDGE_EXTRACT_EXPLORE",
    "PROPOSAL_BUNDLE",
    "SPEC_BUNDLE",
    "DESIGN_BUNDLE",
    "TASKS_BUNDLE",
    "TDD_BUNDLE",
    "KNOWLEDGE_EXTRACT_TDD",
))
PHASE_VALUES = frozenset((
    "EXPLORE_REQUEST_UNDERSTANDING",
    "EXPLORE_CONTEXT_PACK",
    "EXPLORE_EVIDENCE_DIGEST",
    "EXPLORE_EXPLORATION_MAP",
    "EXPLORE_OUTCOME_SYNTHESIS",
    "EXPLORE_HANDOFF",
    "KNOWLEDGE_EXTRACT_EXPLORE_SYNTHESIS",
    "KNOWLEDGE_EXTRACT_EXPLORE_PATCH",
    "PROPOSAL_PURPOSE",
    "PROPOSAL_HANDOFF",
    "SPEC_DRAFT",
    "SPEC_HANDOFF",
    "DESIGN_DRAFT",
    "DESIGN_HANDOFF",
    "TASKS_DRAFT",
    "TASKS_HANDOFF",
    "VALIDATE_JSON",
    "TDD_CREATE_TEST",
    "TDD_IMPLEMENT",
    "TDD_REVIEW",
    "TDD_HANDOFF",
    "KNOWLEDGE_EXTRACT_TDD_SYNTHESIS",
    "KNOWLEDGE_EXTRACT_TDD_PATCH",
))
RUN_STATUS_VALUES = frozenset(("PENDING", "RUNNING", "WAITING_FOR_USER", "COMPLETED", "FAILED", "CANCELLED"))
CI_TARGET_VALUES = frozenset(("github", "gitlab", "both"))
KNOWLEDGE_PATCH_STATUS_VALUES = frozenset(("CANDIDATE", "REJECTED"))
CI_SIGNAL_SCOPE_VALUES = frozenset(("trunk_baseline", "branch", "merge_request", "post_merge_refresh"))


def _require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _text_tuple(values: tuple[str, ...] | list[str], field: str) -> tuple[str, ...]:
    normalized = tuple(_require_text(value, field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field} must not contain duplicates")
    return normalized


def _bundle_text(value: str, field: str = "bundle") -> str:
    normalized = _require_text(value, field)
    if normalized not in BUNDLE_VALUES:
        raise ValueError(f"{field} is not a known bundle")
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


def _ci_target_text(value: str, field: str = "target") -> str:
    normalized = _require_text(value, field)
    if normalized not in CI_TARGET_VALUES:
        raise ValueError(f"{field} must be github, gitlab, or both")
    return normalized


def _knowledge_patch_status(value: str, field: str = "status") -> str:
    normalized = _require_text(value, field)
    if normalized not in KNOWLEDGE_PATCH_STATUS_VALUES:
        raise ValueError(f"{field} is not a known knowledge patch status")
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
    root_bundle: str = "SDD_BUNDLE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "root_bundle", _bundle_text(self.root_bundle, "root_bundle"))


@dataclass(frozen=True, slots=True)
class ResumeRun:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class RetryPhase:
    run_id: str
    bundle: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))
        object.__setattr__(self, "phase", _phase_text(self.phase))


@dataclass(frozen=True, slots=True)
class RetryBundle:
    run_id: str
    bundle: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))


@dataclass(frozen=True, slots=True)
class CancelRun:
    run_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))


@dataclass(frozen=True, slots=True)
class InstallCiTemplates:
    target: str = "github"
    force: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _ci_target_text(self.target))
        if not isinstance(self.force, bool):
            raise TypeError("force must be bool")


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
class RejectKnowledgePatch:
    patch_id: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", _require_text(self.patch_id, "patch_id"))
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


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
class ListKnowledgePatches:
    run_id: str | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", None if self.run_id is None else _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "status", None if self.status is None else _knowledge_patch_status(self.status))


@dataclass(frozen=True, slots=True)
class GetKnowledgePatch:
    patch_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", _require_text(self.patch_id, "patch_id"))


@dataclass(frozen=True, slots=True)
class RunStarted:
    run_id: str
    request: str
    root_bundle: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "root_bundle", _bundle_text(self.root_bundle, "root_bundle"))


@dataclass(frozen=True, slots=True)
class BundleStarted:
    run_id: str
    bundle: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))


@dataclass(frozen=True, slots=True)
class BundleCompleted:
    run_id: str
    bundle: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))


@dataclass(frozen=True, slots=True)
class BundleFailed:
    run_id: str
    bundle: str
    error: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))
        object.__setattr__(self, "error", _require_text(self.error, "error"))


@dataclass(frozen=True, slots=True)
class BundleRetryStarted:
    run_id: str
    bundle: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))


@dataclass(frozen=True, slots=True)
class PhaseStarted:
    run_id: str
    bundle: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))
        object.__setattr__(self, "phase", _phase_text(self.phase))


@dataclass(frozen=True, slots=True)
class PhaseCompleted:
    run_id: str
    bundle: str
    phase: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))
        object.__setattr__(self, "phase", _phase_text(self.phase))


@dataclass(frozen=True, slots=True)
class PhaseFailed:
    run_id: str
    bundle: str
    phase: str
    error: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "bundle", _bundle_text(self.bundle))
        object.__setattr__(self, "phase", _phase_text(self.phase))
        object.__setattr__(self, "error", _require_text(self.error, "error"))


@dataclass(frozen=True, slots=True)
class KnowledgePatchCreated:
    run_id: str
    patch_id: str
    origin_bundle: str
    path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "patch_id", _require_text(self.patch_id, "patch_id"))
        object.__setattr__(self, "origin_bundle", _bundle_text(self.origin_bundle, "origin_bundle"))
        object.__setattr__(self, "path", _require_text(self.path, "path"))


@dataclass(frozen=True, slots=True)
class KnowledgePatchRejected:
    patch_id: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", _require_text(self.patch_id, "patch_id"))
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class TestsStarted:
    run_id: str
    task_id: str
    group: str
    attempt: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "task_id", _require_text(self.task_id, "task_id"))
        object.__setattr__(self, "group", _require_text(self.group, "group"))
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")


@dataclass(frozen=True, slots=True)
class TestsFinished:
    run_id: str
    task_id: str
    group: str
    attempt: int
    total: int
    failed: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "task_id", _require_text(self.task_id, "task_id"))
        object.__setattr__(self, "group", _require_text(self.group, "group"))
        for field in ("attempt", "total", "failed"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if self.failed > self.total:
            raise ValueError("failed tests cannot exceed total tests")


@dataclass(frozen=True, slots=True)
class EscalationRaised:
    run_id: str
    issue_id: str
    origin_bundle: str
    category: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "issue_id", _require_text(self.issue_id, "issue_id"))
        object.__setattr__(self, "origin_bundle", _bundle_text(self.origin_bundle, "origin_bundle"))
        object.__setattr__(self, "category", _require_text(self.category, "category"))
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class EscalationResolved:
    run_id: str
    issue_id: str
    action: str
    target_bundle: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "issue_id", _require_text(self.issue_id, "issue_id"))
        action = _require_text(self.action, "action")
        if action not in {"ASK_USER", "REWIND", "FAIL", "CONTINUE"}:
            raise ValueError("action is not a known escalation resolution")
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "target_bundle", None if self.target_bundle is None else _bundle_text(self.target_bundle, "target_bundle"))
        if self.action == "REWIND" and self.target_bundle is None:
            raise ValueError("REWIND escalation resolution requires a target bundle")
        if self.action != "REWIND" and self.target_bundle is not None:
            raise ValueError("only REWIND escalation resolution may target a bundle")


@dataclass(frozen=True, slots=True)
class UserDecisionRequested:
    run_id: str
    decision_id: str
    origin_bundle: str
    prompt: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "origin_bundle", _bundle_text(self.origin_bundle, "origin_bundle"))
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


@dataclass(frozen=True, slots=True)
class CiTemplatesInstalled:
    target: str
    installed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _ci_target_text(self.target))
        object.__setattr__(self, "installed", _text_tuple(self.installed, "installed"))
        object.__setattr__(self, "skipped", _text_tuple(self.skipped, "skipped"))
        object.__setattr__(self, "warnings", _text_tuple(self.warnings, "warnings"))


Event = (
    RunStarted | BundleStarted | BundleCompleted | BundleFailed | BundleRetryStarted | PhaseStarted | PhaseCompleted | PhaseFailed |
    KnowledgePatchCreated | KnowledgePatchRejected | TestsStarted | TestsFinished | EscalationRaised | EscalationResolved |
    UserDecisionRequested | UserDecisionReceived | RunResumed | RunCompleted | RunCancelled | CiTemplatesInstalled
)
Command = StartRun | ResumeRun | RetryPhase | RetryBundle | CancelRun | InstallCiTemplates | SubmitUserDecision | RejectKnowledgePatch
Query = GetRun | ListRuns | GetRunState | GetAvailableActions | ListKnowledgePatches | GetKnowledgePatch


@dataclass(frozen=True, slots=True)
class PendingDecisionView:
    decision_id: str
    origin_bundle: str
    prompt: str
    created_at: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _require_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "origin_bundle", _bundle_text(self.origin_bundle, "origin_bundle"))
        object.__setattr__(self, "prompt", _require_text(self.prompt, "prompt"))
        object.__setattr__(self, "created_at", _require_text(self.created_at, "created_at"))
        object.__setattr__(self, "options", _text_tuple(self.options, "options"))


@dataclass(frozen=True, slots=True)
class TaskSummaryView:
    task_id: str
    title: str
    status: str
    attempts: int = 0
    last_failure: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _require_text(self.task_id, "task_id"))
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "status", _require_text(self.status, "status"))
        if isinstance(self.attempts, bool) or self.attempts < 0:
            raise ValueError("attempts must be a non-negative integer")
        if self.last_failure is not None:
            object.__setattr__(self, "last_failure", _require_text(self.last_failure, "last_failure"))


@dataclass(frozen=True, slots=True)
class ErrorView:
    code: str
    message: str
    bundle: str | None = None
    phase: str | None = None
    timestamp: str = "unknown"

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _require_text(self.code, "code"))
        object.__setattr__(self, "message", _require_text(self.message, "message"))
        object.__setattr__(self, "bundle", None if self.bundle is None else _bundle_text(self.bundle, "bundle"))
        object.__setattr__(self, "phase", None if self.phase is None else _phase_text(self.phase))
        object.__setattr__(self, "timestamp", _require_text(self.timestamp, "timestamp"))


@dataclass(frozen=True, slots=True)
class KnowledgePatchView:
    patch_id: str
    run_id: str
    origin_bundle: str
    version: int
    status: str
    path: str
    proposal_id: str
    summary: str
    created_at: str
    rejected_at: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "patch_id", _require_text(self.patch_id, "patch_id"))
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "origin_bundle", _bundle_text(self.origin_bundle, "origin_bundle"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        object.__setattr__(self, "status", _knowledge_patch_status(self.status))
        object.__setattr__(self, "path", _require_text(self.path, "path"))
        object.__setattr__(self, "proposal_id", _require_text(self.proposal_id, "proposal_id"))
        object.__setattr__(self, "summary", _require_text(self.summary, "summary"))
        object.__setattr__(self, "created_at", _require_text(self.created_at, "created_at"))
        if self.rejected_at is not None:
            object.__setattr__(self, "rejected_at", _require_text(self.rejected_at, "rejected_at"))
        if self.rejection_reason is not None:
            object.__setattr__(self, "rejection_reason", _require_text(self.rejection_reason, "rejection_reason"))


@dataclass(frozen=True, slots=True)
class RunView:
    run_id: str
    request: str
    status: str
    root_bundle: str
    current_bundle: str | None = None
    current_phase: str | None = None
    completed_phases: tuple[str, ...] = ()
    completed_bundles: tuple[str, ...] = ()
    pending_decision: PendingDecisionView | None = None
    tasks: tuple[TaskSummaryView, ...] = ()
    errors: tuple[ErrorView, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "status", _status_text(self.status))
        object.__setattr__(self, "root_bundle", _bundle_text(self.root_bundle, "root_bundle"))
        object.__setattr__(self, "current_bundle", None if self.current_bundle is None else _bundle_text(self.current_bundle, "current_bundle"))
        object.__setattr__(self, "current_phase", None if self.current_phase is None else _phase_text(self.current_phase, "current_phase"))
        object.__setattr__(self, "completed_phases", tuple(_phase_text(phase, "completed_phases") for phase in self.completed_phases))
        object.__setattr__(self, "completed_bundles", tuple(_bundle_text(bundle, "completed_bundles") for bundle in self.completed_bundles))
        if self.pending_decision is not None:
            _require_instance(self.pending_decision, PendingDecisionView, "pending_decision")
        object.__setattr__(self, "tasks", _typed_tuple(self.tasks, TaskSummaryView, "tasks"))
        object.__setattr__(self, "errors", _typed_tuple(self.errors, ErrorView, "errors"))


@dataclass(frozen=True, slots=True)
class RunSummaryView:
    run_id: str
    request: str
    status: str
    current_bundle: str | None = None
    current_phase: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "request", _require_text(self.request, "request"))
        object.__setattr__(self, "status", _status_text(self.status))
        object.__setattr__(self, "current_bundle", None if self.current_bundle is None else _bundle_text(self.current_bundle, "current_bundle"))
        object.__setattr__(self, "current_phase", None if self.current_phase is None else _phase_text(self.current_phase, "current_phase"))


@dataclass(frozen=True, slots=True)
class CommandResult:
    run: RunView
    events: tuple[Event, ...]

    def __post_init__(self) -> None:
        _require_instance(self.run, RunView, "run")
        object.__setattr__(self, "events", _typed_tuple(self.events, Event, "events"))


@dataclass(frozen=True, slots=True)
class InstallCiTemplatesResult:
    target: str
    installed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    events: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _ci_target_text(self.target))
        object.__setattr__(self, "installed", _text_tuple(self.installed, "installed"))
        object.__setattr__(self, "skipped", _text_tuple(self.skipped, "skipped"))
        object.__setattr__(self, "warnings", _text_tuple(self.warnings, "warnings"))
        object.__setattr__(self, "events", _typed_tuple(self.events, CiTemplatesInstalled, "events"))


@dataclass(frozen=True, slots=True)
class GetRunResult:
    run: RunView
    def __post_init__(self) -> None: _require_instance(self.run, RunView, "run")


@dataclass(frozen=True, slots=True)
class ListRunsResult:
    runs: tuple[RunSummaryView, ...]
    def __post_init__(self) -> None: object.__setattr__(self, "runs", _typed_tuple(self.runs, RunSummaryView, "runs"))


@dataclass(frozen=True, slots=True)
class GetRunStateResult:
    run_id: str
    status: str
    current_bundle: str | None = None
    current_phase: str | None = None
    pending_decision: PendingDecisionView | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "status", _status_text(self.status))
        object.__setattr__(self, "current_bundle", None if self.current_bundle is None else _bundle_text(self.current_bundle, "current_bundle"))
        object.__setattr__(self, "current_phase", None if self.current_phase is None else _phase_text(self.current_phase, "current_phase"))
        if self.pending_decision is not None: _require_instance(self.pending_decision, PendingDecisionView, "pending_decision")


@dataclass(frozen=True, slots=True)
class GetAvailableActionsResult:
    run_id: str
    actions: tuple[str, ...]
    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _require_text(self.run_id, "run_id"))
        object.__setattr__(self, "actions", _text_tuple(self.actions, "actions"))


@dataclass(frozen=True, slots=True)
class GetKnowledgePatchResult:
    patch: KnowledgePatchView
    def __post_init__(self) -> None: _require_instance(self.patch, KnowledgePatchView, "patch")


@dataclass(frozen=True, slots=True)
class ListKnowledgePatchesResult:
    patches: tuple[KnowledgePatchView, ...]
    def __post_init__(self) -> None: object.__setattr__(self, "patches", _typed_tuple(self.patches, KnowledgePatchView, "patches"))


@dataclass(frozen=True, slots=True)
class RejectKnowledgePatchResult:
    patch: KnowledgePatchView
    events: tuple[KnowledgePatchRejected, ...]
    def __post_init__(self) -> None:
        _require_instance(self.patch, KnowledgePatchView, "patch")
        object.__setattr__(self, "events", _typed_tuple(self.events, KnowledgePatchRejected, "events"))


CommandExecutionResult = CommandResult | InstallCiTemplatesResult | RejectKnowledgePatchResult
QueryResult = GetRunResult | ListRunsResult | GetRunStateResult | GetAvailableActionsResult | GetKnowledgePatchResult | ListKnowledgePatchesResult
