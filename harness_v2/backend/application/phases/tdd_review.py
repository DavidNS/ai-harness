"""TDD_REVIEW phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.tdd_common import _task_mapping
from harness_v2.backend.domain.lifecycle import BundleName, PhaseName


def execute(context: PhaseExecutionContext) -> PhaseResult:
    from harness_v2.backend.application.tdd_loop import parse_tdd_review
    inputs = {"run_id": context.run.run_id, "request": context.run.request, "tasks": [_task_mapping(task) for task in context.run.tasks], "implementation": context.artifacts.read_text(context.run.run_id, "tdd/implement.txt") or ""}
    output = context.artifacts.run_worker_text(context.run, BundleName.TDD_BUNDLE, PhaseName.TDD_REVIEW, "tdd_review", inputs)
    review = parse_tdd_review(output)
    context.artifacts.write_json(context.run.run_id, "tdd/review.json", review)
    return PhaseResult()
