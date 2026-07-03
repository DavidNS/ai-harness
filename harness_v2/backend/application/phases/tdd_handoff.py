"""TDD_HANDOFF phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.domain.tasks import TaskStatus


def execute(context: PhaseExecutionContext) -> PhaseResult:
    context.artifacts.write_json(
        context.run.run_id,
        "published/tdd-handoff.json",
        {
            "schema_version": 1,
            "bundle": "tdd",
            "artifacts": ["tasks.json", "published/tdd-results.json"],
            "next_bundle": "KNOWLEDGE_EXTRACT_TDD",
            "completed_tasks": [task.task_id for task in context.run.tasks if task.status is TaskStatus.COMPLETED],
        },
    )
    return PhaseResult()
