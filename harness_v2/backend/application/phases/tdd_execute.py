"""TDD_EXECUTE phase."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

from harness_v2.backend.application.bundle_artifacts import BundleValidationError
from harness_v2.backend.application.contracts import TestsFinished, TestsStarted
from harness_v2.backend.application.phase_artifacts.sdd import validate_tasks_document
from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.tdd_contracts import parse_tdd_review
from harness_v2.backend.domain.escalation import EscalationCategory, EscalationIssue
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName
from harness_v2.backend.domain.tasks import TaskStatus, TaskSummary
from harness_v2.backend.ports.tool_runner import ToolRunRequest, ToolRunResult


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


def execute(context: PhaseExecutionContext) -> PhaseResult:
    run = context.run
    if not run.tasks:
        raise BundleValidationError("TDD_BUNDLE requires tasks from TASKS_BUNDLE")
    if not context.runtime.allow_repository_mutation:
        reason = "TDD_BUNDLE requires an explicitly mutation-enabled working directory"
        _write_results(context, [], reason)
        return _escalated(EscalationCategory.VALIDATION_BLOCKED, reason, ("published/tdd-results.json",))
    if context.runtime.repository is None or context.runtime.rollback is None or context.runtime.tool_runner is None:
        raise BundleValidationError("TDD_EXECUTE requires repository, rollback, and tool runner runtime ports")

    task_document = context.artifacts.read_json(run.run_id, "tasks.json")
    if task_document is None:
        raise BundleValidationError("required artifact tasks.json is missing")
    validate_tasks_document(task_document)
    task_plans = {task.task_id: task for task in _task_plans(task_document)}
    summaries = list(run.tasks)
    results: list[dict[str, Any]] = []
    events: list[object] = []

    for index, summary in enumerate(summaries):
        if summary.status is TaskStatus.COMPLETED:
            continue
        plan = task_plans.get(summary.task_id)
        if plan is None:
            reason = f"task {summary.task_id} is missing from tasks.json"
            _write_results(context, results, reason)
            return _escalated(EscalationCategory.TASK_PLAN_GAP, reason, ("published/tdd-results.json",))
        summary, issue = _execute_task(context, summary, plan, results, events)
        summaries[index] = summary
        if issue is not None:
            _write_results(context, results, issue.reason)
            return PhaseResult(tasks=tuple(summaries), escalation_issue=issue, events=tuple(events))

    completed = tuple(summaries)
    _write_results(context, results, None)
    return PhaseResult(tasks=completed, events=tuple(events))


def _execute_task(
    context: PhaseExecutionContext,
    summary: TaskSummary,
    plan: TddTaskPlan,
    results: list[dict[str, Any]],
    events: list[object],
) -> tuple[TaskSummary, EscalationIssue | None]:
    current = summary
    while current.attempts < context.runtime.tdd_max_attempts:
        attempt = current.attempts + 1
        snapshot = context.runtime.repository.capture(context.runtime.working_directory)
        attempt_result: dict[str, Any] = {"task_id": current.task_id, "attempt": attempt, "events": []}
        results.append(attempt_result)
        current = current.replace(status=TaskStatus.IN_PROGRESS, attempts=attempt, last_failure=None)
        try:
            context.artifacts.run_worker_text(
                context.run,
                BundleName.TDD_BUNDLE,
                PhaseName.TDD_EXECUTE,
                "tdd_create_test",
                {"task": plan.to_mapping(), "attempt": attempt},
            )
            red_runs = _run_test_group(context, current.task_id, "red", attempt, plan.focused_tests, events)
            attempt_result["red_tests"] = [_command_payload(item) for item in red_runs]
            red_issue = _red_step_issue(red_runs)
            if red_issue is not None:
                context.runtime.rollback.restore(context.runtime.working_directory, snapshot)
                return current.replace(status=TaskStatus.FAILED, last_failure=red_issue), _issue(
                    EscalationCategory.VALIDATION_BLOCKED,
                    red_issue,
                    ("published/tdd-results.json",),
                )

            context.artifacts.run_worker_text(
                context.run,
                BundleName.TDD_BUNDLE,
                PhaseName.TDD_EXECUTE,
                "tdd_implement",
                {"task": plan.to_mapping(), "attempt": attempt, "red_tests": attempt_result["red_tests"]},
            )
            diff = context.runtime.repository.diff(snapshot, context.runtime.repository.capture(context.runtime.working_directory))
            attempt_result["diff"] = {
                "added": list(diff.added),
                "modified": list(diff.modified),
                "deleted": list(diff.deleted),
            }
            out_of_scope = _out_of_scope(diff.changed_paths, plan.touched_paths)
            if out_of_scope:
                reason = "TDD task changed paths outside touched_paths: " + ", ".join(out_of_scope)
                context.runtime.rollback.restore(context.runtime.working_directory, snapshot)
                return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
                    EscalationCategory.TASK_PLAN_GAP,
                    reason,
                    ("published/tdd-results.json",),
                )

            focused = _run_test_group(context, current.task_id, "focused", attempt, plan.focused_tests, events)
            broader = _run_test_group(context, current.task_id, "broader", attempt, plan.broader_tests, events)
            attempt_result["focused_tests"] = [_command_payload(item) for item in focused]
            attempt_result["broader_tests"] = [_command_payload(item) for item in broader]
            infra_reason = _infra_issue((*focused, *broader))
            if infra_reason is not None:
                context.runtime.rollback.restore(context.runtime.working_directory, snapshot)
                return current.replace(status=TaskStatus.FAILED, last_failure=infra_reason), _issue(
                    EscalationCategory.VALIDATION_BLOCKED,
                    infra_reason,
                    ("published/tdd-results.json",),
                )
            failed = [item for item in (*focused, *broader) if not item.succeeded]
            if failed:
                reason = "validation commands failed"
                context.runtime.rollback.restore(context.runtime.working_directory, snapshot)
                current = current.replace(status=TaskStatus.PENDING, last_failure=reason)
                continue

            review_snapshot = context.runtime.repository.capture(context.runtime.working_directory)
            review_text = context.artifacts.run_worker_text(
                context.run,
                BundleName.TDD_BUNDLE,
                PhaseName.TDD_EXECUTE,
                "tdd_review",
                {
                    "task": plan.to_mapping(),
                    "attempt": attempt,
                    "diff": attempt_result["diff"],
                    "red_tests": attempt_result["red_tests"],
                    "focused_tests": attempt_result["focused_tests"],
                    "broader_tests": attempt_result["broader_tests"],
                    "acceptance_criteria": list(plan.acceptance_criteria),
                },
            )
            review_diff = context.runtime.repository.diff(review_snapshot, context.runtime.repository.capture(context.runtime.working_directory))
            if review_diff.changed_paths:
                reason = "TDD review changed repository files despite read-only contract: " + ", ".join(review_diff.changed_paths)
                context.runtime.rollback.restore(context.runtime.working_directory, snapshot)
                return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
                    EscalationCategory.VALIDATION_BLOCKED,
                    reason,
                    ("published/tdd-results.json",),
                )
            review = parse_tdd_review(review_text)
            attempt_result["review"] = review
            if review["verdict"] == "APPROVE":
                return current.replace(status=TaskStatus.COMPLETED, last_failure=None), None
            context.runtime.rollback.restore(context.runtime.working_directory, snapshot)
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
            context.runtime.rollback.restore(context.runtime.working_directory, snapshot)
            return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
                EscalationCategory.INFRASTRUCTURE_FAILURE,
                reason,
                ("published/tdd-results.json",),
            )

    reason = f"TDD task {current.task_id} did not pass within {context.runtime.tdd_max_attempts} attempts"
    return current.replace(status=TaskStatus.FAILED, last_failure=reason), _issue(
        EscalationCategory.IMPLEMENTATION_BLOCKED,
        reason,
        ("published/tdd-results.json",),
    )


def _run_test_group(
    context: PhaseExecutionContext,
    task_id: str,
    group: str,
    attempt: int,
    commands: tuple[tuple[str, ...], ...],
    events: list[object],
) -> tuple[ToolRunResult, ...]:
    events.append(TestsStarted(context.run.run_id, task_id, group, attempt))
    results = _run_commands(context, commands)
    failed = len([result for result in results if not result.succeeded])
    events.append(TestsFinished(context.run.run_id, task_id, group, attempt, len(results), failed))
    return results


def _run_commands(context: PhaseExecutionContext, commands: tuple[tuple[str, ...], ...]) -> tuple[ToolRunResult, ...]:
    return tuple(
        context.runtime.tool_runner.run(
            ToolRunRequest(
                command=command,
                cwd=context.runtime.working_directory,
                timeout_seconds=context.runtime.tdd_command_timeout_seconds,
            )
        )
        for command in commands
    )


def _task_plans(document: dict[str, Any]) -> tuple[TddTaskPlan, ...]:
    return tuple(_task_plan(item) for item in document["tasks"])


def _task_plan(value: dict[str, Any]) -> TddTaskPlan:
    return TddTaskPlan(
        task_id=value["id"].strip(),
        title=value["title"].strip(),
        touched_paths=_text_tuple(value["touched_paths"], "touched_paths"),
        focused_tests=_commands(value["focused_tests"], "focused_tests"),
        broader_tests=_commands(value["broader_tests"], "broader_tests"),
        acceptance_criteria=_text_tuple(value["acceptance_criteria"], "acceptance_criteria"),
    )


def _commands(value: list[list[str]], field: str) -> tuple[tuple[str, ...], ...]:
    return tuple(_text_tuple(command, field) for command in value)


def _text_tuple(value: list[str], _field: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value)


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


def _write_results(context: PhaseExecutionContext, results: list[dict[str, Any]], blocked_reason: str | None) -> None:
    context.artifacts.write_json(context.run.run_id, "published/tdd-results.json", {"schema_version": 1, "phase": "tdd", "results": results, "blocked_reason": blocked_reason})


def _issue(category: EscalationCategory, reason: str, evidence: tuple[str, ...]) -> EscalationIssue:
    return EscalationIssue(
        issue_id="tdd-execute-blocked",
        origin_bundle=BundleName.TDD_BUNDLE,
        category=category,
        reason=reason,
        evidence_artifact_ids=evidence,
    )


def _escalated(category: EscalationCategory, reason: str, evidence: tuple[str, ...]) -> PhaseResult:
    return PhaseResult(escalation_issue=_issue(category, reason, evidence))
