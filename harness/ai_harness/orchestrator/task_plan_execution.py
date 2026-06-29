"""Task plan installation and TDD loop adapter helpers."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol, Sequence

from ..errors import HarnessError
from ..models import Task, TaskStatus
from ..pipeline.tdd_loop import ImplementationOutcome, TaskPlan, TddLoop
from .context import RunContext


class TaskPlanCallbacks(Protocol):
    request_brief: Callable[[], str]


class TestEvidence(Protocol):
    def to_dict(self) -> dict[str, object]: ...


class TaskPlanExecution:
    """Install task plans and adapt TDD loop callbacks to orchestrator services."""

    def __init__(
        self,
        context: RunContext,
        callbacks: TaskPlanCallbacks,
        invoke_with_repair: Callable[..., str],
    ) -> None:
        self._ctx = context
        self._callbacks = callbacks
        self._invoke_with_repair = invoke_with_repair

    def install_tasks(self, raw_tasks: Sequence[Mapping[str, object]]) -> None:
        self._ctx.task_documents = {str(raw["id"]): raw for raw in raw_tasks}
        tasks = [
            Task(
                str(raw["id"]),
                str(raw["title"]),
                tuple(raw["depends_on"]),
                acceptance_criteria=tuple(raw["acceptance_criteria"]),
                test_commands=tuple(
                    " ".join(command) for command in raw["focused_tests"] + raw["broader_tests"]
                ),
            )
            for raw in raw_tasks
        ]
        self._ctx.state.update(tasks=tasks)

    def restore_tasks(self) -> None:
        if not self._ctx.task_documents:
            document = self._ctx.artifacts.read_json("tasks.json")
            self._ctx.task_documents = {str(item["id"]): item for item in document["tasks"]}

    def run_tdd(self) -> None:
        self.restore_tasks()
        plans = [TaskPlan.from_mapping(item) for item in self._ctx.task_documents.values()]
        loop = TddLoop(
            self._ctx.target,
            self._ctx.state,
            plans,
            self._implement,
            self._review,
            artifacts=self._ctx.artifacts,
            timeout_seconds=self._ctx.config.timeout_seconds,
            max_attempts=self._ctx.config.max_attempts,
            progress=self._ctx.progress,
        )
        while True:
            result = loop.run_one()
            if result is None:
                break
            if result.status is TaskStatus.FAILED:
                raise HarnessError(f"task {result.task_id} failed: {result.failure}")
        if any(task.status is not TaskStatus.COMPLETED for task in self._ctx.state.load().tasks):
            raise HarnessError("TDD loop ended with incomplete tasks")

    def _implement(self, task: Task, attempt: int, failures: tuple[str, ...]) -> ImplementationOutcome:
        raw = self._ctx.task_documents[task.id]
        design = (
            self._ctx.artifacts.read("design.md")
            if self._ctx.artifacts.exists("design.md")
            else self._callbacks.request_brief()
        )
        output = self._invoke_with_repair(
            "implement",
            {
                "design.md": design,
                "task": raw,
                "repository": str(self._ctx.target),
                "prior_failures": list(failures),
            },
        )
        artifact = f"implementation/{task.id}/{attempt}.md"
        self._ctx.artifacts.write(artifact, output)
        self._ctx.state.record_artifact(artifact, "TDD_LOOP")
        return ImplementationOutcome(tuple(raw["touched_paths"]), output)

    def _review(self, task: Task, outcome: ImplementationOutcome, evidence: tuple[TestEvidence, ...]) -> str:
        spec = (
            self._ctx.artifacts.read("spec.md")
            if self._ctx.artifacts.exists("spec.md")
            else self._callbacks.request_brief()
        )
        return self._invoke_with_repair(
            "review",
            {
                "spec.md": spec,
                "task": self._ctx.task_documents[task.id],
                "diff": outcome.repository_diff,
                "test_evidence": [item.to_dict() for item in evidence],
            },
        )
