"""TDD_CREATE_TEST phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.tdd_common import _task_mapping
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    inputs = {"run_id": context.run.run_id, "request": context.run.request, "tasks": [_task_mapping(task) for task in context.run.tasks]}
    output = context.artifacts.run_worker_text(context.run, BundleName.TDD_BUNDLE, PhaseName.TDD_CREATE_TEST, "tdd_create_test", inputs)
    context.artifacts.write_text(context.run.run_id, "tdd/create-test.txt", output)
    return PhaseResult()
