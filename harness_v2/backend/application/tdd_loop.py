"""Application service for the v2 TDD implementation loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.bundle_orchestration import BundleContext, BundleExecutionResult
from harness_v2.backend.domain.escalation import EscalationCategory, EscalationIssue
from harness_v2.backend.domain.lifecycle import PhaseName
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary
from harness_v2.backend.ports.repository import RepositoryRollbackPort, RepositorySnapshotPort
from harness_v2.backend.ports.tool_runner import ToolRunnerPort, ToolRunRequest, ToolRunResult


@dataclass(frozen=True, slots=True)
class TddResultReporter:
    def write_results(self, context: BundleContext, results: list[dict[str, Any]], blocked_reason: str | None) -> None:
        context.artifacts.write_json(context.run.run_id, "published/tdd-results.json", _results_payload(results, blocked_reason))

    def write_handoff(self, context: BundleContext, summaries: tuple[TaskSummary, ...]) -> None:
        context.artifacts.write_json(
            context.run.run_id,
            "published/tdd-handoff.json",
            {
                "schema_version": 1,
                "bundle": "tdd",
                "artifacts": ["tasks.json", "published/tdd-results.json"],
                "next_bundle": None,
                "completed_tasks": [task.task_id for task in summaries if task.status is TaskStatus.COMPLETED],
            },
        )


@dataclass(frozen=True, slots=True)
class TddLoopService:
    repository: RepositorySnapshotPort
    rollback: RepositoryRollbackPort
    tool_runner: ToolRunnerPort
    max_attempts: int = 3
    reporter: TddResultReporter = field(default_factory=TddResultReporter)

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")

    def execute(self, context: BundleContext) -> BundleExecutionResult:
        run = context.run
        if not run.tasks:
            raise BundleValidationError("TDD_BUNDLE requires tasks from TASKS_BUNDLE")
        if not context.runtime.allow_repository_mutation:
            reason = "TDD_BUNDLE requires an explicitly mutation-enabled working directory"
            self.reporter.write_results(context, [], reason)
            return _escalated(EscalationCategory.VALIDATION_BLOCKED, reason, ("published/tdd-results.json",))

        task_document = context.artifacts.read_json(run.run_id, "tasks.json")
        if task_document is None:
            raise BundleValidationError("required artifact tasks.json is missing")
        task_plans = {task.task_id: task for task in _task_plans(task_document)}
        summaries = list(run.tasks)
        results: list[dict[str, Any]] = []

        for index, summary in enumerate(summaries):
            if summary.status is TaskStatus.COMPLETED:
                continue
            plan = task_plans.get(summary.task_id)
            if plan is None:
                reason = f"task {summary.task_id} is missing from tasks.json"
                self.reporter.write_results(context, results, reason)
                return _escalated(EscalationCategory.TASK_PLAN_GAP, reason, ("published/tdd-results.json",))
            summary, issue = self._execute_task(context, summary, plan, results)
            summaries[index] = summary
            if issue is not None:
                self.reporter.write_results(context, results, issue.reason)
                return BundleExecutionResult(tasks=tuple(summaries), escalation_issue=issue)

        completed = tuple(summaries)
        self.reporter.write_results(context, results, None)
        self.reporter.write_handoff(context, completed)
        return BundleExecutionResult(tasks=completed)

    def _execute_task(
        self,
        context: BundleContext,
        summary: TaskSummary,
        plan: "TddTaskPlan",
        results: list[dict[str, Any]],
    ) -> tuple[TaskSummary, EscalationIssue | None]:
        current = summary
        while current.attempts < self.max_attempts:
            attempt = current.attempts + 1
            snapshot = self.repository.capture(context.runtime.working_directory)
            attempt_result: dict[str, Any] = {"task_id": current.task_id, "attempt": attempt, "events": []}
            results.append(attempt_result)
            current = current.replace(status=TaskStatus.IN_PROGRESS, attempts=attempt, last_failure=None)
            try:
                context.artifacts.run_worker_text(
                    context.run,
                    PhaseName.TDD_BUNDLE,
                    "tdd_create_test",
                    {"task": plan.to_mapping(), "attempt": attempt},
                )
                red_runs = self._run_commands(context, plan.focused_tests)
                attempt_result["red_tests"] = [_command_payload(item) for item in red_runs]
                red_issue = _red_step_issue(red_runs)
                if red_issue is not None:
                    self.rollback.restore(context.runtime.working_directory, snapshot)
                    return current.replace(status=TaskStatus.FAILED, last_failure=red_issue), _issue(
                        EscalationCategory.VALIDATION_BLOCKED,
                        red_issue,
                        ("published/tdd-results.json",),
                    )

                context.artifacts.run_worker_text(
                    context.run,
                    PhaseName.TDD_BUNDLE,
                    "tdd_implement",
                    {"task": plan.to_mapping(), "attempt": attempt, "red_tests": attempt_result["red_tests"]},
                )
                diff = self.repository.diff(snapshot, self.repository.capture(context.runtime.working_directory))
                attempt_result["diff"] = {
                    "added": list(diff.added),
                    "modified": list(diff.modified),
                    "deleted": list(diff.deleted),
                }
                out_of_scope = _out_of_scope(diff.changed_paths, plan.touched_paths)
                if out_of_scope:
                    reason = "TDD task changed paths outside touched_paths: " + ", ".join(out_of_scope)
                    self.rollback.restore(context.runtime.working_directory, snapshot)
                    return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
                        EscalationCategory.TASK_PLAN_GAP,
                        reason,
                        ("published/tdd-results.json",),
                    )

                focused = self._run_commands(context, plan.focused_tests)
                broader = self._run_commands(context, plan.broader_tests)
                attempt_result["focused_tests"] = [_command_payload(item) for item in focused]
                attempt_result["broader_tests"] = [_command_payload(item) for item in broader]
                infra_reason = _infra_issue((*focused, *broader))
                if infra_reason is not None:
                    self.rollback.restore(context.runtime.working_directory, snapshot)
                    return current.replace(status=TaskStatus.FAILED, last_failure=infra_reason), _issue(
                        EscalationCategory.VALIDATION_BLOCKED,
                        infra_reason,
                        ("published/tdd-results.json",),
                    )
                failed = [item for item in (*focused, *broader) if not item.succeeded]
                if failed:
                    reason = "validation commands failed"
                    self.rollback.restore(context.runtime.working_directory, snapshot)
                    current = current.replace(status=TaskStatus.PENDING, last_failure=reason)
                    continue

                review_text = context.artifacts.run_worker_text(
                    context.run,
                    PhaseName.TDD_BUNDLE,
                    "tdd_review",
                    {"task": plan.to_mapping(), "attempt": attempt, "diff": attempt_result["diff"]},
                )
                review = parse_tdd_review(review_text)
                attempt_result["review"] = review
                if review["verdict"] == "APPROVE":
                    return current.replace(status=TaskStatus.COMPLETED, last_failure=None), None
                self.rollback.restore(context.runtime.working_directory, snapshot)
                escalation_category = review.get("escalation_category")
                if escalation_category is not None:
                    reason = f"TDD review requested escalation: {escalation_category}"
                    return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
                        EscalationCategory(escalation_category),
                        reason,
                        ("published/tdd-results.json",),
                    )
                reason = "TDD review requested changes"
                current = current.replace(status=TaskStatus.PENDING, last_failure=reason)
            except Exception as exc:
                reason = str(exc) or type(exc).__name__
                self.rollback.restore(context.runtime.working_directory, snapshot)
                return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
                    EscalationCategory.INFRASTRUCTURE_FAILURE,
                    reason,
                    ("published/tdd-results.json",),
                )

        reason = f"TDD task {current.task_id} did not pass within {self.max_attempts} attempts"
        return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
            EscalationCategory.IMPLEMENTATION_BLOCKED,
            reason,
            ("published/tdd-results.json",),
        )

    def _run_commands(self, context: BundleContext, commands: tuple[tuple[str, ...], ...]) -> tuple[ToolRunResult, ...]:
        return tuple(
            self.tool_runner.run(
                ToolRunRequest(
                    command=command,
                    cwd=context.runtime.working_directory,
                    timeout_seconds=context.runtime.tdd_command_timeout_seconds,
                )
            )
            for command in commands
        )


@dataclass(frozen=True, slots=True)
class TddTaskPlan:
    task_id: str
    title: str
    touched_paths: tuple[str, ...]
    focused_tests: tuple[tuple[str, ...], ...]
    broader_tests: tuple[tuple[str, ...], ...]
    acceptance_criteria: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "title": self.title,
            "touched_paths": list(self.touched_paths),
            "focused_tests": [list(command) for command in self.focused_tests],
            "broader_tests": [list(command) for command in self.broader_tests],
            "acceptance_criteria": list(self.acceptance_criteria),
        }


def parse_tdd_review(text: str) -> dict[str, Any]:
    verdict: str | None = None
    escalation_category: str | None = None
    findings: list[str] = []
    section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if section == "Verdict" and verdict is None:
            if line not in {"APPROVE", "REQUEST_CHANGES"}:
                raise BundleValidationError("TDD review verdict must be APPROVE or REQUEST_CHANGES")
            verdict = line
            continue
        if section == "Escalation Category" and escalation_category is None:
            escalation_category = _review_escalation_category(line).value
            continue
        if section == "Findings" and line.startswith("-"):
            findings.append(line.lstrip("- ").strip())
    if verdict not in {"APPROVE", "REQUEST_CHANGES"}:
        raise BundleValidationError("TDD review missing verdict")
    if verdict == "APPROVE" and escalation_category is not None:
        raise BundleValidationError("approved TDD review must not include escalation category")
    return {"verdict": verdict, "findings": findings, "escalation_category": escalation_category}


def _review_escalation_category(value: str) -> EscalationCategory:
    try:
        category = EscalationCategory(value)
    except ValueError as exc:
        raise BundleValidationError("TDD review escalation category is unknown") from exc
    allowed = {
        EscalationCategory.DESIGN_GAP,
        EscalationCategory.TASK_PLAN_GAP,
        EscalationCategory.IMPLEMENTATION_BLOCKED,
        EscalationCategory.VALIDATION_BLOCKED,
    }
    if category not in allowed:
        raise BundleValidationError("TDD review escalation category is not valid for TDD")
    return category


def _task_plans(document: dict[str, Any]) -> tuple[TddTaskPlan, ...]:
    raw_tasks = document.get("tasks")
    if not isinstance(raw_tasks, list):
        raise BundleValidationError("tasks.json tasks must be a list")
    return tuple(_task_plan(item) for item in raw_tasks)


def _task_plan(value: object) -> TddTaskPlan:
    if not isinstance(value, dict):
        raise BundleValidationError("task item must be an object")
    return TddTaskPlan(
        task_id=_text(value.get("id"), "task id"),
        title=_text(value.get("title"), "task title"),
        touched_paths=_text_tuple(value.get("touched_paths"), "touched_paths"),
        focused_tests=_commands(value.get("focused_tests"), "focused_tests"),
        broader_tests=_commands(value.get("broader_tests"), "broader_tests"),
        acceptance_criteria=_text_tuple(value.get("acceptance_criteria"), "acceptance_criteria"),
    )


def _commands(value: object, field: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise BundleValidationError(f"{field} must be a list")
    commands: list[tuple[str, ...]] = []
    for command in value:
        commands.append(_text_tuple(command, field))
    return tuple(commands)


def _text_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise BundleValidationError(f"{field} must be a list of nonempty strings")
    return tuple(item.strip() for item in value)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BundleValidationError(f"{field} is required")
    return value.strip()


def _red_step_issue(results: tuple[ToolRunResult, ...]) -> str | None:
    infra = _infra_issue(results)
    if infra is not None:
        return infra
    if all(result.succeeded for result in results):
        return "focused tests passed before implementation; TDD red step was not proven"
    return None


def _infra_issue(results: tuple[ToolRunResult, ...]) -> str | None:
    for result in results:
        command = " ".join(result.command)
        if result.missing_executable:
            return f"validation command executable is missing: {command}"
        if result.timed_out:
            return f"validation command timed out: {command}"
    return None


def _out_of_scope(paths: tuple[str, ...], allowed: tuple[str, ...]) -> tuple[str, ...]:
    if "." in allowed:
        return ()
    return tuple(path for path in paths if not any(_path_allowed(path, pattern) for pattern in allowed))


def _path_allowed(path: str, pattern: str) -> bool:
    normalized = pattern.rstrip("/")
    return path == normalized or path.startswith(normalized + "/") or fnmatch(path, normalized)


def _command_payload(result: ToolRunResult) -> dict[str, Any]:
    return {
        "command": list(result.command),
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "missing_executable": result.missing_executable,
    }


def _results_payload(results: list[dict[str, Any]], blocked_reason: str | None) -> dict[str, Any]:
    return {"schema_version": 1, "phase": "tdd", "results": results, "blocked_reason": blocked_reason}


def _issue(category: EscalationCategory, reason: str, evidence: tuple[str, ...]) -> EscalationIssue:
    return EscalationIssue(
        issue_id="tdd-loop-blocked",
        origin_phase=PhaseName.TDD_BUNDLE,
        category=category,
        reason=reason,
        evidence_artifact_ids=evidence,
    )


def _escalated(category: EscalationCategory, reason: str, evidence: tuple[str, ...]) -> BundleExecutionResult:
    return BundleExecutionResult(escalation_issue=_issue(category, reason, evidence))
