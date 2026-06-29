"""Task planning phase execution helpers."""

from __future__ import annotations

import json
import sys
from typing import Callable, Mapping, Protocol

from ..phases import get_phase
from .context import RunContext
from .task_plan_execution import TaskPlanExecution


class TaskExecutionCallbacks(Protocol):
    explorer_scope: Callable[[], dict[str, object]]
    validate_full_sdd_task_coverage: Callable[[Mapping[str, object], Mapping[str, object]], None]
    worker: Callable[[str, Mapping[str, object]], str]
    full_sdd_inputs: Callable[..., dict[str, object]]
    request_brief: Callable[[], str]
    referenced_markdown_documents: Callable[[str], dict[str, str]]


class TaskExecution:
    """Execute task generation and TDD loop phases against shared run context."""

    def __init__(
        self,
        context: RunContext,
        callbacks: TaskExecutionCallbacks,
        invoke_with_repair: Callable[..., str],
    ) -> None:
        self._ctx = context
        self._callbacks = callbacks
        self._task_plans = TaskPlanExecution(context, callbacks, invoke_with_repair)

    def tasks(self) -> None:
        scope = self._callbacks.explorer_scope()
        document = json.loads(self._callbacks.worker("tasks", self._callbacks.full_sdd_inputs("spec.md", "design.md")))
        self._callbacks.validate_full_sdd_task_coverage(document, scope)
        self._task_plans.install_tasks(document["tasks"])

    def simple_task(self) -> None:
        documents = self._callbacks.referenced_markdown_documents(self._ctx.state.load().user_input)
        if documents:
            source = next(iter(documents))
            title = f"Implement the improvement described by {source}"
            criteria = [
                f"The repository implements the improvement described by {source}.",
                "The requested change is implemented and verified.",
            ]
        else:
            title = "Implement the requested change"
            criteria = ["The requested change is implemented and verified"]
        focused_tests, broader_tests = self._simple_task_tests()
        task = {
            "id": "T1",
            "title": title,
            "depends_on": [],
            "acceptance_criteria": criteria,
            "touched_paths": ["."],
            "focused_tests": focused_tests,
            "broader_tests": broader_tests,
            "status": "pending",
        }
        document = {"schema_version": 1, "phase": "tasks", "tasks": [task]}
        get_phase("tasks").validate(json.dumps(document))
        self._ctx.artifacts.write_json("tasks.json", document)
        self._ctx.state.record_artifact("tasks.json", "SIMPLE_TASK")
        self._task_plans.install_tasks([task])

    def tdd(self) -> None:
        self._task_plans.run_tdd()

    def _simple_task_tests(self) -> tuple[list[list[str]], list[list[str]]]:
        focused = [
            ["git", "diff", "--check"]
            if (self._ctx.target / ".git").exists()
            else [sys.executable, "-c", "print('syntax gate skipped outside git')"]
        ]
        if not (self._ctx.target / "tests").is_dir():
            return focused, []
        broader = [
            [sys.executable, "-B", "-m", "unittest", "discover", "tests/integration"],
            [sys.executable, "-B", "-m", "unittest", "tests.acceptance.test_end_to_end"],
        ]
        return focused, broader
