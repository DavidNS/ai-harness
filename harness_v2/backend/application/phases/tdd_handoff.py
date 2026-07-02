"""TDD_HANDOFF phase."""

from __future__ import annotations

from harness_v2.backend.application.phase_executor import PhaseExecutionContext, PhaseResult
from harness_v2.backend.application.phases.tdd_common import _task_mapping


def execute(context: PhaseExecutionContext) -> PhaseResult:
    results = {"schema_version": 1, "phase": "tdd", "tasks": [_task_mapping(task) for task in context.run.tasks], "review": context.artifacts.read_json(context.run.run_id, "tdd/review.json") or {}}
    context.artifacts.write_json(context.run.run_id, "published/tdd-results.json", results)
    context.artifacts.write_json(context.run.run_id, "published/tdd-handoff.json", {"schema_version": 1, "bundle": "tdd", "artifacts": ["published/tdd-results.json"], "next_bundle": "KNOWLEDGE_EXTRACT_TDD"})
    return PhaseResult()
