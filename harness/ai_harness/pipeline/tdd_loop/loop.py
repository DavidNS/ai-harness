"""Controller loop implementation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Sequence

from ...config import CONTROLLER_DEFAULT_ATTEMPTS, CONTROLLER_MAX_ATTEMPTS
from ...control_outputs import ControlFlowSignal, PhaseEscalation
from ...errors import ProviderPhaseError, ValidationError
from ...models import ReviewVerdict, Task, TaskStatus, select_ready_task
from ...phases import PhaseRepairExhaustedError, PhaseValidationError
from ...pipeline.state_machine import GRAPHS, graph_for
from ...stores.artifact import ArtifactStore
from ...stores.state import StateStore
from .commands import run_command
from .repository import (
    _repository_changes,
    _repository_directories,
    _repository_snapshot,
    _restore_repository_snapshot,
)
from .review import _review_result
from .types import (
    CommandEvidence,
    CommandRunner,
    ImplementationOutcome,
    ImplementWorker,
    LoopResult,
    ReviewWorker,
    TaskPlan,
)


class ObservedScopeViolation(ValidationError):
    """Observed repository changes escaped the current task boundary."""

    def __init__(self, outside_paths: Sequence[str], allowed_paths: Sequence[str]) -> None:
        self.outside_paths = tuple(outside_paths)
        self.allowed_paths = tuple(allowed_paths)
        paths = ", ".join(self.outside_paths)
        allowed = ", ".join(self.allowed_paths) or "<none>"
        super().__init__(f"observed changed path is outside task scope: {paths}; allowed paths: {allowed}")


class TddLoop:
    """Process at most one ready task through bounded implementation attempts."""

    def __init__(
        self,
        target_repository: Path,
        state_store: StateStore,
        plans: Sequence[TaskPlan],
        implement: ImplementWorker,
        review: ReviewWorker,
        *,
        artifacts: ArtifactStore | None = None,
        command_runner: CommandRunner = run_command,
        timeout_seconds: float = 120.0,
        max_attempts: int = CONTROLLER_DEFAULT_ATTEMPTS,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.target = Path(target_repository).resolve()
        if not self.target.is_dir():
            raise ValidationError("target repository must be a directory")
        if isinstance(max_attempts, bool) or not 1 <= max_attempts <= CONTROLLER_MAX_ATTEMPTS:
            raise ValidationError("max attempts must be between one and ten")
        if timeout_seconds <= 0:
            raise ValidationError("test timeout must be positive")
        self.state_store = state_store
        self.artifacts = artifacts or state_store.artifacts
        self.plans = {plan.id: plan for plan in plans}
        if len(self.plans) != len(plans):
            raise ValidationError("task plan IDs must be unique")
        self.implement = implement
        self.review = review
        self.command_runner = command_runner
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.progress = progress or (lambda _: None)

    def _save_task(self, task: Task) -> None:
        state = self.state_store.load()
        matches = [index for index, candidate in enumerate(state.tasks) if candidate.id == task.id]
        if len(matches) != 1:
            raise ValidationError(f"state must contain task exactly once: {task.id}")
        state.tasks[matches[0]] = task
        self.state_store.save(state)

    def _validated_paths(self, paths: Sequence[str]) -> tuple[str, ...]:
        result: list[str] = []
        for raw in paths:
            if not isinstance(raw, str) or not raw:
                raise ValidationError("changed paths must be nonempty strings")
            path = Path(raw)
            candidate = path.resolve() if path.is_absolute() else (self.target / path).resolve()
            if not candidate.is_relative_to(self.target):
                raise ValidationError(f"changed path is outside target repository: {raw}")
            result.append(candidate.relative_to(self.target).as_posix())
        return tuple(dict.fromkeys(result))

    def _validate_observed_scope(self, paths: Sequence[str], allowed_paths: Sequence[str]) -> None:
        allowed = self._validated_paths(allowed_paths)
        outside: list[str] = []
        for path in paths:
            if not any(base == "." or path == base or path.startswith(f"{base}/") for base in allowed):
                outside.append(path)
        if outside:
            raise ObservedScopeViolation(outside, allowed)

    @staticmethod
    def _scope_violation_feedback(task: Task, violation: ObservedScopeViolation) -> str:
        outside = ", ".join(violation.outside_paths)
        allowed = ", ".join(violation.allowed_paths) or "<none>"
        return (
            f"hard task-scope violation for {task.id}: observed changed path is outside task scope: {outside}. "
            f"Allowed paths for this task are: {allowed}. Retry without touching paths outside this task scope. "
            "If the requested behavior cannot be implemented within these paths, do not choose an escalation target; "
            "return a clear blocked explanation so the controller can route it."
        )

    @staticmethod
    def _scope_escalation_reason(task: Task, violation: ObservedScopeViolation) -> str:
        outside = ", ".join(violation.outside_paths)
        allowed = ", ".join(violation.allowed_paths) or "<none>"
        return (
            f"Task {task.id} repeatedly changed path(s) outside its allowed scope: {outside}. "
            f"Allowed paths were: {allowed}. The task boundary or touched_paths are incompatible with the implementation need; "
            "regenerate the task plan so the required files are included in the correct task or the work is split differently."
        )

    def _scope_escalation_target(self) -> str:
        state = self.state_store.load()
        graph = graph_for(state.strategy, state.complexity)
        return "TASKS" if "TASKS" in graph else "SIMPLE_TASK"

    def _write_attempt(self, task: Task, attempt: int, outcome: ImplementationOutcome,
                       *, status: str, evidence: Sequence[CommandEvidence] = (),
                       review: str | None = None, failure: str | None = None) -> None:
        name = f"attempts/{task.id}/{attempt}.json"
        self.artifacts.write_json(name, {
            "schema_version": 1, "task_id": task.id, "attempt": attempt, "status": status,
            "implementation": {"changed_paths": list(outcome.changed_paths), "summary": outcome.summary,
                               "exit_code": outcome.exit_code, "stderr": outcome.stderr,
                               "repository_diff": outcome.repository_diff},
            "test_evidence": [item.to_dict() for item in evidence],
            "review": review, "failure": failure,
        })
        self.state_store.record_artifact(name, "TDD_LOOP")

    @staticmethod
    def _review_result(candidate: str):
        return _review_result(candidate)

    def run_one(self) -> LoopResult | None:
        state = self.state_store.load()
        in_progress = [task for task in state.tasks if task.status is TaskStatus.IN_PROGRESS]
        if len(in_progress) > 1:
            raise ValidationError("only one task may be in progress")
        selected = in_progress[0] if in_progress else select_ready_task(state.tasks)
        if selected is None:
            return None
        try:
            plan = self.plans[selected.id]
        except KeyError as exc:
            raise ValidationError(f"task plan is missing: {selected.id}") from exc

        task = selected if selected.status is TaskStatus.IN_PROGRESS else replace(selected, status=TaskStatus.IN_PROGRESS)
        self._save_task(task)
        failures = ([f"resuming interrupted task after attempt {task.attempts}"]
                    if selected.status is TaskStatus.IN_PROGRESS else [])

        if task.attempts >= self.max_attempts:
            task = replace(task, status=TaskStatus.FAILED)
            self._save_task(task)
            return LoopResult(task.id, task.status, task.attempts, "implementation attempts exhausted")

        observed_scope_violations: set[str] = set()
        for attempt in range(task.attempts + 1, self.max_attempts + 1):
            self.progress(f"Task {task.id} attempt {attempt}/{self.max_attempts}: implement")
            before = _repository_snapshot(self.target)
            before_directories = _repository_directories(self.target)
            worker_failure: str | None = None
            try:
                outcome = self.implement(task, attempt, tuple(failures))
            except ControlFlowSignal:
                _restore_repository_snapshot(self.target, before, before_directories)
                raise
            except Exception as exc:
                worker_failure = f"implementation worker raised {type(exc).__name__}: {exc}"
                stderr = exc.diagnostic if isinstance(exc, ProviderPhaseError) else worker_failure
                outcome = ImplementationOutcome((), exit_code=None, stderr=stderr)
            claimed_paths = outcome.changed_paths
            changed_paths, repository_diff = _repository_changes(before, _repository_snapshot(self.target))
            outcome = replace(outcome, changed_paths=changed_paths, repository_diff=repository_diff)
            try:
                if worker_failure is None:
                    self._validated_paths(claimed_paths)
                self._validate_observed_scope(changed_paths, plan.allowed_paths)
                failure = worker_failure
                if failure is None and not outcome.succeeded:
                    failure = f"implementation exited with {outcome.exit_code}"
                scope_violation = None
                repeated_scope_violation = False
            except ObservedScopeViolation as exc:
                scope_violation = exc
                repeated_scope_violation = any(path in observed_scope_violations for path in exc.outside_paths)
                observed_scope_violations.update(exc.outside_paths)
                failure = self._scope_violation_feedback(task, exc)
            except ValidationError as exc:
                failure = str(exc)
                scope_violation = None
                repeated_scope_violation = False

            # This write is intentionally before the first controller-run test.
            self._write_attempt(task, attempt, outcome, status="implemented", failure=failure)
            task = replace(task, attempts=attempt)
            self._save_task(task)

            if scope_violation is not None and repeated_scope_violation:
                self._write_attempt(task, attempt, outcome, status="failed", failure=failure)
                self.progress(f"Task {task.id} attempt {attempt}/{self.max_attempts}: restoring failed attempt changes")
                _restore_repository_snapshot(self.target, before, before_directories)
                raise ControlFlowSignal(PhaseEscalation(
                    "IMPLEMENT",
                    self._scope_escalation_target(),
                    self._scope_escalation_reason(task, scope_violation),
                ))

            evidence: list[CommandEvidence] = []
            if failure is None:
                for command in plan.focused_tests:
                    result = self.command_runner(command, self.target, self.timeout_seconds)
                    evidence.append(result)
                    if not result.passed:
                        failure = "focused test failed"
                        break
            if failure is None:
                for command in plan.broader_tests:
                    result = self.command_runner(command, self.target, self.timeout_seconds)
                    evidence.append(result)
                    if not result.passed:
                        failure = "broader test failed"
                        break

            review_output: str | None = None
            if failure is None:
                try:
                    review_output = self.review(task, outcome, tuple(evidence))
                    verdict, findings = self._review_result(review_output)
                    if verdict is ReviewVerdict.REQUEST_CHANGES:
                        failure = f"review requested changes: {findings}"
                except (ControlFlowSignal, PhaseRepairExhaustedError):
                    _restore_repository_snapshot(self.target, before, before_directories)
                    raise
                except (PhaseValidationError, StopIteration, ValueError) as exc:
                    failure = f"review output is invalid: {exc}"
                except Exception as exc:
                    failure = f"review worker raised {type(exc).__name__}: {exc}"

            if failure is None:
                task = replace(task, status=TaskStatus.COMPLETED)
                self.progress(f"Task {task.id} attempt {attempt}/{self.max_attempts} completed")
                self._write_attempt(task, attempt, outcome, status="completed", evidence=evidence,
                                    review=review_output)
                self._save_task(task)
                return LoopResult(task.id, task.status, attempt)

            failures.append(failure)
            self.progress(f"Task {task.id} attempt {attempt}/{self.max_attempts} failed: {failure}")
            self._write_attempt(task, attempt, outcome, status="failed", evidence=evidence,
                                review=review_output, failure=failure)
            self.progress(f"Task {task.id} attempt {attempt}/{self.max_attempts}: restoring failed attempt changes")
            _restore_repository_snapshot(self.target, before, before_directories)

        task = replace(task, status=TaskStatus.FAILED)
        self._save_task(task)
        return LoopResult(task.id, task.status, task.attempts, failures[-1])
